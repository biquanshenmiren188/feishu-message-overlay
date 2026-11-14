"""Correct the installed app's navigation scope without replacing its identity or worker."""
import fcntl,importlib.util,json,os,re,shutil,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('bot',Path(__file__).with_name('deploy-bot-entry.py'))
bot=importlib.util.module_from_spec(spec);spec.loader.exec_module(bot)
base=bot.base

def main():
 stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text())
 assert re.fullmatch(r'[a-f0-9]{40}',m['source'])
 target=Path('/opt/radar-webpush-test/public/manifest.webmanifest')
 worker=target.with_name('sw.js')
 with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  current=base.CURRENT.resolve();assert str(current)==m['current'],'Concurrent release'
  before=target.read_bytes();assert base.sha(before)==m['before'],'Manifest changed'
  after=(stage/'manifest.webmanifest').read_bytes();assert base.sha(after)==m['after']
  a,b=json.loads(before),json.loads(after)
  assert a['scope']=='/radar/push-test/' and b['scope']=='/radar/'
  assert dict(a,scope=b['scope'])==b,'Only navigation scope may change'
  assert a['id']==a['start_url']=='/radar/push-test/' and b['display']=='standalone'
  base.health()
  if '--apply' not in sys.argv:print('PWA scope preflight passed');return
  static=base.inventory(current);backend=Path('/opt/radar-alarms/current').resolve()
  backend_files=base.inventory(backend);services=bot.pids();config=bot.config();states=base.state_digest()
  worker_hash=base.sha(worker.read_bytes());fallback_hash=base.sha(base.FALLBACK.read_bytes())
  backup=base.ROOT/'backups'/('20261114-pwa-scope-'+str(time.time_ns()));backup.mkdir(mode=0o700)
  (backup/'manifest.webmanifest').write_bytes(before);(backup/'source.json').write_text(json.dumps(m))
  temp=target.with_name('manifest.scope-next');assert not temp.exists()
  try:
   temp.write_bytes(after);shutil.copymode(target,temp);os.replace(temp,target)
   assert base.CURRENT.resolve()==current and Path('/opt/radar-alarms/current').resolve()==backend
   now=base.inventory(current)
   assert now[1]==static[1] and now[0].keys()==static[0].keys()
   assert all(now[0][n]==h for n,h in static[0].items() if n!='market-display-cache.json')
   assert base.inventory(backend)==backend_files and bot.pids()==services
   assert bot.config()==config and base.state_digest()==states
   assert base.sha(worker.read_bytes())==worker_hash and base.sha(base.FALLBACK.read_bytes())==fallback_hash
   assert target.read_bytes()==after;base.health()
   report=dict(source=m['source'],backup=str(backup),current=str(current),scope=b['scope'],id=b['id'],start_url=b['start_url'],onlyScopeChanged=True,workerUnchanged=True,staticAndBackendUnchanged=True,rulesBindingsSubscriptionsPreserved=True,servicesUnchanged=True,manifestSha=base.sha(after))
   (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
  except BaseException:
   if target.read_bytes()==after:
    temp.write_bytes(before);shutil.copymode(target,temp);os.replace(temp,target)
   raise
if __name__=='__main__':main()
