"""Update BOT settings, optionally its binding API; preserve PWA state and publisher."""
import pathlib, json, hashlib, uuid, paramiko, argparse, subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--with-binding-api',action='store_true',help='Deploy the authenticated binding endpoint with its tests')
parser.add_argument('--with-profiles',action='store_true',help='Deploy independent push plans and user code creation')
args=parser.parse_args()
# The former binding API now lives in the profile-aware server bundle.
if args.with_binding_api:args.with_profiles=True

web=pathlib.Path(__file__).resolve().parents[1]
config=json.loads((pathlib.Path.home()/'.ssh/tencent-radar-initial.json').read_text())
config['hostname']=config.pop('host')
client=paramiko.SSHClient()
client.load_host_keys(str(pathlib.Path.home()/'.ssh/tencent-radar-known-hosts'))
client.connect(**config,timeout=12,look_for_keys=False,allow_agent=False)
try:
 stage='/tmp/radar-settings-'+uuid.uuid4().hex
 ftp=client.open_sftp();ftp.mkdir(stage,mode=0o700);hashes={}
 files={name:web/'robot-push'/name for name in ['notification-settings.js','notification-settings.css']}
 if args.with_binding_api or args.with_profiles:files.update({name:web/'push-test'/name for name in ['server.py','server_test.py','live_test.py','delivery_test.py']})
 if args.with_profiles:files.update({name:web/'push-test'/name for name in ['live.py','profiles.py','profiles_test.py']})
 baselines={}
 for name in (['server.py','live.py'] if args.with_profiles else ['server.py']):
  baseline=subprocess.check_output(['git','show','HEAD:web/push-test/'+name],cwd=web.parent).replace(b'\r\n',b'\n')
  baselines[name]=hashlib.sha256(baseline).hexdigest()
 if args.with_profiles:
  old_profile=subprocess.run(['git','show','HEAD:web/push-test/profiles.py'],cwd=web.parent,capture_output=True)
  baselines['profiles.py']=hashlib.sha256(old_profile.stdout.replace(b'\r\n',b'\n')).hexdigest() if old_profile.returncode==0 else None
 for name,path in files.items():
  raw=path.read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest()
  with ftp.file(stage+'/'+name,'wb') as f:f.write(raw)
 ftp.close()
 script=r'''
import pathlib,hashlib,json,subprocess,shutil,fcntl,os,re,time,urllib.request,sys,tempfile
p=pathlib.Path(STAGE)
assert all(hashlib.sha256((p/k).read_bytes()).hexdigest()==v for k,v in HASHES.items())
def pid(name):return subprocess.check_output(['systemctl','show',name,'--property=MainPID','--value'],text=True).strip()
pids={n:pid(n) for n in ['robot-push','radar-webpush-test']}
current=pathlib.Path('/opt/funding-radar-web/current')
root=pathlib.Path('/opt/radar-webpush-test')
backend='server.py' in HASHES
backend_files=[name for name in HASHES if name.endswith('.py')]
def request(route,token=None):
 req=urllib.request.Request('http://127.0.0.1:18885/radar/push-test/api/'+route,headers={'Authorization':'Bearer '+token} if token else {})
 with urllib.request.urlopen(req,timeout=5) as response:return json.loads(response.read())
def read_state():return json.loads(pathlib.Path('/var/lib/radar-webpush-test/state.json').read_text())
state=read_state()
registry_path=pathlib.Path('/var/lib/radar-webpush-test/profiles.json')
registry=json.loads(registry_path.read_text()) if registry_path.exists() else None
profile_states={}
for item in registry['profiles'] if registry else []:
 assert re.fullmatch('[a-f0-9]{32}',item['id'])
 profile_states[item['id']]=json.loads((registry_path.parent/'profiles'/item['id']/'state.json').read_text())
if backend:
 for name,expected in BASELINES.items():
  if expected is None:assert not (root/name).exists(),'New backend module already exists; review before deploying'
  else:assert hashlib.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()==expected,'Backend changed; review before deploying'
 candidate=p/'candidate';candidate.mkdir()
 for f in root.glob('*.py'):shutil.copyfile(f,candidate/f.name)
 for name in backend_files:shutil.copyfile(p/name,candidate/name)
 tests=subprocess.run([str(root/'venv/bin/python'),'-m','unittest','discover','-s',str(candidate),'-p','*_test.py'],capture_output=True,text=True)
 if tests.returncode:raise RuntimeError(tests.stderr[-3000:])
 if 'profiles.py' in HASHES:
  # Rehearse migration against a private copy, never a second live feed reader.
  sys.path.insert(0,str(candidate))
  from profiles import Profiles
  with tempfile.TemporaryDirectory(dir=p) as rehearsal:
   sandbox=pathlib.Path(rehearsal)
   (sandbox/'state.json').write_text(json.dumps(state))
   if registry:
    (sandbox/'profiles.json').write_text(json.dumps(registry))
    for key,value in profile_states.items():
     directory=sandbox/'profiles'/key;directory.mkdir(parents=True)
     (directory/'state.json').write_text(json.dumps(value))
   def no_send(*args):raise RuntimeError('Migration must not send')
   app=Profiles(sandbox,'/etc/radar-webpush-test/config.json',no_send)
   assert app.resolve(state['token']).state==state,'Migration changed existing state'
   again=Profiles(sandbox,'/etc/radar-webpush-test/config.json',no_send)
   assert again.resolve(state['token']).state==state,'Migration was not idempotent'
   for key,value in profile_states.items():assert again.accounts[key].state==value,'Existing profile changed'
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 old=current.resolve();new=old.parent/('20261017-switch-code-'+str(int(time.time())))
 fallback=pathlib.Path('/opt/radar-webpush-test/public/index.html');previous=fallback.read_bytes()
 backup=root/('backup-'+new.name);backup.mkdir(mode=0o700)
 (backup/'index.html').write_bytes(previous)
 if backend:
  for name in backend_files:
   if (root/name).exists():shutil.copyfile(root/name,backup/name)
  # State backup is for recovery only; rollback never rewinds notification seq.
  (backup/'state.json').write_text(json.dumps(state));(backup/'state.json').chmod(0o600)
  if registry:
   (backup/'profiles.json').write_text(json.dumps(registry));(backup/'profiles.json').chmod(0o600)
   for key,value in profile_states.items():
    directory=backup/'profiles'/key;directory.mkdir(parents=True,mode=0o700)
    (directory/'state.json').write_text(json.dumps(value));(directory/'state.json').chmod(0o600)
 try:
  shutil.copytree(old,new,symlinks=True)
  bot=new/'robot-push'
  for name in ['notification-settings.js','notification-settings.css']:
   shutil.copyfile(p/name,bot/name);(bot/name).chmod(0o644)
  index=bot/'index.html';html=index.read_text()
  assert 'notification-settings.js?v=' in html
  html=re.sub(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v=20261017-switch1',html)
  index.write_text(html)
  if backend:
   for name in backend_files:
    temp=root/(name+'.next');shutil.copyfile(p/name,temp);temp.chmod(0o644);os.replace(temp,root/name)
   subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
   for attempt in range(20):
    try:
     assert request('health')=={'ok':True,'mode':'live'}
     if request('status',state['token'])['source']['connected']:break
    except (OSError,AssertionError):pass
    time.sleep(.5)
   else:raise RuntimeError('Push service did not recover')
   binding=request('binding',state['token'])
   config=json.loads(pathlib.Path('/etc/radar-webpush-test/config.json').read_text())
   assert binding=={'pushCode':config['pairCode']}
  temp=fallback.with_suffix('.next');temp.write_text(html);temp.chmod(0o644);os.replace(temp,fallback)
  link=current.with_name('current.settings-next');link.symlink_to(new);os.replace(link,current)
  assert pid('robot-push')==pids['robot-push']
  if not backend:assert pid('radar-webpush-test')==pids['radar-webpush-test']
  after=read_state()
  assert state.get('subscription')==after.get('subscription') and state['token']==after['token']
  assert state['live']['settings']==after['live']['settings'] and state['live']['revision']==after['live']['revision']
  assert after['seq']>=state['seq']
  for key,before in profile_states.items():
   after_profile=json.loads((registry_path.parent/'profiles'/key/'state.json').read_text())
   assert before.get('subscription')==after_profile.get('subscription') and before['token']==after_profile['token']
   assert before['live']['settings']==after_profile['live']['settings'] and before['live']['revision']==after_profile['live']['revision']
   assert after_profile['seq']>=before['seq']
  assert all(hashlib.sha256(((root if k.endswith('.py') else current/'robot-push')/k).read_bytes()).hexdigest()==v for k,v in HASHES.items())
  preserved=0
  for before in old.rglob('*'):
   relative=before.relative_to(old)
   if before.is_file() and str(relative) not in ['robot-push/index.html','robot-push/notification-settings.js','robot-push/notification-settings.css']:
    assert before.read_bytes()==(new/relative).read_bytes(),str(relative)
    preserved+=1
  print(json.dumps({'release':str(new),'previous':str(old),'backup':str(backup),'publisherUnchanged':True,'pushServiceRestarted':backend,'bindingVerified':backend,'subscriptionAndSettingsPreserved':True,'assetsVerified':True,'otherFilesPreserved':preserved}))
 except Exception:
  fallback.write_bytes(previous)
  if current.resolve()==new:
   link=current.with_name('current.settings-rollback');link.symlink_to(old);os.replace(link,current)
  if backend:
   subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
   for name in backend_files:
    if (backup/name).exists():shutil.copyfile(backup/name,root/name)
    else:(root/name).unlink(missing_ok=True)
   subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  raise
'''.replace('STAGE',repr(stage)).replace('HASHES',repr(hashes)).replace('BASELINES',repr(baselines))
 stdin,stdout,stderr=client.exec_command('sudo -n python3 -',timeout=90)
 stdin.write(script.encode());stdin.channel.shutdown_write()
 output,error=stdout.read().decode(),stderr.read().decode()
 if stdout.channel.recv_exit_status():raise RuntimeError(error[:2000])
 print(output)
finally:client.close()
