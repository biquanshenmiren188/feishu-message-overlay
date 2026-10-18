"""Publish the inspected retention-only receiver change; no credentials/state rollback."""
import argparse,hashlib,json,pathlib,paramiko,subprocess
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--report',type=pathlib.Path,required=True);a=p.parse_args()
source=pathlib.Path(__file__).with_name('server.py').read_text(encoding='utf-8')
payload=dict(apply=a.apply,source=source,sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=pathlib.Path(__file__).parent,text=True).strip(),expected='1e3ab8f106769e6577748884cfcce1ffb2ae310710fb003c9a2a324e5441a394')
script=r'''
import pathlib,json,hashlib,subprocess,fcntl,time,os,shutil,urllib.request
P=PAYLOAD
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pid(name):return subprocess.check_output(['systemctl','show',name,'--property=MainPID','--value'],text=True).strip()
target=pathlib.Path('/opt/robot-push/server.py')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert sha(target)==P['expected'],'Receiver changed; inspect again'
 compile(P['source'],str(target),'exec')
 before=pid('radar-webpush-test')
 if not P['apply']:print(json.dumps(dict(preflight=True,serverHash=sha(target))))
 else:
  backup=pathlib.Path('/opt/robot-push/backups')/('history30-'+str(int(time.time())))
  backup.mkdir(mode=0o700);shutil.copy2(target,backup/'server.py')
  candidate=target.with_name('server.history-next');candidate.write_text(P['source']);shutil.copymode(target,candidate)
  try:
   os.replace(candidate,target);subprocess.run(['systemctl','restart','robot-push'],check=True,timeout=30)
   connected=False
   for attempt in range(40):
    try:
     with urllib.request.urlopen('http://127.0.0.1:18883/health',timeout=2) as response:health=json.load(response)
     if health.get('ready') and health.get('lastSourceAge') is not None and health['lastSourceAge']<45:connected=True;break
    except Exception:pass
    time.sleep(.5)
   assert connected,'Receiver did not reconnect'
   assert pid('radar-webpush-test')==before,'Push service unexpectedly restarted'
   report=dict(backup=str(backup),serverSha256=sha(target),sourceCommit=P['sourceCommit'],connected=connected,normalCount=health['normalCount'],pushServiceUnchanged=True)
   (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
  except Exception:
   shutil.copy2(backup/'server.py',candidate);os.replace(candidate,target)
   subprocess.run(['systemctl','restart','robot-push'],check=True,timeout=30)
   raise
'''.replace('PAYLOAD',repr(payload),1)
cfg=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text());cfg['hostname']=cfg.pop('host')
c=paramiko.SSHClient();c.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
try:
 c.connect(**cfg,timeout=15,look_for_keys=False,allow_agent=False)
 i,o,e=c.exec_command('sudo -n python3 -',timeout=90);i.write(script);i.channel.shutdown_write()
 result=o.read().decode();error=e.read().decode()
 if o.channel.recv_exit_status():raise RuntimeError(error[:2000])
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(result,encoding='utf-8');print(result)
finally:c.close()
