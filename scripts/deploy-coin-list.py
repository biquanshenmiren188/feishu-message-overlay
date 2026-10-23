"""Guarded incremental coin inventory release; no user rule mutations."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2];current=Path('/opt/funding-radar-web/current')
backend=Path('/opt/radar-webpush-test');state=Path('/var/lib/radar-webpush-test')
expected={'desktop_rules.py':'0fbdb39e682e850c897f2bb433b0fbf348db25906d16c68140f73e821f76345b','server.py':'dcef1f945359e842270b88c52207c5ed849e4d227e9d4ba0ba3e435d6f635545'}
assets=['robot-push/settings/'+n for n in ('app.js','index.html','style.css','coin-list.js')]+['robot-push/notification-settings.js']
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
 assert old.name=='20261023-split-rules-1792726790','Production baseline changed'
 assert all(digest(backend/n)==v for n,v in expected.items()),'Backend baseline changed'
 assert digest(old/'robot-push/notification-settings.js')=='4364326d87fd4b05db0486b71e5288cfa2802cd67e61ae13ed0817a97298cbdb','Notification baseline changed'
 release='20261023-coin-list-'+str(int(time.time()));new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
 excluded=set(assets)|{'settings-preview-source.json'}
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True)
 for name in assets:shutil.copyfile(stage/name,new/name)
 (new/'settings-preview-source.json').write_text(json.dumps(dict(source_sha=sha,mode='saved-coin-inventory',assets={n:digest(new/n) for n in assets}),indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items())
 publisher=pid()
 for name in expected:shutil.copyfile(backend/name,backup/name)
 subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
 before_mobile=mobile();before_policy=policy()
 try:
  for name in expected:
   temp=backend/(name+'.next');shutil.copyfile(stage/name,temp);temp.chmod(0o644);os.replace(temp,backend/name)
  subprocess.run(['systemctl','start','radar-webpush-test'],check=True);health()
  assert mobile()==before_mobile and policy()==before_policy,'Existing settings changed'
  assert pid()==publisher,'Publisher restarted unexpectedly'
  link=current.with_name('current.coin-list-next');link.symlink_to(new);os.replace(link,current)
  result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),preservedFiles=len(preserved),existingRulesPreserved=True,mobileBindingsPreserved=True,publisherUnchanged=True,desktopRestarted=False)
  (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 except Exception:
  if current.resolve()==new:
   link=current.with_name('current.coin-list-rollback');link.symlink_to(old);os.replace(link,current)
  for name in expected:shutil.copyfile(backup/name,backend/name)
  subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  raise
