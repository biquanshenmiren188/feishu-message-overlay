"""Atomic additive center release. Never restart existing senders or restore user data."""
import fcntl
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

spec=importlib.util.spec_from_file_location('base',Path(__file__).with_name('deploy-price-alarms.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
BACKEND=Path('/opt/radar-push-center')
SNIPPET=Path('/etc/nginx/snippets/radar-push-center.conf')
UNIT=Path('/etc/systemd/system/radar-push-center.service')
PWA=Path('/opt/radar-webpush-test/public/center')

def pids():return subprocess.check_output(['systemctl','show','robot-push','radar-webpush-test','radar-alarms','--property=Id,MainPID'],text=True)
def health():
    with urlopen('http://127.0.0.1:18887/radar/push-center-api/health',timeout=5) as r:assert json.load(r)['ok']
    base.health()

def main():
    stage=Path(sys.argv[1]).resolve();apply='--apply' in sys.argv[2:]
    manifest=json.loads((stage/'manifest.json').read_text())
    assert manifest['validation']['passed'] and manifest['validation']['files']==manifest['files']
    for group in ('files','backend'):
        for name,digest in manifest[group].items():
            assert not name.startswith('/') and '..' not in name.split('/') and '\\' not in name
            assert base.sha((stage/('static' if group=='files' else 'backend')/name).read_bytes())==digest
    subprocess.run(['/usr/bin/python3','-m','unittest','discover','-s',str(stage/'backend'),'-p','*_test.py'],check=True)
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=base.CURRENT.resolve();assert str(old)==manifest['previous']
        for name,digest in manifest['baseline'].items():assert base.sha((old/name).read_bytes())==digest,name
        for name in manifest['newFiles']:assert not (old/name).exists(),name
        assert not PWA.exists() and not PWA.is_symlink()
        assert not (BACKEND/'current').exists() and not UNIT.exists() and not SNIPPET.exists()
        before,links=base.inventory(old);states=base.state_digest();services=pids();fallback=base.FALLBACK.read_bytes();old_nginx=base.SNIPPET.read_bytes()
        if not apply:
            print(json.dumps(dict(preflight=True,previous=str(old),files=len(manifest['files']))));return
        label='20261106-push-center-'+str(time.time_ns())
        new=base.ROOT/'releases'/label;backup=base.ROOT/'backups'/label;backup.mkdir(mode=0o700)
        (backup/'previous-target.txt').write_text(str(old));(backup/'fallback.html').write_bytes(fallback);(backup/'push-snippet.conf').write_bytes(old_nginx);(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
        shutil.copytree(old,new,symlinks=True)
        for name in manifest['files']:
            target=new/name;assert not target.is_symlink();target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(stage/'static'/name,target);target.chmod(0o644)
        after,newlinks=base.inventory(new);assert links==newlinks
        assert all(after[n]==h for n,h in before.items() if n not in manifest['files'] and n!='market-display-cache.json')
        backend=BACKEND/'releases'/manifest['sourceCommits']['push'];backend.mkdir(parents=True)
        for name in manifest['backend']:shutil.copyfile(stage/'backend'/name,backend/name);(backend/name).chmod(0o644)
        try:
            base.switch(BACKEND/'current',backend);shutil.copyfile(backend/'radar-push-center.service',UNIT)
            subprocess.run(['systemctl','daemon-reload'],check=True);subprocess.run(['systemctl','enable','--now','radar-push-center'],check=True)
            for _ in range(20):
                try:health();break
                except Exception:time.sleep(.5)
            else:raise RuntimeError('Center health failed')
            SNIPPET.write_text('''location ^~ /radar/push-center-api/ {
    limit_req zone=funding_http burst=20 nodelay;
    limit_req_status 429;
    limit_conn funding_conn 16;
    proxy_pass http://127.0.0.1:18887;
    proxy_connect_timeout 2s;
    proxy_read_timeout 30s;
    client_max_body_size 8k;
    access_log off;
    add_header Cache-Control "no-store" always;
}
''')
            base.SNIPPET.write_bytes(old_nginx+b'\ninclude /etc/nginx/snippets/radar-push-center.conf;\n')
            PWA.symlink_to(base.CURRENT/'push-center',target_is_directory=True)
            subprocess.run(['nginx','-t'],check=True)
            assert base.CURRENT.resolve()==old and base.state_digest()==states and pids()==services
            base.switch(base.CURRENT,new);base.FALLBACK.write_bytes((new/'robot-push/index.html').read_bytes())
            subprocess.run(['systemctl','reload','nginx'],check=True);health()
            assert base.state_digest()==states and pids()==services
            after,afterlinks=base.inventory(new);assert afterlinks==links and all(after[n]==h for n,h in manifest['files'].items())
            report=dict(release=str(new),previous=str(old),sourceCommits=manifest['sourceCommits'],staticFiles=len(manifest['files']),preservedFiles=len(before)-len(set(before)&set(manifest['files'])),existingServicesUnchanged=True,rulesAndBindingsPreserved=True,centerService='active',pwaCenter=True)
            (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        except BaseException:
            if base.CURRENT.resolve()==new:base.switch(base.CURRENT,old)
            base.FALLBACK.write_bytes(fallback);base.SNIPPET.write_bytes(old_nginx);SNIPPET.unlink(missing_ok=True)
            PWA.unlink(missing_ok=True);subprocess.run(['systemctl','disable','--now','radar-push-center'])
            UNIT.unlink(missing_ok=True);(BACKEND/'current').unlink(missing_ok=True);subprocess.run(['systemctl','daemon-reload'])
            subprocess.run(['nginx','-t'],check=True);subprocess.run(['systemctl','reload','nginx'],check=True)
            raise

if __name__=='__main__':main()
