"""Static-only mobile layout rollout. Current release is cloned; no service or rule writes."""
import fcntl,importlib.util,json,os,re,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def pids():return subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','radar-alarms','--property=Id,MainPID'],text=True)
def config():
    with sqlite3.connect('file:/var/lib/radar-alarms/alarms.sqlite3?mode=ro',uri=True) as db:
        return base.sha(json.dumps([db.execute(q).fetchall() for q in ('SELECT id,enabled,revision FROM profiles ORDER BY id','SELECT id,profile,config FROM rules ORDER BY id','SELECT * FROM devices ORDER BY profile')],sort_keys=True).encode())
def main():
    stage=Path(sys.argv[1]);m=json.loads((stage/'manifest.json').read_text())
    assert re.fullmatch(r'[0-9a-f]{40}',m['source']), 'Expected committed source SHA'
    expected={'index.html','position-limits/index.html','robot-push/index.html','robot-push/settings/index.html','robot-push/alarms/index.html','robot-push/alarms/history.html','robot-push/mobile-compact.css','robot-push/settings/mobile-compact.js'}
    assert set(m['files'])==expected and set(m['newFiles'])=={'robot-push/mobile-compact.css','robot-push/settings/mobile-compact.js'}
    assert set(m['baseline'])==expected-set(m['newFiles'])
    for name,h in m['files'].items():assert base.sha((stage/'static'/name).read_bytes())==h,name
    assert base.sha((stage/'fallback.html').read_bytes())==m['fallbackAfter']
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=base.CURRENT.resolve();assert str(old)==m['previous'],'Concurrent release: rebuild candidate'
        for n,h in m['baseline'].items():assert base.sha((old/n).read_bytes())==h,n
        for n in m['newFiles']:assert not (old/n).exists(),n
        fallback=base.FALLBACK.read_bytes();assert base.sha(fallback)==m['fallbackBefore'];base.health()
        if '--apply' not in sys.argv:print('Preflight passed');return
        original,links=base.inventory(old);services=pids();backend=Path('/opt/radar-alarms/current').resolve();backend_files=base.inventory(backend);alarm_config=config();states=base.state_digest()
        name='20261113-mobile-compact-'+str(time.time_ns());new=base.ROOT/'releases'/name;backup=base.ROOT/'backups'/name;backup.mkdir(mode=0o700)
        (backup/'manifest.json').write_text(json.dumps(m,indent=2));(backup/'fallback.html').write_bytes(fallback)
        shutil.copytree(old,new,symlinks=True)
        for n in m['files']:
            assert not (new/n).is_symlink();shutil.copyfile(stage/'static'/n,new/n);(new/n).chmod(0o644)
        after,newlinks=base.inventory(new);assert links==newlinks and set(after)==set(original)|set(m['newFiles'])
        assert all(after[n]==h for n,h in original.items() if n not in m['files'] and n!='market-display-cache.json')
        temp=base.FALLBACK.with_name('index.mobile-next.html');assert not temp.exists()
        try:
            temp.write_bytes((stage/'fallback.html').read_bytes());shutil.copymode(base.FALLBACK,temp)
            assert config()==alarm_config and base.state_digest()==states
            base.switch(base.CURRENT,new);os.replace(temp,base.FALLBACK)
            assert pids()==services and Path('/opt/radar-alarms/current').resolve()==backend and base.inventory(backend)==backend_files
            assert config()==alarm_config and base.state_digest()==states
            assert all(base.sha((new/n).read_bytes())==h for n,h in m['files'].items());base.health()
            report=dict(release=str(new),previous=str(old),backend=str(backend),source=m['source'],allServicesUnchanged=True,backendFilesUnchanged=True,rulesAndBindingsPreserved=True,preservedFiles=len(original)-len(m['baseline']),files=m['files'])
            (backup/'deployment.json').write_text(json.dumps(report));print(json.dumps(report))
        except BaseException:
            if base.CURRENT.resolve()==new:
                base.switch(base.CURRENT,old);temp.write_bytes(fallback);os.replace(temp,base.FALLBACK)
            raise
if __name__=='__main__':main()
