"""Publish only the rebuilt BOT summary bundle and its wrapping style.

Requires a snapshot manifest, matching PWA fallback, and prepared candidate.
Default is a read-only preflight; --apply performs the atomic static release.
"""
import argparse, hashlib, json, pathlib, paramiko

p=argparse.ArgumentParser()
p.add_argument('--baseline',type=pathlib.Path,required=True)
p.add_argument('--candidate',type=pathlib.Path,required=True)
p.add_argument('--report',type=pathlib.Path,required=True)
p.add_argument('--apply',action='store_true')
a=p.parse_args()
baseline=json.loads((a.baseline/'manifest.json').read_text(encoding='utf-8'))
candidate=json.loads((a.candidate/'manifest.json').read_text(encoding='utf-8'))
assert candidate['sourceRelease']==baseline['release']
files={}
for name,item in candidate['files'].items():
 data=(a.candidate/name).read_bytes()
 assert hashlib.sha256(data).hexdigest()==item['sha256'],name
 files[name]=data.decode('utf-8')
fallback=(a.baseline/'pwa-fallback.html').read_bytes()
assert fallback==(a.baseline/'robot-push/index.html').read_bytes(),'Inspect the different PWA fallback first'
payload=dict(apply=a.apply,baseline=baseline,candidate=candidate,files=files,fallbackSha=hashlib.sha256(fallback).hexdigest())
script=r'''
import pathlib,json,hashlib,fcntl,subprocess,shutil,os,time
P=PAYLOAD
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pids():return {n:subprocess.check_output(['systemctl','show',n,'--property=MainPID','--value'],text=True).strip() for n in ['robot-push','radar-webpush-test']}
web=pathlib.Path('/opt/funding-radar-web');current=web/'current'
fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 old=current.resolve();assert str(old)==P['baseline']['release'],'Production changed; inspect again'
 for name,item in P['baseline']['files'].items():assert sha(old/name)==item['sha256'],'Changed source: '+name
 for name,digest in P['candidate']['sourceHashes'].items():assert hashlib.sha256((old/name).read_text().encode()).hexdigest()==digest,'Changed module: '+name
 assert sha(fallback)==P['fallbackSha'],'PWA fallback changed'
 before=pids();previous=fallback.read_bytes()
 assert set(P['files'])==set(P['candidate']['files'])
 for name,content in P['files'].items():
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
  assert name=='robot-push/index.html' or name.startswith(('performance-20261017/bot-summary-','performance-20261017/summary-risk-'))
  if name!='robot-push/index.html':assert not (old/name).exists(),'Use new immutable asset names'
  assert hashlib.sha256(content.encode()).hexdigest()==P['candidate']['files'][name]['sha256']
 if not P['apply']:
  print(json.dumps(dict(preflight=True,release=str(old),files=len(P['files']),services=before)))
 else:
  name='20261017-summary-risk-'+str(int(time.time()))
  new=web/'releases'/name;backup=web/'backups'/name
  assert not new.exists() and not backup.exists()
  original={str(f.relative_to(old)):sha(f) for f in old.rglob('*') if f.is_file() and not f.is_symlink()}
  backup.mkdir(parents=True);(backup/'pwa-index.html').write_bytes(previous)
  (backup/'previous-target.txt').write_text(str(old));(backup/'candidate-manifest.json').write_text(json.dumps(P['candidate']))
  shutil.copytree(old,new,symlinks=True)
  for relative,content in P['files'].items():
   dest=new/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content.encode())
  preserved=0
  for relative,digest in original.items():
   assert sha(old/relative)==digest,'Concurrent modification: '+relative
   if relative not in P['files']:
    assert sha(new/relative)==digest,'Unrelated file changed: '+relative
    preserved+=1
  for relative,item in P['candidate']['files'].items():assert sha(new/relative)==item['sha256']
  switched=False;tmp=fallback.with_name('index.performance-next')
  try:
   assert current.resolve()==old and sha(fallback)==P['fallbackSha']
   tmp.write_bytes(P['files']['robot-push/index.html'].encode());shutil.copymode(fallback,tmp)
   link=web/'current.performance-next';link.symlink_to(new);os.replace(link,current);switched=True
   os.replace(tmp,fallback)
   assert pids()==before,'Unexpected service restart'
   report=dict(release=str(new),previous=str(old),backup=str(backup),preservedFiles=preserved,servicesUnchanged=True,hashes={n:sha(new/n) for n in P['files']},fallbackSha256=sha(fallback))
   (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
  except Exception:
   tmp.write_bytes(previous);os.replace(tmp,fallback)
   if switched:
    link=web/'current.performance-rollback';link.symlink_to(old);os.replace(link,current)
   raise
'''.replace('PAYLOAD',repr(payload),1)
cfg=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text())
cfg['hostname']=cfg.pop('host')
c=paramiko.SSHClient();c.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
try:
 c.connect(**cfg,timeout=15,look_for_keys=False,allow_agent=False)
 stdin,stdout,stderr=c.exec_command('sudo -n python3 -',timeout=120)
 stdin.write(script);stdin.channel.shutdown_write()
 result=stdout.read().decode();error=stderr.read().decode()
 if stdout.channel.recv_exit_status():raise RuntimeError(error[:2000])
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(result,encoding='utf-8');print(result)
finally:c.close()
