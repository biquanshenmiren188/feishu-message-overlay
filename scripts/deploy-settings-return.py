"""Incremental startup-shell layout repair. Default --check does not publish.

On host: python3 deploy-settings-return.py STAGE SOURCE_SHA [--check|--apply]
Requires validation.json for these exact candidate bytes. No service restarts.
"""
import fcntl,hashlib,json,os,pathlib,re,shutil,subprocess,sys,time

ROOT=pathlib.Path('/opt/funding-radar-web');CURRENT=ROOT/'current'
FALLBACK=pathlib.Path('/opt/radar-webpush-test/public/index.html')
DYNAMIC='market-display-cache.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def safe(name):
 assert isinstance(name,str) and name and '\\' not in name and '\x00' not in name
 p=pathlib.PurePosixPath(name);assert not p.is_absolute() and all(x not in ('','.','..') for x in name.split('/'))
 return name
def regular(root,name):
 cursor=root;assert not root.is_symlink()
 for part in pathlib.PurePosixPath(safe(name)).parts:cursor=cursor/part;assert not cursor.is_symlink()
 assert cursor.is_file();return cursor
def scan(root):
 files,links={},{}
 def walk(folder,prefix=''):
  for entry in os.scandir(folder):
   name=prefix+entry.name
   if entry.is_symlink():links[name]=os.readlink(entry.path)
   elif entry.is_dir(follow_symlinks=False):walk(entry.path,name+'/')
   elif entry.is_file(follow_symlinks=False):files[name]=sha(pathlib.Path(entry.path).read_bytes())
   else:raise ValueError('Unexpected entry: '+name)
 walk(root);return files,links
def unchanged(now,before):return set(now)==set(before) and all(n==DYNAMIC or now[n]==h for n,h in before.items())
def services():
 units=subprocess.check_output(['systemctl','list-units','--type=service','--state=running','--no-legend','--plain'],text=True)
 names=sorted(line.split()[0] for line in units.splitlines() if line.strip())
 return subprocess.check_output(['systemctl','show',*names,'--property=Id,MainPID'],text=True)
def containers():
 result={}
 for identity in subprocess.check_output(['docker','ps','-q'],text=True).split():
  item=json.loads(subprocess.check_output(['docker','inspect',identity],text=True))[0]
  result[item['Name']]=(item['Id'],item['State']['Pid'],item['State']['StartedAt'])
 return result
def settings_digest():
 root=pathlib.Path('/var/lib/radar-webpush-test');values={}
 for p in [root/'state.json',*sorted((root/'profiles').glob('*/state.json'))]:
  if p.exists():
   data=json.loads(p.read_text());live=data.get('live',{});values[str(p)]={k:data.get(k) for k in ('token','subscription','subscriptions')};values[str(p)].update(settings=live.get('settings'),revision=live.get('revision'))
 for p in [root/'desktop-rules.json',*sorted((root/'profiles').glob('*/desktop-rules.json'))]:
  if p.exists():
   data=json.loads(p.read_text());values[str(p)]={k:data.get(k) for k in ('desktop','cards','revision','coinOperations')}
 for p in [root/'profiles.json',pathlib.Path('/etc/radar-webpush-test/config.json')]:
  if p.exists():values[str(p)]=sha(p.read_bytes())
 return sha(json.dumps(values,sort_keys=True).encode())
def switch(target):
 temp=CURRENT.with_name('current.settings-return-next');assert not temp.exists() and not temp.is_symlink();temp.symlink_to(target);os.replace(temp,CURRENT)
def main():
 stage=pathlib.Path(sys.argv[1]).resolve();commit=sys.argv[2];mode=sys.argv[3] if len(sys.argv)>3 else '--check'
 assert mode in ('--check','--apply') and re.fullmatch('[0-9a-f]{40}',commit)
 plan=json.loads(regular(stage,'manifest.json').read_bytes());baseline_raw=regular(stage,'baseline.json').read_bytes();baseline=json.loads(baseline_raw)
 assert plan['schema']==1 and plan['sourceCommit']==commit and plan['sourceCommitted'] is True
 assert plan['baselineHash']==sha(baseline_raw) and plan['sourceRelease']==baseline['release']
 assert re.fullmatch('assets/settings-return-[0-9a-f]{16}',plan['prefix']) and 'robot-push/settings/index.html' in plan['files']
 payloads={}
 for name,item in plan['files'].items():
  assert name=='robot-push/settings/index.html'
  payloads[name]=regular(stage,name).read_bytes();assert sha(payloads[name])==item['sha256'] and len(payloads[name])==item['bytes'],name
 assert sha(pathlib.Path(__file__).read_bytes().replace(b'\r\n',b'\n'))==plan['sourceFiles']['scripts/deploy-settings-return.py']
 validation=json.loads(regular(stage,'validation.json').read_bytes())
 assert validation['passed'] is True and validation['files']==plan['files']
 with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);old=CURRENT.resolve(strict=True)
  assert CURRENT.is_symlink() and old.parent==ROOT/'releases' and str(old)==plan['sourceRelease'],'Inspect concurrent release'
  for name,item in baseline['files'].items():assert sha(regular(old,name).read_bytes())==item['sha256'],'Production changed: '+name
  before,links=scan(old);pids=services();running=containers();settings=settings_digest();fallback=sha(FALLBACK.read_bytes())
  if mode=='--check':print(json.dumps(dict(preflight=True,release=str(old),files=len(plan['files']),baselineFiles=len(before))));return
  name='20261106-settings-return-'+str(time.time_ns());new=ROOT/'releases'/name;backup=ROOT/'backups'/name;backup.mkdir(mode=0o700)
  (backup/'previous-target.txt').write_text(str(old));(backup/'manifest.json').write_bytes(regular(stage,'manifest.json').read_bytes())
  (backup/'baseline-inventory.json').write_text(json.dumps(dict(files=before,symlinks=links),sort_keys=True))
  shutil.copytree(old,new,symlinks=True)
  for name in plan['files']:
   target=new/safe(name);target.parent.mkdir(parents=True,exist_ok=True)
   assert all(not p.is_symlink() for p in (target,*target.parents));target.write_bytes(payloads[name]);target.chmod(0o644)
  copied,copied_links=scan(new);assert copied_links==links and set(copied)==set(before)|set(plan['files'])
  assert all(name==DYNAMIC or copied[name]==value for name,value in before.items() if name not in plan['files'])
  assert all(copied[name]==item['sha256'] for name,item in plan['files'].items()),'Copied candidate changed'
  assert CURRENT.resolve()==old and unchanged(scan(old)[0],before) and scan(old)[1]==links
  assert services()==pids and containers()==running and settings_digest()==settings and sha(FALLBACK.read_bytes())==fallback
  try:
   switch(new)
   assert services()==pids and containers()==running and settings_digest()==settings and sha(FALLBACK.read_bytes())==fallback
   after,after_links=scan(new);assert unchanged(after,copied) and after_links==copied_links
   for n,item in plan['files'].items():assert sha(regular(new,n).read_bytes())==item['sha256']
   report=dict(sourceCommit=commit,release=str(new),previous=str(old),backup=str(backup),staticFiles=len(plan['files']),preservedFiles=len(before)-1,servicesUnchanged=True,containersUnchanged=True,rulesAndBindingsPreserved=True,fallbackUnchanged=True,hashes={n:item['sha256'] for n,item in plan['files'].items()})
   (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
  except BaseException:
   # Inspect the actual link, including an exception immediately after rename.
   # Never roll back a release belonging to a concurrent operator.
   target=CURRENT.resolve(strict=True)
   if target==new:
    switch(old);assert CURRENT.resolve(strict=True)==old,'Rollback verification failed'
   else:assert target==old,'Concurrent release prevents rollback'
   raise
if __name__=='__main__':main()
