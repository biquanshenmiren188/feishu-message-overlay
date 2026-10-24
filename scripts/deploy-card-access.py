"""Static-only card access and manual rule recovery; no user-state writes."""
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
 fcntl.flock(lock,fcntl.LOCK_EX);old=current.resolve();assert old.name=='20261023-inline-cards-1792760774'
 source=old/'performance-20261017/bot-cards-363a2757cd74.js';assert digest(source).startswith('363a2757cd74')
 text=source.read_text();assert text.count('card-policy.js?v=20261023-inline1')==1
 raw=text.replace('card-policy.js?v=20261023-inline1','card-policy.js?v=20261024-access1').encode();bundle='performance-20261017/bot-cards-'+hashlib.sha256(raw).hexdigest()[:12]+'.js'
 oldref='/radar/'+str(source.relative_to(old));oldfallback=fallback.read_bytes();oldindex=(old/'robot-push/index.html').read_text();assert oldindex.count(oldref)==oldfallback.decode().count(oldref)==1
 before=settings();services=subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','--property=MainPID'])
 name='20261024-card-access-'+str(int(time.time()));new=old.parent/name;backup=Path('/opt/funding-radar-web/backups')/name;backup.mkdir(mode=0o700);(backup/'pwa-index.html').write_bytes(oldfallback)
 assets=['robot-push/card-policy.js','robot-push/notification-settings.js',*['robot-push/settings/'+p for p in ('app.js','rules.js','index.html','style.css')]];excluded={'robot-push/index.html','settings-preview-source.json',*assets};preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in excluded}
 shutil.copytree(old,new,symlinks=True);(new/bundle).write_bytes(raw);
 for asset in assets:shutil.copyfile(stage/asset,new/asset)
 (new/'robot-push/index.html').write_text(oldindex.replace(oldref,'/radar/'+bundle))
 manifest=json.loads((new/'settings-preview-source.json').read_text());manifest['source_sha']=sha;manifest['assets'].update({n:digest(new/n) for n in [*assets,'robot-push/index.html',bundle]});(new/'settings-preview-source.json').write_text(json.dumps(manifest,indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items());assert settings()==before
 try:
  link=current.with_name('current.card-empty-next');link.symlink_to(new);os.replace(link,current)
  temp=fallback.with_suffix('.next');temp.write_text(oldfallback.decode().replace(oldref,'/radar/'+bundle));temp.chmod(0o644);os.replace(temp,fallback)
  assert settings()==before;assert subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','--property=MainPID'])==services
 except Exception:
  link=current.with_name('current.card-empty-rollback');link.symlink_to(old);os.replace(link,current);fallback.write_bytes(oldfallback);raise
 result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),bundle=bundle,preservedFiles=len(preserved),rulesPreserved=True,bindingsPreserved=True,servicesUnchanged=True);(backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
