"""BOT/PWA and shared card lifecycle release; run: python3 deploy.py STAGE SOURCE_SHA.

STAGE/deployment.json contains baselineCurrent (informational), baselineHashes
for every ASSETS entry, BOT index and current content-hash bundle, fallbackHash,
and stageHashes including all replacement assets. No user data is written.
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
import urllib.request
from patch_card_retention import patch_bundle
from pathlib import Path, PurePosixPath


ASSETS = ('robot-push/basispulse-model.js',)
BACKENDS = {'basispulse.py': Path('/opt/robot-push/basispulse.py'), 'desktop_rules.py': Path('/opt/radar-webpush-test/desktop_rules.py')}
SERVICES = ['basispulse', 'radar-webpush-test']
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
    # Only the two lifecycle services may restart; check all other running
    # service PIDs so an unexpected service change prevents a success report.
    units = subprocess.check_output(
        ['systemctl', 'list-units', '--type=service', '--state=running', '--no-legend', '--plain'],
        text=True)
    names = sorted(line.split()[0] for line in units.splitlines() if line.strip() and line.split()[0] not in {name+'.service' for name in SERVICES})
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
    require(len(sys.argv) == 3, 'Usage: deploy.py STAGE SOURCE_SHA')
    stage = Path(sys.argv[1]).resolve()
    sha = sys.argv[2]
    require(re.fullmatch(r'[a-f0-9]{40}', sha) is not None, 'Expected full source SHA')
    plan = json.loads((stage / 'deployment.json').read_text())
    require({*ASSETS, *BACKENDS, 'deploy.py', 'patch_card_retention.py'}.issubset(plan['stageHashes']), 'Replacement hashes missing')
    for name, expected in plan['stageHashes'].items():
        require(digest(stage / safe_relative(name)) == expected, 'Staging hash mismatch: ' + name)
    def restart_services():
        subprocess.run(['systemctl', 'start', *SERVICES], check=True)
        for attempt in range(35):
            try:
                with urllib.request.urlopen('http://127.0.0.1:18885/radar/push-test/api/health', timeout=2) as response:
                    require(json.load(response)['ok'], 'Web Push unhealthy')
                cache=json.loads(Path('/var/lib/robot-push/basispulse.json').read_text())
                if cache.get('snapshot',{}).get('retentionSeconds') == 30:
                    require(all(subprocess.check_output(['systemctl','is-active',service],text=True).strip()=='active' for service in SERVICES), 'Lifecycle services inactive')
                    return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError('Lifecycle services not ready')

    with open('/var/lib/funding-radar-storage/guard.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = CURRENT.resolve(strict=True)
        require(old.parent == Path('/opt/funding-radar-web/releases'), 'Unexpected current directory')
        old_index = (old / INDEX).read_bytes()
        refs = re.findall(rb'/radar/(performance-[^"\s<>]+/bot-cards-[a-f0-9]+\.js)', old_index)
        require(len(refs) == 1, 'Unexpected BOT bundle reference')
        old_bundle = safe_relative(refs[0].decode())
        required_baselines = {*ASSETS, INDEX, old_bundle}
        require(required_baselines.issubset(plan['baselineHashes']), 'Relevant baseline hashes missing')
        for name in required_baselines:
            require(digest(old / name) == plan['baselineHashes'][name], 'Production asset changed: ' + name)
        for name,path in BACKENDS.items():
            require(digest(path)==plan['backendHashes'][name], 'Backend changed: '+name)
        require(digest(FALLBACK) == plan['fallbackHash'], 'PWA fallback changed')
        old_fallback = FALLBACK.read_bytes()
        fallback_stat = FALLBACK.stat()
        source = (old / old_bundle).read_bytes()
        raw = patch_bundle(source)
        bundle = str(PurePosixPath(old_bundle).parent / ('bot-cards-' + hashlib.sha256(raw).hexdigest()[:12] + '.js'))
        old_ref = b'/radar/' + old_bundle.encode()
        new_ref = b'/radar/' + bundle.encode()
        require(old_index.count(old_ref) == old_fallback.count(old_ref) == 1,
                'BOT and PWA must both reference the verified bundle')
        require(not (old / bundle).exists(), 'Candidate bundle path already exists')
        index_raw = old_index.replace(old_ref, new_ref)
        fallback_raw = old_fallback.replace(old_ref, new_ref)
        before = user_settings()
        services = service_pids()
        name = '20261025-card-retention-' + str(int(time.time())) + '-' + uuid.uuid4().hex[:6]
        new = old.parent / name
        backup = Path('/opt/funding-radar-web/backups') / name
        backup.mkdir(mode=0o700)
        (backup / 'pwa-index.html').write_bytes(old_fallback)
        (backup / 'deployment.json').write_text(json.dumps(plan, indent=2))
        backend_metadata={}
        for filename,path in BACKENDS.items():
            (backup/filename).write_bytes(path.read_bytes());backend_metadata[filename]=path.stat()
        excluded = {*ASSETS, INDEX, MANIFEST}
        preserved = {str(path.relative_to(old)): digest(path) for path in old.rglob('*')
                     if path.is_file() and str(path.relative_to(old)) not in excluded}
        shutil.copytree(old, new, symlinks=True)
        for asset in ASSETS:
            require(not (new / asset).is_symlink(), 'Target asset must be a regular file')
            shutil.copyfile(stage / asset, new / asset)
        require(not (new / INDEX).is_symlink() and not (new / MANIFEST).is_symlink(),
                'Target metadata must be regular files')
        (new / bundle).write_bytes(raw)
        (new / INDEX).write_bytes(index_raw)
        manifest = json.loads((new / MANIFEST).read_text())
        # Preserve other source entries and record the lifecycle backend update.
        manifest.update(source_sha=sha, mode='shared-card-retention')
        manifest['card_retention'] = {'seconds': 30, 'source_sha': sha,
                                     'backends': {name: plan['stageHashes'][name] for name in BACKENDS}}
        manifest['assets'].update({asset: digest(new / asset) for asset in [*ASSETS, INDEX, bundle]})
        (new / MANIFEST).write_text(json.dumps(manifest, indent=2))
        require(all(digest(new / path) == expected for path, expected in preserved.items()),
                'Unrelated candidate assets changed')
        require(user_settings() == before, 'User settings changed during preparation')
        require(service_pids() == services, 'Service PIDs changed during preparation')
        require(CURRENT.resolve() == old and FALLBACK.read_bytes() == old_fallback,
                'Production entry changed during preparation')
        backends_changed = False
        switched = False
        fallback_written = False
        try:
            backends_changed=True
            subprocess.run(['systemctl','stop',*SERVICES],check=True)
            for filename,path in BACKENDS.items():
                atomic_bytes(path,(stage/filename).read_bytes(),backend_metadata[filename])
            switch_current(new)
            switched = True
            atomic_bytes(FALLBACK, fallback_raw, fallback_stat)
            fallback_written = True
            restart_services()
            require(CURRENT.resolve() == new, 'Current did not switch')
            require(FALLBACK.read_bytes() == fallback_raw, 'PWA fallback verification failed')
            require(Path('/opt/radar-webpush-test/public/settings').resolve() == new / 'robot-push/settings',
                    'PWA settings do not follow current')
            require(user_settings() == before, 'User settings changed during publication')
            require(service_pids() == services, 'Service PIDs changed during publication')
            result = dict(source_sha=sha, release=str(new), previous=str(old),
                          observedBaseline=plan.get('baselineCurrent'), backup=str(backup),
                          bundle=bundle, preservedFiles=len(preserved), rulesPreserved=True,
                          bindingsPreserved=True, unrelatedServicesUnchanged=True, restartedServices=SERVICES, pwaUpdated=True,
                          backendHashes={name:digest(path) for name,path in BACKENDS.items()},
                          assetHashes={asset: digest(new / asset) for asset in [*ASSETS, INDEX, bundle]},
                          fallbackHash=digest(FALLBACK))
            (backup / 'result.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
        except Exception:
            # Roll back code only; concurrent legitimate user edits are retained.
            try:
                if backends_changed:
                    subprocess.run(['systemctl','stop',*SERVICES],check=True)
                    for filename,path in BACKENDS.items():
                        atomic_bytes(path,(backup/filename).read_bytes(),backend_metadata[filename])
                    subprocess.run(['systemctl','start',*SERVICES],check=True)
                if switched:
                    switch_current(old)
            finally:
                if fallback_written or FALLBACK.read_bytes() != old_fallback:
                    atomic_bytes(FALLBACK, old_fallback, fallback_stat)
            raise


if __name__ == '__main__':
    main()
