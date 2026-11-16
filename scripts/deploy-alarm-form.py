"""Static-only alarm form cleanup. No service restart or existing rule write."""
import fcntl, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path
spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def pids():
    return subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','radar-alarms','--property=Id,MainPID'],text=True)

stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text())
assert set(m['files'])=={'robot-push/alarms/'+n for n in ('index.html','app.js','search.js')}
assert set(m['baseline'])==set(m['files'])
for n,h in m['files'].items():assert base.sha((stage/'static'/n).read_bytes())==h,n
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    old=base.CURRENT.resolve();assert str(old)==m['previous']
    for n,h in m['baseline'].items():assert base.sha((old/n).read_bytes())==h,n
    if '--apply' not in sys.argv:print('Preflight passed');sys.exit(0)
    label='20261113-alarm-form-'+str(time.time_ns());new=base.ROOT/'releases'/label;backup=base.ROOT/'backups'/label;backup.mkdir()
    (backup/'manifest.json').write_text(json.dumps(m,indent=2))
    before,links=base.inventory(old);services=pids();backend=Path('/opt/radar-alarms/current').resolve();fallback=base.FALLBACK.read_bytes()
    shutil.copytree(old,new,symlinks=True)
    for n in m['files']:shutil.copyfile(stage/'static'/n,new/n);(new/n).chmod(0o644)
    after,newlinks=base.inventory(new);assert links==newlinks
    assert all(after[n]==h for n,h in before.items() if n not in m['files'] and n!='market-display-cache.json')
    try:
        base.switch(base.CURRENT,new)
        assert pids()==services and Path('/opt/radar-alarms/current').resolve()==backend and fallback==base.FALLBACK.read_bytes()
        assert all(base.sha((new/n).read_bytes())==h for n,h in m['files'].items())
        report=dict(release=str(new),previous=str(old),backend=str(backend),source=m['source'],allServicesUnchanged=True,preservedFiles=len(before)-3)
        (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
    except BaseException:
        if base.CURRENT.resolve()==new:base.switch(base.CURRENT,old)
        raise
