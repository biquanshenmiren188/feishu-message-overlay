"""Incremental static/backend release; stage manifest pins both live baselines."""
import fcntl, hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path
spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text())
assert set(m['backend'])=={'engine.py','store.py','server.py','test_alarms.py','market.py'}
assert set(m['files'])=={'robot-push/alarms/'+n for n in ('index.html','app.js','style.css','session.js','dom.js','history.html','history.js','snapshot.js')}
for group,folder in [('backend','backend'),('files','static')]:
 for n,h in m[group].items():assert base.sha((stage/folder/n).read_bytes())==h,n
assert base.sha((stage/'pushbackend/server.py').read_bytes())==m['pushFile']
subprocess.run(['/opt/radar-webpush-test/venv/bin/python','-m','unittest','discover','-s',str(stage/'pushbackend'),'-p','server_test.py'],check=True)
subprocess.run(['/opt/radar-webpush-test/venv/bin/python','-m','unittest','discover','-s',str(stage/'backend'),'-p','test_*.py'],check=True)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 push=Path('/opt/radar-webpush-test/server.py');oldpush=push.read_bytes();assert base.sha(oldpush)==m['pushBaseline']
 old=base.CURRENT.resolve();oldb=Path('/opt/radar-alarms/current').resolve()
 assert str(old)==m['previous'] and str(oldb)==m['previousBackend']
 for n,h in m['baseline'].items():assert base.sha((old/n).read_bytes())==h,n
 for n in m.get('newFiles',[]):assert not (old/n).exists(),n
 for n,h in m['backendBaseline'].items():assert base.sha((oldb/n).read_bytes())==h,n
 if '--apply' not in sys.argv:print('Preflight passed');sys.exit(0)
 label='20261111-alarm-cache-'+str(time.time_ns());new=base.ROOT/'releases'/label
 newb=Path('/opt/radar-alarms/releases')/m['source'];backup=base.ROOT/'backups'/label;backup.mkdir()
 (backup/'webpush-server.py').write_bytes(oldpush)
 (backup/'manifest.json').write_text(json.dumps(m,indent=2))
 before,links=base.inventory(old);pids=subprocess.check_output(['systemctl','show','robot-push','--property=MainPID']);states=base.state_digest();fallback=base.FALLBACK.read_bytes()
 shutil.copytree(old,new,symlinks=True);shutil.copytree(oldb,newb,ignore=shutil.ignore_patterns('__pycache__'))
 for n in m['files']:shutil.copyfile(stage/'static'/n,new/n);(new/n).chmod(0o644)
 for n in m['backend']:shutil.copyfile(stage/'backend'/n,newb/n);(newb/n).chmod(0o644)
 after,newlinks=base.inventory(new);assert links==newlinks
 assert all(after[n]==h for n,h in before.items() if n not in m['files'] and n!='market-display-cache.json')
 try:
  shutil.copyfile(stage/'pushbackend/server.py',push);push.chmod(0o644)
  subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  from urllib.request import Request,urlopen
  credential=json.loads(Path('/var/lib/radar-webpush-test/state.json').read_text())['token']
  for attempt in range(30):
   try:
    with urlopen(Request('http://127.0.0.1:18885/internal/alarm-identity',headers={'Authorization':'Bearer '+credential}),timeout=2) as response:
     assert 'profileId' in json.load(response)
    break
   except Exception:time.sleep(.5)
  else:raise RuntimeError('Identity service readiness failed')
  base.switch(Path('/opt/radar-alarms/current'),newb)
  subprocess.run(['systemctl','restart','radar-alarms'],check=True)
  from urllib.request import urlopen
  for _ in range(30):
   try:
    health=json.load(urlopen('http://127.0.0.1:18886/radar/alarms-api/health',timeout=2))
    assert health['notificationLevel']=='critical' and health['ringingSeconds']==30 and health['version']==5;break
   except Exception:time.sleep(.5)
  else:raise RuntimeError('health failed')
  from urllib.request import Request
  credential=json.loads(Path('/var/lib/radar-webpush-test/state.json').read_text())['token']
  with urlopen(Request('http://127.0.0.1:18886/radar/alarms-api/state?events=latest-test',headers={'Authorization':'Bearer '+credential}),timeout=10) as response:
   assert 'revision' in json.load(response)
  assert base.CURRENT.resolve()==old
  base.switch(base.CURRENT,new)
  assert pids==subprocess.check_output(['systemctl','show','robot-push','--property=MainPID']) and states==base.state_digest() and fallback==base.FALLBACK.read_bytes()
  assert all(base.sha((new/n).read_bytes())==h for n,h in m['files'].items())
  report=dict(release=str(new),backend=str(newb),previous=str(old),previousBackend=str(oldb),source=m['source'],health=health,publisherUnchanged=True,webpushRestarted=True)
  (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
 except BaseException:
  if base.CURRENT.resolve()==new:base.switch(base.CURRENT,old)
  push.write_bytes(oldpush)
  subprocess.run(['systemctl','restart','radar-webpush-test'],check=True)
  base.switch(Path('/opt/radar-alarms/current'),oldb)
  subprocess.run(['systemctl','restart','radar-alarms'],check=True)
  raise
