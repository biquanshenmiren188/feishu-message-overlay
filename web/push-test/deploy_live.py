"""Promote the existing phone subscription; patch only the BOT settings assets."""
import pathlib, json, hashlib, uuid, argparse, paramiko
parser=argparse.ArgumentParser()
parser.add_argument('--ssh-config',type=pathlib.Path,default=pathlib.Path.home()/'.ssh/tencent-radar-initial.json')
parser.add_argument('--known-hosts',type=pathlib.Path,default=pathlib.Path.home()/'.ssh/tencent-radar-known-hosts')
args=parser.parse_args()
source=pathlib.Path(__file__).resolve().parents[1]
def connect():
 config=json.loads(args.ssh_config.read_text())
 config['hostname']=config.pop('host')
 client=paramiko.SSHClient();client.load_host_keys(str(args.known_hosts))
 client.connect(**config,timeout=12,look_for_keys=False,allow_agent=False)
 return client
def run(client,script,timeout):
 stdin,stdout,stderr=client.exec_command('sudo -n python3 -',timeout=timeout)
 stdin.write(script.encode('utf-8'));stdin.channel.shutdown_write()
 output,error=stdout.read().decode('utf-8'),stderr.read().decode('utf-8')
 if stdout.channel.recv_exit_status():raise RuntimeError(error[:3000])
 return output
files={name:source/'push-test'/name for name in ['server.py','server_test.py','live.py','live_test.py','profiles.py','profiles_test.py','delivery.py','delivery_test.py','signals.py','preferences.py','radar-webpush-test.service','index.html','app.js','sw.js']}
files.update({name:source/'robot-push'/name for name in ['notification-settings.js','notification-settings.css']})
s=connect()
try:
 stage='/tmp/radar-webpush-live-'+uuid.uuid4().hex
 ftp=s.open_sftp();ftp.mkdir(stage,mode=0o700);hashes={}
 for name,path in files.items():
  raw=path.read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
  with ftp.file(stage+'/'+name,'wb') as f:f.write(raw)
  ftp.chmod(stage+'/'+name,0o600)
 ftp.close()
 script=r'''
import pathlib,subprocess,json,hashlib,shutil,os,time,urllib.request,fcntl
p=pathlib.Path(STAGE);expected=HASHES
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in expected.items())
def cmd(args):
 r=subprocess.run(args,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-2000:])
 return r.stdout.strip()
root=pathlib.Path('/opt/radar-webpush-test');venv=root/'venv/bin/python';public=root/'public'
# Test candidate modules in isolation before touching the running service.
tests=cmd([str(venv),'-m','unittest','discover','-s',str(p),'-p','*_test.py'])
pid=cmd(['systemctl','show','robot-push','--property=MainPID','--value'])
unit=pathlib.Path('/etc/systemd/system/radar-webpush-test.service')
backup=root/('backup-live-'+str(int(time.time())));backup.mkdir(mode=0o700)
targets={}
for name in expected:
 if name.startswith('notification-settings'):continue
 targets[name]=unit if name.endswith('.service') else (public if name in ['index.html','app.js','sw.js'] else root)/name
for name,dest in targets.items():
 if dest.exists():shutil.copyfile(dest,backup/name)
current=pathlib.Path('/opt/funding-radar-web/current');old=current.resolve()
new=old.parent/('20261017-webpush-live-'+str(int(time.time())))
try:
 with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  assert current.resolve()==old,'web release changed during deployment'
  shutil.copytree(old,new,symlinks=True)
  web=new/'robot-push'
  for name in ['notification-settings.js','notification-settings.css']:
   shutil.copyfile(p/name,web/name);(web/name).chmod(0o644)
  index=web/'index.html';html=index.read_text()
  assert '</body>' in html
  if 'notification-settings.js' not in html:
   html=html.replace('</body>','<script type="module" src="./notification-settings.js?v=20261017-live1"></script></body>')
  import re
  html=re.sub(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v=20261017-mobile1',html)
  index.write_text(html)
  for name,dest in targets.items():shutil.copyfile(p/name,dest);dest.chmod(0o644)
  cmd(['systemd-analyze','verify',str(unit)])
  cmd(['systemctl','daemon-reload']);cmd(['systemctl','restart','radar-webpush-test'])
  time.sleep(2)
  health=json.loads(urllib.request.urlopen('http://127.0.0.1:18885/radar/push-test/api/health',timeout=5).read())
  assert health=={'ok':True,'mode':'live'}
  link=current.with_name('current.webpush-live-next');link.symlink_to(new);os.replace(link,current)
  state=json.loads(pathlib.Path('/var/lib/radar-webpush-test/state.json').read_text())
  req=urllib.request.Request('http://127.0.0.1:18885/radar/push-test/api/status',headers={'Authorization':'Bearer '+state['token']})
  status=json.loads(urllib.request.urlopen(req,timeout=5).read())
  assert status['subscribed'] and status['source']['connected'],status['source']
  assert pid==cmd(['systemctl','show','robot-push','--property=MainPID','--value'])
  print(json.dumps({'health':health,'settings':status['settings'],'source':status['source'],'subscribed':status['subscribed'],'lastDelivery':status['lastDelivery'],'previewRows':len(status['preview']),'previousWeb':str(old),'release':str(new),'backup':str(backup),'hashes':expected,'publisherUnchanged':True,'deployedAt':int(time.time())}))
except Exception:
 for name,dest in targets.items():
  if (backup/name).exists():shutil.copyfile(backup/name,dest)
 if current.resolve()==new:
  link=current.with_name('current.webpush-rollback');link.symlink_to(old);os.replace(link,current)
 cmd(['systemctl','daemon-reload']);cmd(['systemctl','restart','radar-webpush-test'])
 raise
'''.replace('STAGE',repr(stage)).replace('HASHES',repr(hashes))
 result=json.loads(run(s,script,timeout=120))
 print(json.dumps(result,ensure_ascii=False))
finally:s.close()
