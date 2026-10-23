"""Incremental inline manager release, authorized desktop coin capability only."""
import fcntl,hashlib,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
stage=Path(sys.argv[1]);sha=sys.argv[2];current=Path('/opt/funding-radar-web/current');webpush=Path('/opt/radar-webpush-test');publisher=Path('/opt/robot-push');state=Path('/var/lib/radar-webpush-test');fallback=webpush/'public/index.html'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def settings():
 d=json.loads((state/'desktop-rules.json').read_text());out={'desktop':{k:d.get(k) for k in ('desktop','cards','revision','coinOperations')}}
 for p in [state/'state.json',*sorted((state/'profiles').glob('*/state.json'))]:
  d=json.loads(p.read_text());out[str(p)]={k:d.get(k) for k in ('token','subscription','subscriptions')}|{'settings':d.get('live',{}).get('settings'),'revision':d.get('live',{}).get('revision')}
 return out
def health(port,path,key):
 for n in range(40):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=3) as r:assert json.load(r)[key]
   return
  except Exception:
   if n==39:raise
   time.sleep(.25)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);old=current.resolve();assert old.name=='20261023-web-cards-1792759125','Production changed'
 assert digest(publisher/'server.py')=='00b8b6292babe0a61c0cce9920c85a25c85f32985a2efdd677be299ef5f3a7ca'
 assert digest(webpush/'server.py')=='2971b36503d5bd7463ff4579bde6cc7aca186abc405b89009e76a7f42dc4d1c9'
 assert not (publisher/'coin_control.py').exists() and not (webpush/'coin_control.py').exists()
 public=Path('/tmp/radar-existing-desktop-public.pem');der=subprocess.check_output(['openssl','pkey','-pubin','-in',str(public),'-outform','DER']);kid=hashlib.sha256(der).hexdigest()[:16]
 registered=Path('/etc/robot-push')/('desktop-reader-'+kid+'.pem');assert registered.is_file()
 assert subprocess.check_output(['openssl','pkey','-pubin','-in',str(registered),'-outform','DER'])==der,'Installed desktop identity changed'
 capability=registered.with_name('desktop-coin-manager-'+kid+'.enabled');assert not capability.exists(),'Manager capability already exists'
 oldbundle='performance-20261017/bot-cards-6fdb44e5a08f.js';assert digest(old/oldbundle)=='6fdb44e5a08ff044f853f108916bf582e553eec283f7fdac9dfef7d242927cb5'
 text=(old/oldbundle).read_text();assert text.count('card-policy.js?v=20261023-cards2')==1
 raw=text.replace('card-policy.js?v=20261023-cards2','card-policy.js?v=20261023-inline1').encode();bundle='performance-20261017/bot-cards-'+hashlib.sha256(raw).hexdigest()[:12]+'.js'
 marker='/radar/'+oldbundle;oldindex=(old/'robot-push/index.html').read_text();oldfallback=fallback.read_bytes();assert oldindex.count(marker)==oldfallback.decode().count(marker)==1
 assets=['robot-push/'+n for n in ('card-policy.js','card-policy.css','card-manager.js')]
 release='20261023-inline-cards-'+str(int(time.time()));new=old.parent/release;backup=Path('/opt/funding-radar-web/backups')/release;backup.mkdir(mode=0o700)
 preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in set(assets)|{'robot-push/index.html','settings-preview-source.json'}}
 shutil.copytree(old,new,symlinks=True)
 for name in assets:shutil.copyfile(stage/name,new/name)
 (new/bundle).write_bytes(raw);(new/'robot-push/index.html').write_text(oldindex.replace(marker,'/radar/'+bundle))
 manifest=json.loads((new/'settings-preview-source.json').read_text());manifest.update(source_sha=sha,mode='inline-card-management');manifest['assets'].update({n:digest(new/n) for n in [*assets,bundle,'robot-push/index.html']});manifest['backend'].update({n:digest(stage/'push'/n) for n in ('server.py','coin_control.py')});manifest['publisher']={n:digest(stage/'publisher'/n) for n in ('server.py','coin_control.py')};(new/'settings-preview-source.json').write_text(json.dumps(manifest,indent=2))
 assert all(digest(new/p)==h for p,h in preserved.items())
 shutil.copyfile(webpush/'server.py',backup/'push-server.py');shutil.copyfile(publisher/'server.py',backup/'publisher-server.py');(backup/'pwa-index.html').write_bytes(oldfallback)
 subprocess.run(['systemctl','stop','robot-push','radar-webpush-test'],check=True);before=settings()
 try:
  for folder,target in [('push',webpush),('publisher',publisher)]:
   for name in ('server.py','coin_control.py'):
    temp=target/(name+'.next');shutil.copyfile(stage/folder/name,temp);temp.chmod(0o644);os.replace(temp,target/name)
  capability.write_text('Coin rules management for this explicitly authorized desktop only.\n');capability.chmod(0o640);shutil.chown(capability,user='root',group='robot-push')
  subprocess.run(['systemctl','start','radar-webpush-test'],check=True);health(18885,'/radar/push-test/api/health','ok')
  subprocess.run(['systemctl','start','robot-push'],check=True);health(18883,'/health','ready')
  assert settings()==before,'Existing rules or bindings changed'
  link=current.with_name('current.inline-cards-next');link.symlink_to(new);os.replace(link,current)
  temp=fallback.with_suffix('.next');temp.write_text(oldfallback.decode().replace(marker,'/radar/'+bundle));temp.chmod(0o644);os.replace(temp,fallback)
  result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),bundle=bundle,preservedFiles=len(preserved),rulesPreserved=True,bindingsPreserved=True,desktopCoinManagerEnabled=True,otherReaderPermissionsUnchanged=True);(backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 except Exception:
  if current.resolve()==new:
   link=current.with_name('current.inline-cards-rollback');link.symlink_to(old);os.replace(link,current)
  fallback.write_bytes(oldfallback);subprocess.run(['systemctl','stop','robot-push','radar-webpush-test'],check=True)
  shutil.copyfile(backup/'push-server.py',webpush/'server.py');shutil.copyfile(backup/'publisher-server.py',publisher/'server.py')
  (webpush/'coin_control.py').unlink(missing_ok=True);(publisher/'coin_control.py').unlink(missing_ok=True);capability.unlink(missing_ok=True)
  subprocess.run(['systemctl','start','radar-webpush-test','robot-push'],check=True);raise
