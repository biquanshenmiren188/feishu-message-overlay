"""Static-only follow-up to price alarms. Run on host with STAGE [--apply]."""
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

spec=importlib.util.spec_from_file_location('alarm_deploy',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def service_ids():
    return subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','radar-alarms','--property=Id,MainPID'],text=True)

def main():
    stage=Path(sys.argv[1]).resolve();apply='--apply' in sys.argv[2:]
    manifest=json.loads((stage/'manifest.json').read_text())
    assert manifest['validation']['passed']
    for name,digest in manifest['files'].items():
        assert not name.startswith('/') and '..' not in name.split('/') and '\\' not in name
        assert base.sha((stage/'static'/name).read_bytes())==digest
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=base.CURRENT.resolve();assert str(old)==manifest['previous']
        for name,digest in manifest['baseline'].items():assert base.sha((old/name).read_bytes())==digest,name
        before,links=base.inventory(old);states=base.state_digest();pids=service_ids();fallback=base.FALLBACK.read_bytes()
        if not apply:
            print(json.dumps({'preflight':True,'release':str(old),'files':len(manifest['files'])}));return
        label='20261106-account-entry-'+str(time.time_ns())
        new=base.ROOT/'releases'/label;backup=base.ROOT/'backups'/label;backup.mkdir(mode=0o700)
        (backup/'previous-target.txt').write_text(str(old));(backup/'fallback.html').write_bytes(fallback)
        (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
        shutil.copytree(old,new,symlinks=True)
        for name in manifest['files']:
            target=new/name;assert not target.is_symlink();shutil.copyfile(stage/'static'/name,target);target.chmod(0o644)
        after,new_links=base.inventory(new);assert links==new_links
        assert all(after[n]==h for n,h in before.items() if n not in manifest['files'] and n!='market-display-cache.json')
        assert all(after[n]==h for n,h in manifest['files'].items())
        assert states==base.state_digest() and pids==service_ids() and base.CURRENT.resolve()==old
        try:
            base.switch(base.CURRENT,new)
            base.FALLBACK.write_bytes((new/'robot-push/index.html').read_bytes())
            base.health();assert states==base.state_digest() and pids==service_ids()
            report={'release':str(new),'previous':str(old),'sourceCommits':manifest['sourceCommits'],'staticFiles':len(manifest['files']),'servicesUnchanged':True,'rulesAndBindingsPreserved':True}
            (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        except BaseException:
            if base.CURRENT.resolve()==new:base.switch(base.CURRENT,old)
            base.FALLBACK.write_bytes(fallback)
            raise

if __name__=='__main__':main()
