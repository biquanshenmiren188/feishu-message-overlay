"""Guarded static BOT/PWA release. Default --check never switches production.

Usage on host: python3 deploy-mobile-reading.py STAGE FULL_SOURCE_SHA [--check|--apply]
No service restart, notification, API, identity or settings writes are performed.
"""
import fcntl,hashlib,json,os,pathlib,re,shutil,stat,subprocess,sys,time

ROOT=pathlib.Path('/opt/funding-radar-web');CURRENT=ROOT/'current'
PUBLIC=pathlib.Path('/opt/radar-webpush-test/public');FALLBACK=PUBLIC/'index.html'
DYNAMIC='market-display-cache.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def safe(name):
 assert isinstance(name,str) and name and '\\' not in name and '\x00' not in name
 p=pathlib.PurePosixPath(name);assert not p.is_absolute() and all(part not in ('','.','..') for part in name.split('/'))
 return name
def regular(root,name):
 target=root;assert not root.is_symlink()
 for part in pathlib.PurePosixPath(safe(name)).parts:target=target/part;assert not target.is_symlink()
 assert target.is_file();return target
def scan(root):
 files,links={},{}
 def walk(folder,prefix=''):
  for entry in os.scandir(folder):
   name=prefix+entry.name
   if entry.is_symlink():links[name]=os.readlink(entry.path)
   elif entry.is_dir(follow_symlinks=False):walk(entry.path,name+'/')
   elif entry.is_file(follow_symlinks=False):files[name]=dict(sha256=sha(pathlib.Path(entry.path).read_bytes()),bytes=entry.stat().st_size)
   else:raise ValueError('Unexpected release entry: '+name)
 walk(root);return dict(files=files,symlinks=links)
def unchanged(now,before):
 return now['symlinks']==before['symlinks'] and set(now['files'])==set(before['files']) and all(n==DYNAMIC or now['files'][n]==item for n,item in before['files'].items())
def services():
 units=subprocess.check_output(['systemctl','list-units','--type=service','--state=running','--no-legend','--plain'],text=True)
 names=sorted(line.split()[0] for line in units.splitlines() if line.strip())
 return subprocess.check_output(['systemctl','show',*names,'--property=Id,MainPID,ActiveState'],text=True)
def containers():
 result={}
 for ident in subprocess.check_output(['docker','ps','-q'],text=True).split():
  c=json.loads(subprocess.check_output(['docker','inspect',ident],text=True))[0]
  result[c['Name']]={'id':c['Id'],'pid':c['State']['Pid'],'startedAt':c['State']['StartedAt']}
 return result
def switch(target):
 temp=CURRENT.with_name('current.mobile-reading-next');assert not temp.exists() and not temp.is_symlink()
 temp.symlink_to(target);os.replace(temp,CURRENT)
def atomic_fallback(body,original_stat,label):
 assert FALLBACK.is_file() and not FALLBACK.is_symlink() and not PUBLIC.is_symlink()
 temp=FALLBACK.with_name('.index.html.'+label)
 with open(temp,'xb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
 temp.chmod(stat.S_IMODE(original_stat.st_mode));os.chown(temp,original_stat.st_uid,original_stat.st_gid)
 assert sha(temp.read_bytes())==sha(body);os.replace(temp,FALLBACK)
def main():
 stage=pathlib.Path(sys.argv[1]).resolve();commit=sys.argv[2];mode=sys.argv[3] if len(sys.argv)>3 else '--check'
 assert mode in ('--check','--apply') and re.fullmatch('[0-9a-f]{40}',commit)
 plan=json.loads(regular(stage,'manifest.json').read_bytes());base_raw=regular(stage,'baseline.json').read_bytes();base=json.loads(base_raw)
 inventory_raw=regular(stage,'all-files.json').read_bytes();inventory=json.loads(inventory_raw)
 assert plan['schema']==1 and plan['kind']=='mobile-reading-static' and plan['sourceCommit']==commit and plan['sourceCommitted'] is True
 assert plan['baselineHash']==sha(base_raw) and plan['inventoryHash']==sha(inventory_raw)==base['inventory']['sha256'] and plan['sourceRelease']==base['release']
 assert re.fullmatch(r'performance-20261017/bot-reading-[0-9a-f]{16}\.js',plan['bundle'])
 assert re.fullmatch(r'mobile-reading-20261101/mobile-scroll-[0-9a-f]{16}\.js',plan['module'])
 assert set(plan['files'])=={plan['bundle'],plan['module'],'robot-push/index.html','pwa-index.html'}
 payloads={}
 for name,item in plan['files'].items():
  payloads[name]=regular(stage,name).read_bytes();assert sha(payloads[name])==item['sha256'] and len(payloads[name])==item['bytes'],name
 assert sha(pathlib.Path(__file__).read_bytes().replace(b'\r\n',b'\n'))==plan['sourceFiles']['scripts/deploy-mobile-reading.py']
 validation=json.loads(regular(stage,'validation.json').read_bytes())
 assert validation['passed'] is True and validation['sourceCommit']==commit and validation['files']==plan['files'] and validation['baselineHash']==plan['baselineHash']
 with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);old=CURRENT.resolve(strict=True)
  assert CURRENT.is_symlink() and old.parent==ROOT/'releases' and str(old)==plan['sourceRelease'],'Reinspect changed production release'
  before=scan(old);assert unchanged(before,inventory),'Full production inventory changed'
  assert FALLBACK.is_file() and not FALLBACK.is_symlink() and not PUBLIC.is_symlink()
  previous=FALLBACK.read_bytes();fallback_stat=FALLBACK.stat();assert sha(previous)==base['fallback']['sha256'],'PWA fallback changed'
  for name,item in base['files'].items():
   p=pathlib.Path(item['path'])
   if p.is_relative_to(old):target=regular(old,p.relative_to(old).as_posix())
   else:assert p.is_relative_to(PUBLIC);target=regular(PUBLIC,p.relative_to(PUBLIC).as_posix())
   assert sha(target.read_bytes())==item['sha256'],name
  pids=services();running=containers()
  if mode=='--check':
   print(json.dumps(dict(preflight=True,release=str(old),files=len(plan['files']),preservedFiles=len(before['files'])-1,fallbackHash=sha(previous),servicesHash=sha(pids.encode()),containers=running)));return
  name='20261101-mobile-reading-'+str(time.time_ns());new=ROOT/'releases'/name;backup=ROOT/'backups'/name;backup.mkdir(mode=0o700)
  (backup/'previous-target.txt').write_text(str(old));(backup/'pwa-index.html').write_bytes(previous)
  for record in ['manifest.json','baseline.json','all-files.json','validation.json']:(backup/record).write_bytes(regular(stage,record).read_bytes())
  shutil.copytree(old,new,symlinks=True)
  assets=[n for n in plan['files'] if n!='pwa-index.html']
  for n in assets:
   target=new/safe(n);target.parent.mkdir(parents=True,exist_ok=True)
   assert all(not p.is_symlink() for p in (target,*target.parents))
   assert n=='robot-push/index.html' or not target.exists(),'Never overwrite an independently deployed module'
   target.write_bytes(payloads[n]);target.chmod(0o644)
  copied=scan(new);assert copied['symlinks']==before['symlinks'] and set(copied['files'])==set(before['files'])|set(assets)
  assert all(n==DYNAMIC or copied['files'][n]==item for n,item in before['files'].items() if n not in assets)
  assert all(copied['files'][n]==plan['files'][n] for n in assets)
  assert CURRENT.resolve()==old and unchanged(scan(old),before) and FALLBACK.read_bytes()==previous
  assert services()==pids and containers()==running
  try:
   switch(new);assert CURRENT.resolve(strict=True)==new
   assert FALLBACK.read_bytes()==previous,'Concurrent PWA write before switch'
   atomic_fallback(payloads['pwa-index.html'],fallback_stat,backup.name+'-next')
   assert services()==pids and containers()==running,'Unrelated process changed'
   assert unchanged(scan(new),copied)
   assert all(sha(regular(new,n).read_bytes())==plan['files'][n]['sha256'] for n in assets)
   assert sha(FALLBACK.read_bytes())==plan['files']['pwa-index.html']['sha256']
   assert CURRENT.resolve(strict=True)==new,'Concurrent release changed final target'
   report=dict(sourceCommit=commit,release=str(new),previous=str(old),backup=str(backup),bundle=plan['bundle'],module=plan['module'],hashes={n:item['sha256'] for n,item in plan['files'].items()},preservedFiles=len(before['files'])-1,servicesUnchanged=True,containersUnchanged=True,desktopRestarted=False,fallbackHash=sha(FALLBACK.read_bytes()))
   (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
  except BaseException:
   actual=CURRENT.resolve(strict=True);assert actual in (old,new),'Concurrent release prevents rollback'
   fallback_now=sha(FALLBACK.read_bytes());assert fallback_now in (sha(previous),plan['files']['pwa-index.html']['sha256']),'Concurrent PWA update prevents rollback'
   if actual==new:switch(old);assert CURRENT.resolve(strict=True)==old
   if fallback_now!=sha(previous):atomic_fallback(previous,fallback_stat,backup.name+'-rollback')
   assert FALLBACK.read_bytes()==previous,'PWA rollback verification failed'
   raise
if __name__=='__main__':main()
