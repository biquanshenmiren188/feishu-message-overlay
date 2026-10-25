"""Static-only BOT/PWA release; run as: python3 deploy.py STAGE SOURCE_SHA.

STAGE/deployment.json contains baselineCurrent (informational), baselineHashes
for inspected existing files, fallbackHash, and stageHashes for the new viewer
and patched entry HTML. No user data is written.
An unrelated release can advance current if every relevant baseline hash is
unchanged; its other files and manifest entries are retained in the new clone.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath


ASSETS = ('robot-push/blocked-pushes.js','robot-push/blocked-pushes.css')
INDEX = 'robot-push/index.html'
MANIFEST = 'settings-preview-source.json'

CURRENT = Path('/opt/funding-radar-web/current')
FALLBACK = Path('/opt/radar-webpush-test/public/index.html')
STATE = Path('/var/lib/radar-webpush-test')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def safe_relative(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and str(path) == name,
            'Unsafe staging path')
    return name


def user_settings():
    # Keep secrets only in memory; polling receipts and delivery counters are
    # intentionally excluded, while every profile's preferences are checked.
    result = {}
    for path in [STATE / 'state.json', *sorted((STATE / 'profiles').glob('*/state.json'))]:
        data = json.loads(path.read_text())
        live = data.get('live', {})
        result[str(path)] = {key: data.get(key) for key in ('token', 'subscription', 'subscriptions')}
        result[str(path)].update(settings=live.get('settings'), revision=live.get('revision'))
    for path in [STATE / 'desktop-rules.json', *sorted((STATE / 'profiles').glob('*/desktop-rules.json'))]:
        if path.exists():
            data = json.loads(path.read_text())
            result[str(path)] = {key: data.get(key) for key in ('desktop', 'cards', 'revision', 'coinOperations')}
    for path in [STATE / 'profiles.json', Path('/etc/radar-webpush-test/config.json')]:
        if path.exists():
            result[str(path)] = digest(path)
    return result


def service_pids():
    # The patch never invokes start/stop/restart; check all currently running
    # service PIDs so an unexpected service change prevents a success report.
    units = subprocess.check_output(
        ['systemctl', 'list-units', '--type=service', '--state=running', '--no-legend', '--plain'],
        text=True)
    names = sorted(line.split()[0] for line in units.splitlines() if line.strip())
    require(bool(names), 'No running services found')
    return subprocess.check_output(['systemctl', 'show', *names, '--property=Id,MainPID'], text=True)


def atomic_bytes(path, raw, metadata):
    temporary = path.with_name(path.name + '.manual-save-' + uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(metadata.st_mode))
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def switch_current(target):
    temporary = CURRENT.with_name('current.manual-save-' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, CURRENT)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    from prepare_blocked_pushes import patch_html
    require(len(sys.argv)==3,'Usage: deploy.py STAGE SOURCE_SHA')
    stage=Path(sys.argv[1]).resolve();sha=sys.argv[2]
    require(re.fullmatch(r'[a-f0-9]{40}',sha) is not None,'Expected source SHA')
    plan=json.loads((stage/'deployment.json').read_text())
    require(plan['sourceCommit']==sha,'Source mismatch')
    require({*ASSETS,INDEX,'pwa-index.html'}.issubset(plan['stageHashes']),'Missing assets')
    for name,expected in plan['stageHashes'].items():
        require(digest(stage/safe_relative(name))==expected,'Stage mismatch: '+name)
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        old=CURRENT.resolve(strict=True)
        require(old.parent==Path('/opt/funding-radar-web/releases'),'Unexpected release path')
        for name,expected in plan['baselineHashes'].items():
            require(digest(old/safe_relative(name))==expected,'Production changed: '+name)
        require(digest(FALLBACK)==plan['fallbackHash'],'PWA changed')
        require(all(not (old/a).exists() for a in ASSETS),'Viewer already deployed; inspect first')
        old_fallback=FALLBACK.read_bytes();fallback_stat=FALLBACK.stat()
        index_raw=patch_html((old/INDEX).read_bytes());fallback_raw=patch_html(old_fallback)
        require(index_raw==(stage/INDEX).read_bytes() and fallback_raw==(stage/'pwa-index.html').read_bytes(),'Untested HTML')
        before=user_settings();services=service_pids()
        name='20261025-blocked-pushes-'+str(int(time.time()))+'-'+uuid.uuid4().hex[:6]
        new=old.parent/name;backup=Path('/opt/funding-radar-web/backups')/name
        backup.mkdir(mode=0o700);(backup/'pwa-index.html').write_bytes(old_fallback)
        (backup/'deployment.json').write_text(json.dumps(plan,indent=2))
        preserved={str(p.relative_to(old)):digest(p) for p in old.rglob('*') if p.is_file() and str(p.relative_to(old)) not in {INDEX,MANIFEST}}
        shutil.copytree(old,new,symlinks=True)
        for asset in ASSETS:shutil.copyfile(stage/asset,new/asset)
        require(not (new/INDEX).is_symlink() and not (new/MANIFEST).is_symlink(),'Unexpected metadata symlink')
        (new/INDEX).write_bytes(index_raw)
        manifest=json.loads((new/MANIFEST).read_text())
        manifest.update(source_sha=sha,mode='blocked-pushes')
        manifest['assets'].update({a:digest(new/a) for a in [*ASSETS,INDEX]})
        (new/MANIFEST).write_text(json.dumps(manifest,indent=2))
        require(all(digest(new/p)==h for p,h in preserved.items()),'Unrelated assets changed')
        require(before==user_settings() and services==service_pids(),'Settings or services changed')
        require(CURRENT.resolve()==old and FALLBACK.read_bytes()==old_fallback,'Release changed during preparation')
        switched=False
        try:
            switch_current(new);switched=True
            atomic_bytes(FALLBACK,fallback_raw,fallback_stat)
            require(CURRENT.resolve()==new and FALLBACK.read_bytes()==fallback_raw,'Entry verification failed')
            require(Path('/opt/radar-webpush-test/public/settings').resolve()==new/'robot-push/settings','Settings link mismatch')
            require(user_settings()==before and service_pids()==services,'Settings or services changed')
            result=dict(source_sha=sha,release=str(new),previous=str(old),backup=str(backup),preservedFiles=len(preserved),rulesPreserved=True,bindingsPreserved=True,servicesUnchanged=True,pwaUpdated=True,assetHashes={a:digest(new/a) for a in [*ASSETS,INDEX]},fallbackHash=digest(FALLBACK))
            (backup/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
        except Exception:
            if switched:switch_current(old)
            if FALLBACK.read_bytes()!=old_fallback:atomic_bytes(FALLBACK,old_fallback,fallback_stat)
            raise


if __name__=='__main__':main()


