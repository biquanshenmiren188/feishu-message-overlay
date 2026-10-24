"""UI-only parent coin menu release. Preserves policy and every unrelated asset."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2];current=Path('/opt/funding-radar-web/current')
assets=['robot-push/settings/'+n for n in ('app.js','index.html','style.css','coin-list.js')]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def settings():
 state=Path('/var/lib/radar-webpush-test');d=json.loads((state/'desktop-rules.json').read_text())
 result={'desktop':{k:d.get(k) for k in ('desktop','cards','revision','coinOperations')}}
 for p in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
  d=json.loads(p.read_text());result[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
 return result
def pids():return subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','--property=MainPID'],text=True)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);old=current.resolve()
 assert old.name=='20261023-coin-list-1792729410','Production baseline changed'
 before=settings();services=pids()
 release='20261023-coin-navigation-'+str(int(time.time()));new=old.parent/release
 excluded=set(assets)|{'settings-preview-source.json'}
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True)
 for name in assets:shutil.copyfile(stage/name,new/name)
 (new/'settings-preview-source.json').write_text(json.dumps(dict(source_sha=sha,mode='parent-coin-menu',assets={n:digest(new/n) for n in assets}),indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items())
 assert settings()==before,'Settings changed during preparation; abort without swapping'
 assert pids()==services,'Service process changed'
 link=current.with_name('current.coin-navigation-next');link.symlink_to(new);os.replace(link,current)
 try:
  assert settings()==before,'Settings changed during release'
  assert pids()==services
 except Exception:
  link=current.with_name('current.coin-navigation-rollback');link.symlink_to(old);os.replace(link,current);raise
 result=dict(source_sha=sha,release=str(new),previous=str(old),preservedFiles=len(preserved),existingRulesPreserved=True,mobileBindingsPreserved=True,servicesUnchanged=True,desktopRestarted=False)
 (new/'coin-navigation-release.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
