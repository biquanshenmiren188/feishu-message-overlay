"""Run on the authorized host. Incremental assets + new isolated service.

python3 deploy-price-alarms.py STAGE PUSH_SHA RADAR_SHA [--check|--apply]
Never restore user state on rollback. Existing message services are not restarted.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT=Path('/opt/funding-radar-web');CURRENT=ROOT/'current'
BACKEND=Path('/opt/radar-alarms');SNIPPET=Path('/etc/nginx/snippets/radar-webpush-test.conf')
ALARM_SNIPPET=Path('/etc/nginx/snippets/radar-alarms.conf')
FALLBACK=Path('/opt/radar-webpush-test/public/index.html')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def inventory(root):
    files,links={},{}
    for p in root.rglob('*'):
        name=str(p.relative_to(root))
        if p.is_symlink():links[name]=os.readlink(p)
        elif p.is_file():files[name]=sha(p.read_bytes())
    return files,links


def state_digest():
    root=Path('/var/lib/radar-webpush-test');value={}
    for p in [root/'state.json',*sorted((root/'profiles').glob('*/state.json'))]:
        if p.exists():
            raw=json.loads(p.read_text());live=raw.get('live',{})
            value[str(p)]={k:raw.get(k) for k in ('token','subscription','device')}
            value[str(p)]['settings']={k:live.get(k) for k in ('settings','revision')}
    for p in [root/'desktop-rules.json',*sorted((root/'profiles').glob('*/desktop-rules.json')),root/'profiles.json',Path('/etc/radar-webpush-test/config.json')]:
        if p.exists():value[str(p)]=sha(p.read_bytes())
    # Device telemetry changes during normal use; subscription and preferences do not.
    for v in value.values():
        if isinstance(v,dict):v.pop('device',None)
    return sha(json.dumps(value,sort_keys=True).encode())


def pids():
    return subprocess.check_output(['systemctl','show','robot-push.service','radar-webpush-test.service','--property=Id,MainPID'],text=True)


def switch(link,target):
    temp=link.with_name(link.name+'.alarms-next')
    if temp.exists() or temp.is_symlink():raise ValueError('stale switch marker')
    temp.symlink_to(target);os.replace(temp,link)


def health():
    with urlopen('http://127.0.0.1:18886/radar/alarms-api/health',timeout=5) as response:
        assert json.load(response)['ok']


def main():
    stage=Path(sys.argv[1]).resolve();push_sha,radar_sha=sys.argv[2:4];apply=len(sys.argv)>4 and sys.argv[4]=='--apply'
    assert all(re.fullmatch('[a-f0-9]{40}',s) for s in (push_sha,radar_sha))
    manifest=json.loads((stage/'manifest.json').read_text())
    validation=json.loads((stage/'validation.json').read_text())
    assert validation['passed'] and validation['files']==manifest['files']
    assert manifest['sourceCommits']=={'push':push_sha,'radar':radar_sha}
    for name,digest in manifest['files'].items():
        assert not name.startswith('/') and '..' not in name.split('/') and '\\' not in name
        assert sha((stage/'static'/name).read_bytes())==digest
    for name,digest in manifest['backend'].items():assert sha((stage/'backend'/name).read_bytes())==digest
    subprocess.run(['/opt/radar-webpush-test/venv/bin/python','-m','unittest','discover','-s',str(stage/'backend'),'-p','test_*.py'],check=True)
    with open('/var/lib/funding-radar-storage/guard.lock','a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=CURRENT.resolve();assert old.parent==ROOT/'releases'
        for name,digest in manifest['baseline'].items():assert sha((old/name).read_bytes())==digest,'Live asset changed: '+name
        for name in manifest.get('newFiles',[]):assert not (old/name).exists(),'Unexpected concurrent asset: '+name
        original,links=inventory(old);states=state_digest();services=pids();fallback=FALLBACK.read_bytes()
        if not apply:
            print(json.dumps(dict(preflight=True,release=str(old),files=len(original),rulesPreserved=True)));return
        label='20261106-price-alarms-'+str(time.time_ns());new=ROOT/'releases'/label;backup=ROOT/'backups'/label;backup.mkdir(mode=0o700)
        old_snippet=SNIPPET.read_bytes();old_alarm=ALARM_SNIPPET.read_bytes() if ALARM_SNIPPET.exists() else None
        old_service=Path('/etc/systemd/system/radar-alarms.service').read_bytes() if Path('/etc/systemd/system/radar-alarms.service').exists() else None
        old_backend=(BACKEND/'current').resolve() if (BACKEND/'current').exists() else None
        (backup/'previous-target.txt').write_text(str(old));(backup/'push-snippet.conf').write_bytes(old_snippet);(backup/'fallback.html').write_bytes(fallback)
        (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
        (backup/'before-inventory.json').write_text(json.dumps(dict(files=original,links=links)))
        if old_alarm:(backup/'alarm-snippet.conf').write_bytes(old_alarm)
        if old_service:(backup/'radar-alarms.service').write_bytes(old_service)
        shutil.copytree(old,new,symlinks=True)
        for name in manifest['files']:
            target=new/name;assert not target.is_symlink();target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(stage/'static'/name,target);target.chmod(0o644)
        copied,copied_links=inventory(new)
        assert copied_links==links
        for name,digest in original.items():
            if name not in manifest['files'] and name!='market-display-cache.json':assert copied[name]==digest,name
        backend=BACKEND/'releases'/push_sha;backend.mkdir(parents=True,exist_ok=False)
        for name in manifest['backend']:shutil.copyfile(stage/'backend'/name,backend/name);(backend/name).chmod(0o644)
        nginx='''location ^~ /radar/alarms-api/ {
    limit_req zone=funding_http burst=20 nodelay;
    limit_req_status 429;
    limit_conn funding_conn 16;
    proxy_pass http://127.0.0.1:18886;
    proxy_connect_timeout 2s;
    proxy_read_timeout 20s;
    client_max_body_size 8k;
    access_log off;
    add_header Cache-Control "no-store" always;
}
'''
        try:
            switch(BACKEND/'current',backend)
            shutil.copyfile(backend/'radar-alarms.service','/etc/systemd/system/radar-alarms.service')
            subprocess.run(['systemctl','daemon-reload'],check=True)
            subprocess.run(['systemctl','enable','--now','radar-alarms.service'],check=True)
            if old_backend:subprocess.run(['systemctl','restart','radar-alarms.service'],check=True)
            for _ in range(20):
                try:health();break
                except Exception:time.sleep(.5)
            else:raise RuntimeError('Alarm health check failed')
            ALARM_SNIPPET.write_text(nginx)
            line=b'\ninclude /etc/nginx/snippets/radar-alarms.conf;\n'
            if b'include /etc/nginx/snippets/radar-alarms.conf;' not in old_snippet:SNIPPET.write_bytes(old_snippet+line)
            subprocess.run(['nginx','-t'],check=True)
            assert CURRENT.resolve()==old and state_digest()==states and pids()==services
            for name,digest in manifest['baseline'].items():assert sha((old/name).read_bytes())==digest
            switch(CURRENT,new)
            FALLBACK.write_bytes((new/'robot-push/index.html').read_bytes())
            subprocess.run(['systemctl','reload','nginx'],check=True)
            health();assert state_digest()==states and pids()==services
            after,after_links=inventory(new);assert after_links==links
            assert all(after[n]==h for n,h in manifest['files'].items())
            report=dict(release=str(new),previous=str(old),backup=str(backup),sourceCommits=manifest['sourceCommits'],staticFiles=len(manifest['files']),preservedFiles=len(original)-len(set(original)&set(manifest['files'])),existingServicesUnchanged=True,rulesAndBindingsPreserved=True,alarmService='active',fallbackMatchesBot=True)
            (backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
        except BaseException:
            if CURRENT.resolve()==new:switch(CURRENT,old)
            FALLBACK.write_bytes(fallback);SNIPPET.write_bytes(old_snippet)
            if old_alarm:ALARM_SNIPPET.write_bytes(old_alarm)
            else:ALARM_SNIPPET.unlink(missing_ok=True)
            if old_backend:
                switch(BACKEND/'current',old_backend)
                if old_service:Path('/etc/systemd/system/radar-alarms.service').write_bytes(old_service)
                subprocess.run(['systemctl','daemon-reload']);subprocess.run(['systemctl','restart','radar-alarms.service'])
            else:subprocess.run(['systemctl','disable','--now','radar-alarms.service'])
            subprocess.run(['nginx','-t'],check=True);subprocess.run(['systemctl','reload','nginx'],check=True)
            # Preserve any new alarm database and encryption key; never restore old user data.
            raise


if __name__=='__main__':main()
