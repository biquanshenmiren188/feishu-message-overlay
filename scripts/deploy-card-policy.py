"""Incremental BOT + PWA card policy release. Never rewrites user settings."""
import fcntl,hashlib,importlib.util,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2];current=Path('/opt/funding-radar-web/current');backend=Path('/opt/radar-webpush-test');state=Path('/var/lib/radar-webpush-test')
expected={'desktop_rules.py':'51e8a525f0ac5c3128b158c1e8ea815371022ff0422f523bcfa73e7c8d5c31e2','server.py':'8ce16a0dfa919ad96352eabc4a5d8ff871f00603e3f573058a59affaf9d72dc3'}
assets=['robot-push/card-policy.js','robot-push/card-policy.css']+['robot-push/settings/'+n for n in ('app.js','index.html','coin-center.js')]
old_bundle='performance-20261017/bot-summary-874b3c8416fa-aster-gc-2060b9cc9d.js'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pid():return subprocess.check_output(['systemctl','show','robot-push','--property=MainPID'],text=True)
def settings():
 d=json.loads((state/'desktop-rules.json').read_text());result={'desktop':{k:d.get(k) for k in ('desktop','cards','revision','coinOperations')}}
 for p in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
  d=json.loads(p.read_text());result[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
 return result
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
 assert old.name=='20261023-coin-center-1792733121','Production changed'
 assert all(digest(backend/n)==v for n,v in expected.items()),'Backend changed'
 spec=importlib.util.spec_from_file_location('patcher',stage/'build-card-policy.py');patcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(patcher)
 raw=patcher.patch_bundle((old/old_bundle).read_bytes());bundle='performance-20261017/bot-cards-'+hashlib.sha256(raw).hexdigest()[:12]+'.js'
 fallback=backend/'public/index.html';old_fallback=fallback.read_bytes();old_index=(old/'robot-push/index.html').read_text()
 marker='/radar/'+old_bundle
 assert old_index.count(marker)==1 and old_fallback.decode().count(marker)==1,'BOT/PWA entry changed'
 release='20261023-web-cards-'+str(int(time.time()));new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
 excluded=set(assets)|{'robot-push/index.html','settings-preview-source.json'}
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True)
 for name in assets:shutil.copyfile(stage/name,new/name)
 (new/bundle).write_bytes(raw);(new/'robot-push/index.html').write_text(old_index.replace(marker,'/radar/'+bundle))
 changed=[*assets,bundle,'robot-push/index.html']
 (new/'settings-preview-source.json').write_text(json.dumps(dict(source_sha=sha,mode='shared-web-card-policies',previous_source='b9ec55482c1e27670433b7d8fccc0c91360533f0',assets={n:digest(new/n) for n in changed},backend={n:digest(stage/n) for n in expected}),indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items())
 publisher=pid();(backup/'pwa-index.html').write_bytes(old_fallback)
 for name in expected:shutil.copyfile(backend/name,backup/name)
 subprocess.run(['systemctl','stop','radar-webpush-test'],check=True);before=settings()
 try:
  for name in expected:
   temp=backend/(name+'.next');shutil.copyfile(stage/name,temp);temp.chmod(0o644);os.replace(temp,backend/name)
  subprocess.run(['systemctl','start','radar-webpush-test'],check=True);health()
  assert settings()==before,'Existing settings changed'
  assert pid()==publisher,'Publisher unexpectedly restarted'
  link=current.with_name('current.web-cards-next');link.symlink_to(new);os.replace(link,current)
  temp=fallback.with_suffix('.next');temp.write_text(old_fallback.decode().replace(marker,'/radar/'+bundle));temp.chmod(0o644);os.replace(temp,fallback)
  result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),bundle=bundle,preservedFiles=len(preserved),existingRulesPreserved=True,mobileBindingsPreserved=True,publisherUnchanged=True,desktopRestarted=False)
  (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 except Exception:
  if current.resolve()==new:
   link=current.with_name('current.web-cards-rollback');link.symlink_to(old);os.replace(link,current)
  fallback.write_bytes(old_fallback)
  subprocess.run(['systemctl','stop','radar-webpush-test'],check=True)
  for name in expected:shutil.copyfile(backup/name,backend/name)
  subprocess.run(['systemctl','start','radar-webpush-test'],check=True);raise
