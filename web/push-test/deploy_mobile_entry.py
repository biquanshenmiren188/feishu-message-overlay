"""Serve BOT at the existing installed PWA entry, preserving subscription/state."""
import argparse, hashlib, json, pathlib, uuid
import paramiko

parser=argparse.ArgumentParser()
parser.add_argument('--ssh-config',type=pathlib.Path,default=pathlib.Path.home()/'.ssh/tencent-radar-initial.json')
parser.add_argument('--known-hosts',type=pathlib.Path,default=pathlib.Path.home()/'.ssh/tencent-radar-known-hosts')
args=parser.parse_args()
web=pathlib.Path(__file__).resolve().parents[1]
files={'notification-settings.js':web/'robot-push/notification-settings.js','sw.js':web/'push-test/sw.js','nginx.conf':web/'push-test/nginx.conf'}
config=json.loads(args.ssh_config.read_text());config['hostname']=config.pop('host')
client=paramiko.SSHClient();client.load_host_keys(str(args.known_hosts))
client.connect(**config,timeout=12,look_for_keys=False,allow_agent=False)
try:
 stage='/tmp/radar-mobile-entry-'+uuid.uuid4().hex
 ftp=client.open_sftp();ftp.mkdir(stage,mode=0o700);hashes={}
 for name,path in files.items():
  raw=path.read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
  with ftp.file(stage+'/'+name,'wb') as f:f.write(raw)
 ftp.close()
 script=r'''
import pathlib,subprocess,json,hashlib,shutil,os,time,fcntl,re
p=pathlib.Path(STAGE)
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in HASHES.items())
def cmd(args):
 r=subprocess.run(args,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-2000:])
 return r.stdout
statefile=pathlib.Path('/var/lib/radar-webpush-test/state.json')
def identity():
 s=json.loads(statefile.read_text())
 return {k:s.get(k) for k in ['token','subscription']}
before=identity()
pids={n:cmd(['systemctl','show',n,'--property=MainPID','--value']) for n in ['robot-push','radar-webpush-test']}
current=pathlib.Path('/opt/funding-radar-web/current');old=current.resolve()
new=old.parent/('20261017-mobile-bot-'+str(int(time.time())))
public=pathlib.Path('/opt/radar-webpush-test/public')
nginx=pathlib.Path('/etc/nginx/snippets/radar-webpush-test.conf')
backup=public.parent/('backup-mobile-entry-'+str(int(time.time())));backup.mkdir(mode=0o700)
targets={'nginx.conf':nginx,'sw.js':public/'sw.js','index.html':public/'index.html'}
for name,dest in targets.items():shutil.copyfile(dest,backup/name)
def switch(target):
 link=current.with_name('current.mobile-entry-next');link.symlink_to(target);os.replace(link,current)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 assert current.resolve()==old,'release changed'
 try:
  shutil.copytree(old,new,symlinks=True)
  bot=new/'robot-push';index=bot/'index.html';html=index.read_text()
  assert '<head>' in html and 'id="feed"' in html
  if '<base ' not in html:html=html.replace('<head>','<head><base href="/radar/robot-push/">',1)
  if 'manifest.webmanifest' not in html:html=html.replace('</head>','<link rel="manifest" href="/radar/push-test/manifest.webmanifest" crossorigin="use-credentials"></head>',1)
  html=re.sub(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v=20261017-mobile1',html)
  index.write_text(html)
  shutil.copyfile(p/'notification-settings.js',bot/'notification-settings.js')
  (bot/'notification-settings.js').chmod(0o644)
  # Fallback cache has the same current overlays, not the repository's older BOT.
  (public/'index.html').write_text(html)
  shutil.copyfile(p/'sw.js',public/'sw.js');(public/'sw.js').chmod(0o644)
  shutil.copyfile(p/'nginx.conf',nginx);nginx.chmod(0o644)
  cmd(['nginx','-t']);switch(new);cmd(['systemctl','reload','nginx'])
  assert '<base href="/radar/robot-push/">' in html
  assert '20261017-mobile1' in html
  assert 'button.click()' not in (bot/'notification-settings.js').read_text()
  assert 'radar-delivery-v5' in (public/'sw.js').read_text()
  # The origin denies non-CDN requests; verify public routes in the authenticated browser.
  assert before==identity(),'subscription identity changed'
  assert all(cmd(['systemctl','show',n,'--property=MainPID','--value'])==pid for n,pid in pids.items())
  print(json.dumps({'release':str(new),'previous':str(old),'backup':str(backup),'botAtInstalledEntry':True,'subscriptionPreserved':True,'servicesUnchanged':True}))
 except Exception:
  for name,dest in targets.items():shutil.copyfile(backup/name,dest)
  if current.resolve()==new:switch(old)
  cmd(['nginx','-t']);cmd(['systemctl','reload','nginx'])
  raise
'''.replace('STAGE',repr(stage)).replace('HASHES',repr(hashes))
 stdin,stdout,stderr=client.exec_command('sudo -n python3 -',timeout=120)
 stdin.write(script.encode());stdin.channel.shutdown_write()
 output,error=stdout.read().decode(),stderr.read().decode()
 if stdout.channel.recv_exit_status():raise RuntimeError(error[:3000])
 print(output)
finally:client.close()
