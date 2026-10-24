"""Guarded incremental coin administration release; no user rule mutations."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2];current=Path('/opt/funding-radar-web/current')
backend=Path('/opt/radar-webpush-test');state=Path('/var/lib/radar-webpush-test')
expected={'desktop_rules.py':'b4606cb713befdd94b40016c9ab0b92bbbe5a83abdf9e5d064b6d9f30aebbfd6','server.py':'2be3947f7f1f62d0d390c8dbb6956064203312bbb3d4a2608ae5dbaee0acc66c'}
new_backend=['coin_edits.py']
assets=['robot-push/settings/'+n for n in ('app.js','index.html','style.css','coin-list.js','coin-center.js')]+['robot-push/notification-settings.js']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pid():return subprocess.check_output(['systemctl','show','robot-push','--property=MainPID'],text=True)
def mobile():
 out={}
 for p in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
  d=json.loads(p.read_text());out[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
 return out
def policy():
 d=json.loads((state/'desktop-rules.json').read_text());return {k:d.get(k) for k in ('desktop','cards','revision','coinOperations')}
def health():
 for attempt in range(40):
  try:
   with urllib.request.urlopen('http://127.0.0.1:18885/radar/push-test/api/health',timeout=3) as r:assert json.load(r)['ok']
   return
  except Exception:
   if attempt==39:raise
   time.sleep(.25)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);old=current.resolve()
 assert old.name=='20261023-coin-navigation-1792731114','Production baseline changed'
 assert all(digest(backend/n)==v for n,v in expected.items()),'Backend baseline changed'
 assert all(not (backend/n).exists() for n in new_backend),'New module already exists'
 assert digest(old/'robot-push/notification-settings.js')=='c222a1a406231d178933440ce2ecc7695235557bf58065afae4b9108a4e021f6','Notification baseline changed'
 release='20261023-coin-center-'+str(int(time.time()));new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
 excluded=set(assets)|{'settings-preview-source.json'}
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True)
 for name in assets:shutil.copyfile(stage/name,new/name)
 (new/'settings-preview-source.json').write_text(json.dumps(dict(source_sha=sha,mode='coin-administration',assets={n:digest(new/n) for n in assets},backend={n:digest(stage/n) for n in [*expected,*new_backend]}),indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items())
 publisher=pid()
 for name in expected:shutil.copyfile(backend/name,backup/name)
 subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
 before_mobile=mobile();before_policy=policy()
 try:
  for name in [*expected,*new_backend]:
   temp=backend/(name+'.next');shutil.copyfile(stage/name,temp);temp.chmod(0o644);os.replace(temp,backend/name)
  subprocess.run(['systemctl','start','radar-webpush-test'],check=True);health()
  assert mobile()==before_mobile and policy()==before_policy,'Existing settings changed'
  assert pid()==publisher,'Publisher restarted unexpectedly'
  link=current.with_name('current.coin-center-next');link.symlink_to(new);os.replace(link,current)
  result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),preservedFiles=len(preserved),existingRulesPreserved=True,mobileBindingsPreserved=True,publisherUnchanged=True,desktopRestarted=False)
  (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 except Exception:
  if current.resolve()==new:
   link=current.with_name('current.coin-center-rollback');link.symlink_to(old);os.replace(link,current)
  subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
  for name in expected:shutil.copyfile(backup/name,backend/name)
  for name in new_backend:(backend/name).unlink(missing_ok=True)
  subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  raise
