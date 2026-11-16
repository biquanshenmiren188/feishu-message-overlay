"""Only add credentialed same-origin manifest links to the inspected live HTML."""
import fcntl,importlib.util,json,os,re,shutil,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('bot',Path(__file__).with_name('deploy-bot-entry.py'))
bot=importlib.util.module_from_spec(spec);spec.loader.exec_module(bot);base=bot.base
TARGETS={'robot-push/index.html','push-center/index.html','robot-push/center/index.html','robot-push/alarms/history.html','robot-push/alarms/index.html','robot-push/settings/index.html'}
def patch(raw):
 after,n=re.subn(rb'<link rel="manifest" href="(/radar/push-test/manifest.webmanifest(?:\?v=[a-zA-Z0-9-]+)?)">',rb'<link rel="manifest" href="\1" crossorigin="use-credentials">',raw)
 assert n==1,'Expected exactly one same-origin manifest link'
 return after
def main():
 stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text());assert re.fullmatch(r'[a-f0-9]{40}',m['source'])
 assert set(m['files'])==set(m['before'])==TARGETS
 with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  old=base.CURRENT.resolve();assert str(old)==m['current']
  for n,h in m['files'].items():
   assert not (old/n).is_symlink() and base.sha((old/n).read_bytes())==m['before'][n]
   assert base.sha((stage/'static'/n).read_bytes())==h and patch((old/n).read_bytes())==(stage/'static'/n).read_bytes()
  fallback=base.FALLBACK.read_bytes();assert base.sha(fallback)==m['fallbackBefore'] and patch(fallback)==(stage/'fallback.html').read_bytes()
  public=base.FALLBACK.parent;manifest=base.sha((public/'manifest.webmanifest').read_bytes());worker=base.sha((public/'sw.js').read_bytes())
  assert manifest==m['manifestSha'];base.health()
  if '--apply' not in sys.argv:print('Manifest link preflight passed');return
  files,links=base.inventory(old);backend=Path('/opt/radar-alarms/current').resolve();backend_files=base.inventory(backend)
  config=bot.config();states=base.state_digest();services=bot.pids()
  name='20261114-pwa-manifest-'+str(time.time_ns());new=base.ROOT/'releases'/name;backup=base.ROOT/'backups'/name;backup.mkdir(mode=0o700)
  (backup/'manifest.json').write_text(json.dumps(m));(backup/'fallback.html').write_bytes(fallback)
  shutil.copytree(old,new,symlinks=True)
  for n in TARGETS:shutil.copyfile(stage/'static'/n,new/n)
  after,newlinks=base.inventory(new);assert links==newlinks and files.keys()==after.keys()
  assert all(after[n]==h for n,h in files.items() if n not in TARGETS and n!='market-display-cache.json')
  temp=base.FALLBACK.with_name('index.manifest-next.html');assert not temp.exists()
  try:
   temp.write_bytes((stage/'fallback.html').read_bytes());shutil.copymode(base.FALLBACK,temp)
   base.switch(base.CURRENT,new);os.replace(temp,base.FALLBACK)
   assert bot.config()==config and base.state_digest()==states and bot.pids()==services
   assert Path('/opt/radar-alarms/current').resolve()==backend and base.inventory(backend)==backend_files
   assert base.sha((public/'sw.js').read_bytes())==worker and base.sha((public/'manifest.webmanifest').read_bytes())==manifest
   assert all(base.sha((new/n).read_bytes())==h for n,h in m['files'].items());base.health()
   report=dict(source=m['source'],release=str(new),previous=str(old),backup=str(backup),changedHTML=len(TARGETS),otherFilesPreserved=len(files)-len(TARGETS),workerAndManifestUnchanged=True,backendAndServicesUnchanged=True,rulesBindingsSubscriptionsPreserved=True)
   (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
  except BaseException:
   if base.CURRENT.resolve()==new:
    base.switch(base.CURRENT,old);temp.write_bytes(fallback);os.replace(temp,base.FALLBACK)
   raise
if __name__=='__main__':main()
