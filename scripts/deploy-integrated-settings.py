"""Incrementally migrate phone settings; preserve identities, queues and existing UI assets.

Run as root: python3 deploy-integrated-settings.py STAGE SOURCE_SHA.
Only the Web Push service restarts; no test messages are sent.
"""
import fcntl,hashlib,json,os,re,shutil,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path

stage=Path(sys.argv[1]).resolve();sha=sys.argv[2]
assert stage.parent==Path('/tmp') and stage.name.startswith('radar-settings-live-')
assert re.fullmatch('[a-f0-9]{40}',sha)
manifest=json.loads((stage/'manifest.json').read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,h in manifest['assets'].items():assert digest(stage/'files'/name)==h
root=Path('/opt/radar-webpush-test');current=Path('/opt/funding-radar-web/current')
backend=['live.py','preferences.py','advanced_rules.py']
def pid(service):return subprocess.check_output(['systemctl','show',service,'--property=MainPID','--value'],text=True).strip()
def states():
 base=Path('/var/lib/radar-webpush-test')
 return {str(p):json.loads(p.read_text()) for p in [base/'state.json',*sorted((base/'profiles').glob('*/state.json'))] if p.exists()}
def identities():return {p:{k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')} for p,d in states().items()}
def authenticated_status():
 result=[]
 for p,d in states().items():
  if not d.get('token'):continue
  req=urllib.request.Request('http://127.0.0.1:18885/radar/push-test/api/status',headers={'Authorization':'Bearer '+d['token']})
  with urllib.request.urlopen(req,timeout=5) as r:body=json.load(r)
  assert body['settings']==d['live']['settings']
  assert isinstance(body['blockedHistory'],list)
  result.append(True)
 return len(result)

with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 old=current.resolve();assert old.parent==Path('/opt/funding-radar-web/releases')
 for name,h in manifest['baseline'].items():
  path=root/name if name.endswith('.py') else old/'robot-push/notification-settings.js'
  assert (digest(path) if path.exists() else None)==h,'Production source drift: '+name
 before=identities();publisher=pid('robot-push');assert int(publisher)>0
 fallback=root/'public/index.html';fallback_before=fallback.read_bytes()
 pwa_files={p.name:digest(p) for p in (root/'public').iterdir() if p.is_file() and p.name!='index.html'}
 scope_link=root/'public/settings';scope_created=not scope_link.exists()
 if not scope_created:assert scope_link.is_symlink() and str(scope_link.readlink())=='/opt/funding-radar-web/current/robot-push/settings'
 config_hash=digest(Path('/etc/radar-webpush-test/config.json'))
 prior=json.loads((old/'settings-preview-source.json').read_text())
 for name,h in prior['assets'].items():assert digest(old/'robot-push/settings'/name)==h
 candidate=stage/'candidate';candidate.mkdir()
 for p in root.glob('*.py'):shutil.copyfile(p,candidate/p.name)
 for name in backend+['advanced_rules_test.py']:shutil.copyfile(stage/'files/web/push-test'/name,candidate/name)
 test=subprocess.run([str(root/'venv/bin/python'),'-m','unittest','discover','-s',str(candidate),'-p','*_test.py'],capture_output=True,text=True)
 if test.returncode:raise RuntimeError(test.stderr[-6000:])
 print(test.stderr.strip(),flush=True)
 # Instantiate a private snapshot twice with a sender that refuses all output.
 sys.path.insert(0,str(candidate))
 from profiles import Profiles
 with tempfile.TemporaryDirectory(dir=stage) as tmp:
  sandbox=Path(tmp);livebase=Path('/var/lib/radar-webpush-test')
  for path,data in states().items():
   target=sandbox/Path(path).relative_to(livebase);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(data));target.chmod(0o600)
  shutil.copyfile(livebase/'profiles.json',sandbox/'profiles.json')
  original={str(p.relative_to(sandbox)):p.read_bytes() for p in sandbox.rglob('*.json')}
  def no_send(*a):raise RuntimeError('Migration must never send')
  for _ in range(2):
   Profiles(sandbox,'/etc/radar-webpush-test/config.json',no_send)
   for name,raw in original.items():assert json.loads((sandbox/name).read_text())==json.loads(raw),'Migration altered state: '+name
 release='20261022-settings-live-'+str(int(time.time()))
 new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
 for name in backend:
  if (root/name).exists():shutil.copyfile(root/name,backup/name)
 (backup/'fallback.html').write_bytes(fallback_before)
 (backup/'previous-release.txt').write_text(str(old))
 exclude={'robot-push/index.html','robot-push/notification-settings.js','settings-preview-source.json'}
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and not str(p.relative_to(old)).startswith('robot-push/settings/') and str(p.relative_to(old)) not in exclude}
 shutil.copytree(old,new,symlinks=True)
 for name in ('index.html','style.css','app.js','rules.js'):
  shutil.copyfile(stage/'files/web/robot-push/settings'/name,new/'robot-push/settings'/name)
 shutil.copyfile(stage/'files/web/robot-push/notification-settings.js',new/'robot-push/notification-settings.js')
 def version(raw):
  text=raw.decode();out,n=re.subn(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v=20261022-integrated1',text)
  assert n==1,'Expected exactly one settings entry';return out.encode()
 (new/'robot-push/index.html').write_bytes(version((old/'robot-push/index.html').read_bytes()))
 fallback_new=version(fallback_before)
 source={'source_sha':sha,'repository':'biquanshenmiren188/feishu-message-overlay','assets':{n:manifest['assets']['web/robot-push/settings/'+n] for n in ('index.html','style.css','app.js','rules.js')},'mode':'integrated-mobile'}
 (new/'settings-preview-source.json').write_text(json.dumps(source,indent=2)+'\n')
 assert all(digest(new/p)==h for p,h in preserved.items())
 assert identities()==before,'Settings changed during staging; recheck before retry'
 changed=False
 try:
  for name in backend:
   temp=root/(name+'.next');shutil.copyfile(stage/'files/web/push-test'/name,temp);temp.chmod(0o644);os.replace(temp,root/name)
  changed=True
  subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  for attempt in range(20):
   try:count=authenticated_status();break
   except Exception:
    if attempt==19:raise
    time.sleep(.25)
  assert identities()==before,'Restart altered settings or binding'
  assert pid('robot-push')==publisher,'Publisher unexpectedly restarted'
  assert digest(Path('/etc/radar-webpush-test/config.json'))==config_hash
  temp=fallback.with_suffix('.next');temp.write_bytes(fallback_new);temp.chmod(0o644);os.replace(temp,fallback)
  if scope_created:scope_link.symlink_to('/opt/funding-radar-web/current/robot-push/settings',target_is_directory=True)
  link=current.with_name('current.settings-live-next');link.symlink_to(new);os.replace(link,current)
  for name in backend:assert digest(root/name)==manifest['assets']['web/push-test/'+name]
  for name in source['assets']:assert digest(current/'robot-push/settings'/name)==source['assets'][name]
  assert all(digest(current/p)==h for p,h in preserved.items())
  assert all(digest(root/'public'/p)==h for p,h in pwa_files.items())
  result=dict(release=str(new),previous=str(old),backup=str(backup),source_sha=sha,tests=test.stderr.strip(),profile_count=count,existing_files_preserved=len(preserved),settings_and_bindings_unchanged=True,publisher_pid_unchanged=True,push_service_restarted=True,pwa_identity_and_worker_unchanged=True)
  (backup/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
 except Exception:
  if current.resolve()==new:
   link=current.with_name('current.settings-live-rollback');link.symlink_to(old);os.replace(link,current)
  fallback.write_bytes(fallback_before)
  if scope_created and scope_link.is_symlink() and str(scope_link.readlink())=='/opt/funding-radar-web/current/robot-push/settings':scope_link.unlink()
  # Never roll back notification state/sequence. If someone saved new settings,
  # retain their compatible backend and roll back only the UI.
  if changed and identities()==before:
   for name in backend:
    if (backup/name).exists():shutil.copyfile(backup/name,root/name)
    elif (root/name).exists():(root/name).unlink()
   subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  raise
