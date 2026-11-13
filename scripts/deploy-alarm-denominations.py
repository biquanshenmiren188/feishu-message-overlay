"""Backend-only guarded release. All website/phone assets remain byte-identical."""
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen

spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def config():
    with sqlite3.connect('file:/var/lib/radar-alarms/alarms.sqlite3?mode=ro',uri=True) as db:
        return base.sha(json.dumps({name:db.execute('SELECT '+cols+' FROM '+name+' ORDER BY 1').fetchall()
            for name,cols in [('profiles','*'),('rules','id,profile,config,created'),('devices','*')]},sort_keys=True).encode())

stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text())
assert set(m['backend'])=={'engine.py','store.py','server.py','test_alarms.py','market.py','instruments.py','sources.py','test_sources.py','denominations.py','test_denominations.py'}
assert not m['files']
for n,h in m['backend'].items():assert base.sha((stage/'backend'/n).read_bytes())==h,n
subprocess.run(['/opt/radar-webpush-test/venv/bin/python','-m','unittest','discover','-s',str(stage/'backend'),'-p','test_*.py'],check=True)
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    old=base.CURRENT.resolve();oldb=Path('/opt/radar-alarms/current').resolve()
    assert str(old)==m['previous'] and str(oldb)==m['previousBackend']
    for n,h in m['backendBaseline'].items():assert base.sha((oldb/n).read_bytes())==h,n
    for n in set(m['backend'])-set(m['backendBaseline']):assert not (oldb/n).exists(),n
    if '--apply' not in sys.argv:print('Preflight passed; backend only');sys.exit(0)
    newb=Path('/opt/radar-alarms/releases')/m['source']
    backup=base.ROOT/'backups'/('20261113-alarm-denominations-'+str(time.time_ns()));backup.mkdir()
    (backup/'manifest.json').write_text(json.dumps(m,indent=2))
    original,links=base.inventory(old);before=config();pids=base.pids();state=base.state_digest()
    shutil.copytree(oldb,newb,ignore=shutil.ignore_patterns('__pycache__'))
    for n in m['backend']:
        shutil.copyfile(stage/'backend'/n,newb/n);(newb/n).chmod(0o644)
    try:
        base.switch(Path('/opt/radar-alarms/current'),newb)
        subprocess.run(['systemctl','restart','radar-alarms'],check=True)
        for _ in range(30):
            try:
                health=json.load(urlopen('http://127.0.0.1:18886/radar/alarms-api/health',timeout=2))
                assert health['version']==12 and health['denominationConversion'] is True
                assert health['quoteRouting']=='same-asset-spot-v3' and health['repeatIntervalSeconds']==30
                assert health['notificationLevel']=='critical' and health['fallbackMultiSelect'] is True
                break
            except Exception:time.sleep(.5)
        else:raise RuntimeError('health failed')
        assert before==config(),'Alarm rules or bindings changed'
        assert base.CURRENT.resolve()==old and pids==base.pids() and state==base.state_digest()
        after,newlinks=base.inventory(old);assert links==newlinks
        assert all(after[n]==h for n,h in original.items() if n!='market-display-cache.json')
        assert all(base.sha((newb/n).read_bytes())==h for n,h in m['backend'].items())
        report=dict(backend=str(newb),previousBackend=str(oldb),release=str(old),source=m['source'],health=health,
                    rulesAndBindingsPreserved=True,unrelatedServicesUnchanged=True,unchangedStaticFiles=len(original))
        (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    except BaseException:
        base.switch(Path('/opt/radar-alarms/current'),oldb)
        subprocess.run(['systemctl','restart','radar-alarms'],check=True)
        raise
