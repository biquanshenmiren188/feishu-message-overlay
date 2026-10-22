"""Guarded incremental web + signed desktop policy release; no test notifications."""
import fcntl,hashlib,json,os,re,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(sys.argv[1]).resolve();sha=sys.argv[2]
web_only='--web-only' in sys.argv[3:]
assert stage.parent==Path('/tmp') and stage.name.startswith('radar-desktop-rules-') and re.fullmatch('[a-f0-9]{40}',sha)
manifest=json.loads((stage/'manifest.json').read_text());current=Path('/opt/funding-radar-web/current');phone=Path('/opt/radar-webpush-test');publisher=Path('/opt/robot-push')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True)
def identity():
 base=Path('/var/lib/radar-webpush-test');out={}
 for p in [base/'state.json',*sorted((base/'profiles').glob('*/state.json'))]:
  d=json.loads(p.read_text());out[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
 return out
def get(path,token=None):
 req=urllib.request.Request('http://127.0.0.1:18885'+path,headers={'Authorization':'Bearer '+token} if token else {})
 with urllib.request.urlopen(req,timeout=12) as response:return json.load(response)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);old=current.resolve();before=identity()
 for path,h in manifest['baseline'].items():assert digest(Path(path))==h,'Changed production baseline: '+path
 for path,h in manifest['assets'].items():assert digest(stage/'files'/path)==h
 backend={phone/'server.py':'web/push-test/server.py',phone/'desktop_rules.py':'web/push-test/desktop_rules.py',publisher/'server.py':'web/robot-push/publisher/server.py',publisher/'state_delta.py':'web/robot-push/publisher/state_delta.py'}
 if web_only:backend={}
 candidate=stage/'candidate';candidate.mkdir()
 for p in phone.glob('*.py'):shutil.copyfile(p,candidate/p.name)
 for name in ('server.py','desktop_rules.py','desktop_rules_test.py','advanced_rules_test.py'):shutil.copyfile(stage/'files/web/push-test'/name,candidate/name)
 tests=run(str(phone/'venv/bin/python'),'-m','unittest','discover','-s',str(candidate),'-p','*_test.py');print(tests.stderr.strip(),flush=True)
 # Isolated real-data parsing: no writes to live rules or phone state.
 sys.path.insert(0,str(candidate));from desktop_rules import DesktopRules
 engine=DesktopRules(candidate);decisions=engine.evaluate();assert decisions['messages']=={} and decisions['cards']=={}
 assert not engine.path.exists()
 release='20261022-desktop-rules-'+str(int(time.time()));new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
 for dest,src in backend.items():
  if dest.exists():shutil.copyfile(dest,backup/(('publisher-' if dest.parent==publisher else 'phone-')+dest.name))
 fallback=phone/'public/index.html';fallback_before=fallback.read_bytes();(backup/'fallback.html').write_bytes(fallback_before);(backup/'previous-release.txt').write_text(str(old))
 pwa={p.name:digest(p) for p in (phone/'public').iterdir() if p.is_file() and p.name!='index.html'}
 excluded={'robot-push/index.html','robot-push/notification-settings.js','settings-preview-source.json'}
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and not str(p.relative_to(old)).startswith('robot-push/settings/') and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True)
 for name in ('index.html','app.js','rules.js','style.css'):shutil.copyfile(stage/'files/web/robot-push/settings'/name,new/'robot-push/settings'/name)
 shutil.copyfile(stage/'files/web/robot-push/notification-settings.js',new/'robot-push/notification-settings.js')
 def version(raw):
  text,n=re.subn(r'notification-settings\.js\?v=[^"\s]+','notification-settings.js?v=20261022-desktop1',raw.decode());assert n==1;return text.encode()
 (new/'robot-push/index.html').write_bytes(version((old/'robot-push/index.html').read_bytes()))
 source=dict(source_sha=sha,repository='biquanshenmiren188/feishu-message-overlay',mode='integrated-desktop-mobile',assets={n:digest(new/'robot-push/settings'/n) for n in ('index.html','app.js','rules.js','style.css')})
 (new/'settings-preview-source.json').write_text(json.dumps(source,indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items());assert identity()==before
 changed=False
 try:
  for dest,src in backend.items():
   temp=dest.with_suffix('.next');shutil.copyfile(stage/'files'/src,temp);temp.chmod(0o644);os.replace(temp,dest)
  changed=bool(backend)
  if changed:run('systemctl','restart','radar-webpush-test')
  for attempt in range(30):
   try:get('/radar/push-test/api/health');break
   except Exception:
    if attempt==29:raise
    time.sleep(.25)
  result=get('/internal/desktop-state');assert result['revision']==0 or isinstance(result['revision'],int)
  # Existing identity authenticates; independent mobile profiles cannot edit desktop.
  for path,data in before.items():
   status=get('/radar/push-test/api/status',data['token']);assert status['settings']==data['settings']
   if Path(path).parent==Path('/var/lib/radar-webpush-test'):assert 'desktop' in get('/radar/push-test/api/desktop-settings',data['token'])
   else:
    try:get('/radar/push-test/api/desktop-settings',data['token']);raise AssertionError('Non-owner desktop access')
    except urllib.error.HTTPError as error:assert error.code==403
  if changed:run('systemctl','restart','robot-push')
  run('systemctl','is-active','robot-push','radar-webpush-test')
  assert identity()==before
  temp=fallback.with_suffix('.next');temp.write_bytes(version(fallback_before));temp.chmod(0o644);os.replace(temp,fallback)
  link=current.with_name('current.desktop-next');link.symlink_to(new);os.replace(link,current)
  assert all(digest(current/p)==h for p,h in preserved.items());assert all(digest(phone/'public'/p)==h for p,h in pwa.items())
  result=dict(release=str(new),previous=str(old),backup=str(backup),source_sha=sha,preserved_files=len(preserved),mobile_settings_bindings_preserved=True,pwa_preserved=True,services_active=True,tests=tests.stderr.strip())
  (backup/'result.json').write_text(json.dumps(result));print(json.dumps(result),flush=True)
 except Exception:
  if current.resolve()==new:
   link=current.with_name('current.desktop-rollback');link.symlink_to(old);os.replace(link,current)
  fallback.write_bytes(fallback_before)
  if changed:
   for dest in backend:
    saved=backup/(('publisher-' if dest.parent==publisher else 'phone-')+dest.name)
    if saved.exists():shutil.copyfile(saved,dest)
   run('systemctl','restart','radar-webpush-test','robot-push')
  raise
