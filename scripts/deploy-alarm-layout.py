"""Static-only approved alarm layout. Preserve all services and alarm configuration.

Run on authorized host: python3 deploy-alarm-layout.py STAGE [--apply].
Stage pins source commit, live baseline and exactly four alarm UI assets.
"""
import fcntl, importlib.util, json, shutil, sqlite3, subprocess, sys, time
from pathlib import Path

spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def pids():
    return subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','radar-alarms','--property=Id,MainPID'],text=True)

def alarm_config():
    with sqlite3.connect('file:/var/lib/radar-alarms/alarms.sqlite3?mode=ro',uri=True) as db:
        values=[db.execute(sql).fetchall() for sql in (
            'SELECT id,enabled,revision FROM profiles ORDER BY id',
            'SELECT id,profile,config FROM rules ORDER BY id',
            'SELECT * FROM devices ORDER BY profile')]
    return base.sha(json.dumps(values,sort_keys=True).encode())

stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text())
expected={'robot-push/alarms/'+n for n in ('index.html','history.html','app.js','compact.css')}
assert set(m['files'])==expected
assert set(m['baseline'])==expected-{'robot-push/alarms/compact.css'}
assert m['newFiles']==['robot-push/alarms/compact.css']
for n,h in m['files'].items():assert base.sha((stage/'static'/n).read_bytes())==h,n
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    old=base.CURRENT.resolve();assert str(old)==m['previous']
    for n,h in m['baseline'].items():assert base.sha((old/n).read_bytes())==h,n
    for n in m['newFiles']:assert not (old/n).exists(),n
    base.health()
    if '--apply' not in sys.argv:print('Preflight passed');sys.exit(0)
    label='20261113-alarm-layout-'+str(time.time_ns());new=base.ROOT/'releases'/label
    backup=base.ROOT/'backups'/label;backup.mkdir(mode=0o700)
    (backup/'manifest.json').write_text(json.dumps(m,indent=2))
    before,links=base.inventory(old);services=pids();backend=Path('/opt/radar-alarms/current').resolve()
    backend_files=base.inventory(backend);fallback=base.FALLBACK.read_bytes();config=alarm_config();states=base.state_digest()
    shutil.copytree(old,new,symlinks=True)
    for n in m['files']:
        assert not (new/n).is_symlink();shutil.copyfile(stage/'static'/n,new/n);(new/n).chmod(0o644)
    after,newlinks=base.inventory(new);assert links==newlinks
    assert set(after)==set(before)|set(m['newFiles'])
    assert all(after[n]==h for n,h in before.items() if n not in m['files'] and n!='market-display-cache.json')
    try:
        base.switch(base.CURRENT,new)
        assert pids()==services and Path('/opt/radar-alarms/current').resolve()==backend
        assert backend_files==base.inventory(backend) and fallback==base.FALLBACK.read_bytes()
        assert config==alarm_config() and states==base.state_digest(),'Unexpected configuration change'
        assert all(base.sha((new/n).read_bytes())==h for n,h in m['files'].items())
        base.health()
        report=dict(release=str(new),previous=str(old),backend=str(backend),source=m['source'],
            allServicesUnchanged=True,backendFilesUnchanged=True,rulesAndBindingsPreserved=True,
            preservedFiles=len(before)-len(m['baseline']),files=m['files'])
        (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
    except BaseException:
        if base.CURRENT.resolve()==new:base.switch(base.CURRENT,old)
        raise
