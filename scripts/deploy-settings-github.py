"""Settings software repository link; static-only deployment."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2];current=Path('/opt/funding-radar-web/current');fallback=Path('/opt/radar-webpush-test/public/index.html')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def settings():
 state=Path('/var/lib/radar-webpush-test');d=json.loads((state/'desktop-rules.json').read_text());out={'desktop':{k:d.get(k) for k in ('desktop','cards','revision','coinOperations')}}
 for p in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
  d=json.loads(p.read_text());out[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
 return out
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);old=current.resolve();assert old.name=='20261024-card-access-1792771871','Production changed'
 assets=['robot-push/settings/index.html','robot-push/settings/style.css'];manifest=json.loads((old/'settings-preview-source.json').read_text())
 assert all(digest(old/p)==manifest['assets'][p] for p in assets),'Settings assets changed'
 before=settings();services=subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','--property=MainPID'])
 name='20261024-settings-github-'+str(int(time.time()));new=old.parent/name
 excluded={*assets,'settings-preview-source.json'};preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True)
 for asset in assets:shutil.copyfile(stage/asset,new/asset)
 manifest['source_sha']=sha;manifest['assets'].update({p:digest(new/p) for p in assets});(new/'settings-preview-source.json').write_text(json.dumps(manifest,indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items());assert settings()==before
 try:
  link=current.with_name('current.settings-github-next');link.symlink_to(new);os.replace(link,current)
  assert Path('/opt/radar-webpush-test/public/settings').resolve()==new/'robot-push/settings','PWA settings not following current'
  assert settings()==before;assert subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','--property=MainPID'])==services
 except Exception:
  link=current.with_name('current.settings-github-rollback');link.symlink_to(old);os.replace(link,current);raise
 print(json.dumps(dict(source_sha=sha,release=str(new),previous=str(old),preservedFiles=len(preserved),rulesPreserved=True,bindingsPreserved=True,servicesUnchanged=True,pwaSettingsMatches=True)))
