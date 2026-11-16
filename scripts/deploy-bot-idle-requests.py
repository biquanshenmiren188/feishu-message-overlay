"""Replace only the blocked-history reader; preserve all UI and alarm assets."""
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


base = module('base', 'deploy-price-alarms.py')
safety = module('safety', 'deploy-bot-resource-budget.py')


def main():
    stage = Path(sys.argv[1]); manifest = json.loads((stage/'manifest.json').read_text())
    expected = {'robot-push/blocked-pushes.js'}
    assert set(manifest['files']) == expected and set(manifest['baseline']) == expected
    for name, digest in manifest['files'].items():
        assert base.sha((stage/'static'/name).read_bytes()) == digest
    with open('/var/lib/funding-radar-storage/guard.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = base.CURRENT.resolve(); assert str(old) == manifest['previous']
        for name, digest in manifest['baseline'].items(): assert base.sha((old/name).read_bytes()) == digest
        if '--apply' not in sys.argv:
            print(json.dumps(dict(preflight=True, current=str(old)))); return
        before, links = base.inventory(old)
        state = safety.protected_state(); pids = safety.pids()
        backend = Path('/opt/radar-alarms/current').resolve(); backend_files = base.inventory(backend)
        fallback = base.FALLBACK.read_bytes()
        old_url = b'blocked-pushes.js?v=20261028-feed1'
        new_url = b'blocked-pushes.js?v=20261116-idle1'
        html_name = 'robot-push/index.html'
        html = (old/html_name).read_bytes()
        assert html.count(old_url) == 1 and fallback.count(old_url) == 1
        new_fallback = fallback.replace(old_url, new_url)
        label = '20261116-bot-idle-requests-' + str(time.time_ns())
        new = base.ROOT/'releases'/label; backup = base.ROOT/'backups'/label
        backup.mkdir(mode=0o700)
        (backup/'manifest.json').write_text(json.dumps(manifest, indent=2))
        (backup/'fallback.html').write_bytes(fallback)
        shutil.copytree(old, new, symlinks=True)
        for name in expected:
            assert not (new/name).is_symlink()
            shutil.copyfile(stage/'static'/name, new/name); (new/name).chmod(0o644)
        (new/html_name).write_bytes(html.replace(old_url, new_url))
        after, newlinks = base.inventory(new)
        assert newlinks == links
        assert all(after[n] == h for n,h in before.items() if n not in expected|{html_name} and n != 'market-display-cache.json')
        try:
            assert safety.protected_state() == state
            fallback_tmp = base.FALLBACK.with_name('index.idle-next.html')
            fallback_tmp.write_bytes(new_fallback); fallback_tmp.chmod(0o644)
            fallback_tmp.replace(base.FALLBACK)
            base.switch(base.CURRENT, new)
            assert safety.pids() == pids and safety.protected_state() == state
            assert Path('/opt/radar-alarms/current').resolve() == backend
            assert base.inventory(backend) == backend_files and base.FALLBACK.read_bytes() == new_fallback
            base.health()
            report = dict(source=manifest['source'],release=str(new),previous=str(old),
                changedFiles=sorted(expected|{html_name}),preservedFiles=len(before)-2,
                fallbackChange='blocked history script version only',
                bindingsAndRulesUnchanged=True,alarmBackendUnchanged=True,servicesUnchanged=True)
            (backup/'deployment.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report))
        except BaseException:
            if base.CURRENT.resolve() == new: base.switch(base.CURRENT,old)
            if base.FALLBACK.read_bytes() == new_fallback:
                base.FALLBACK.write_bytes(fallback)
            raise


if __name__ == '__main__': main()
