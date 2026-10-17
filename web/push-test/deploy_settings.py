"""Update only BOT settings assets; preserve running services and PWA state."""
import pathlib, json, hashlib, uuid, paramiko

web=pathlib.Path(__file__).resolve().parents[1]
config=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text())
config['hostname']=config.pop('host')
client=paramiko.SSHClient()
client.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
client.connect(**config,timeout=12,look_for_keys=False,allow_agent=False)
try:
 stage='/tmp/radar-settings-'+uuid.uuid4().hex
 ftp=client.open_sftp();ftp.mkdir(stage,mode=0o700);hashes={}
 for name in ['notification-settings.js','notification-settings.css']:
  raw=(web/'robot-push'/name).read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
  with ftp.file(stage+'/'+name,'wb') as f:f.write(raw)
 ftp.close()
 script=r'''
import pathlib,hashlib,json,subprocess,shutil,fcntl,os,re,time
p=pathlib.Path(STAGE)
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in HASHES.items())
def pid(name):return subprocess.check_output(['systemctl','show',name,'--property=MainPID','--value'],text=True).strip()
pids={n:pid(n) for n in ['robot-push','radar-webpush-test']}
current=pathlib.Path('/opt/funding-radar-web/current')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 old=current.resolve();new=old.parent/('20261017-mobile-settings-'+str(int(time.time())))
 fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html');previous=fallback.read_bytes()
 try:
  shutil.copytree(old,new,symlinks=True)
  bot=new/'robot-push'
  for name in HASHES:
   shutil.copyfile(p/name,bot/name);(bot/name).chmod(0o644)
  index=bot/'index.html';html=index.read_text()
  assert 'notification-settings.js?v=' in html
  html=re.sub(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v=20261017-mobile1',html)
  index.write_text(html)
  temp=fallback.with_suffix('.next');temp.write_text(html);temp.chmod(0o644);os.replace(temp,fallback)
  link=current.with_name('current.settings-next');link.symlink_to(new);os.replace(link,current)
  assert all(pid(n)==v for n,v in pids.items())
  assert all(hashlib.sha256((current/'robot-push'/k).read_bytes()).hexdigest()==v for k,v in HASHES.items())
  print(json.dumps({'release':str(new),'previous':str(old),'servicesUnchanged':True,'assetsVerified':True}))
 except Exception:
  fallback.write_bytes(previous)
  if current.resolve()==new:
   link=current.with_name('current.settings-rollback');link.symlink_to(old);os.replace(link,current)
  raise
'''.replace('STAGE',repr(stage)).replace('HASHES',repr(hashes))
 stdin,stdout,stderr=client.exec_command('sudo -n python3 -',timeout=90)
 stdin.write(script.encode());stdin.channel.shutdown_write()
 output,error=stdout.read().decode(),stderr.read().decode()
 if stdout.channel.recv_exit_status():raise RuntimeError(error[:2000])
 print(output)
finally:client.close()
