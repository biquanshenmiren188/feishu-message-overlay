"""Publish only the standalone preview, preserving every existing asset and setting.

Run as root on the existing host: python3 deploy-settings-preview.py STAGE SOURCE_SHA
STAGE contains page/ (four static assets), SHA256SUMS.json, and this script.
No service reload, PWA edit, live preference write, or outbound notification occurs.
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

stage = Path(sys.argv[1]).resolve()
sha = sys.argv[2]
assert stage.parent == Path('/tmp') and stage.name.startswith('radar-settings-preview-')
assert re.fullmatch(r'[a-f0-9]{40}', sha)
expected = json.loads((stage / 'SHA256SUMS.json').read_text())
assert set(expected) == {'index.html', 'style.css', 'app.js', 'rules.js'}
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert all(digest(stage/'page'/name) == value for name, value in expected.items())

services = ['robot-push', 'radar-webpush-test']
def pids():
    return {name: subprocess.check_output(['systemctl','show',name,'--property=MainPID','--value'],text=True).strip() for name in services}

def private_configuration():
    # Keep actual identifiers, subscriptions and configuration in memory only.
    root=Path('/var/lib/radar-webpush-test')
    result={}
    for path in [root/'state.json', *sorted((root/'profiles').glob('*/state.json'))]:
        if not path.exists(): continue
        data=json.loads(path.read_text())
        live=data.get('live',{})
        result[str(path)]={k:data.get(k) for k in ('token','subscription','subscriptions')}
        result[str(path)].update(settings=live.get('settings'),revision=live.get('revision'))
    config=Path('/etc/radar-webpush-test/config.json')
    result['service_config_hash']=digest(config)
    return result

def static_inventory(root):
    return {str(p.relative_to(root)): digest(p) for p in root.rglob('*') if p.is_file()}

current=Path('/opt/funding-radar-web/current')
with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    old=current.resolve()
    assert old.parent == Path('/opt/funding-radar-web/releases')
    if (old/'robot-push/settings').exists():
        prior=json.loads((old/'settings-preview-source.json').read_text())
        assert prior['repository']=='biquanshenmiren188/feishu-message-overlay'
        assert set(prior['assets'])==set(expected)
        assert all(digest(old/'robot-push/settings'/name)==value for name,value in prior['assets'].items()), 'Preview assets changed outside the recorded release'
    before_pids=pids()
    assert all(int(v)>0 for v in before_pids.values())
    before_preferences=private_configuration()
    before_files={rel:value for rel,value in static_inventory(old).items() if not rel.startswith('robot-push/settings/') and rel!='settings-preview-source.json'}
    fallback=Path('/opt/radar-webpush-test/public/index.html')
    fallback_hash=digest(fallback)
    release_name='20261022-settings-preview-'+str(int(time.time()))
    new=old.parent/release_name
    backup=Path('/opt/funding-radar-web/backups')/release_name
    backup.mkdir(mode=0o700)
    (backup/'previous-release.txt').write_text(str(old)+'\n')
    (backup/'deployment.json').write_text(json.dumps({'source_sha':sha,'previous':str(old),'assets':expected},indent=2)+'\n')
    try:
        shutil.copytree(old,new,symlinks=True)
        target=new/'robot-push/settings'
        target.mkdir(mode=0o755,exist_ok=True)
        for name in expected:
            shutil.copyfile(stage/'page'/name,target/name)
            (target/name).chmod(0o644)
        manifest=new/'settings-preview-source.json'
        manifest.write_text(json.dumps({'source_sha':sha,'repository':'biquanshenmiren188/feishu-message-overlay','assets':expected},indent=2)+'\n')
        manifest.chmod(0o644)
        assert all(digest(new/rel)==value for rel,value in before_files.items())
        assert private_configuration()==before_preferences, 'Live settings changed during staging; aborting'
        link=current.with_name('current.settings-preview-next')
        link.symlink_to(new)
        os.replace(link,current)
        # Origin HTTP correctly requires Cloudflare Access. Verify via the
        # authorized browser after deployment, never bypass that access control.
        for name,value in expected.items():
            assert digest(current/'robot-push/settings'/name)==value
        assert pids()==before_pids, 'Service PID changed'
        assert private_configuration()==before_preferences, 'Live settings or binding changed'
        assert digest(fallback)==fallback_hash, 'PWA fallback changed'
        assert all(digest(current/rel)==value for rel,value in before_files.items())
        summary={'release':str(new),'previous':str(old),'backup':str(backup),'source_sha':sha,'asset_hashes_verified':True,'browser_verification':'pending','existing_files_preserved':len(before_files),'preferences_and_bindings_unchanged':True,'profile_count':len(before_preferences)-1,'service_pids_unchanged':True,'pwa_fallback_unchanged':True,'url':'https://leida.shenmiren.work/radar/robot-push/settings/'}
        (backup/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary))
    except Exception:
        if current.resolve()==new:
            rollback=current.with_name('current.settings-preview-rollback')
            rollback.symlink_to(old)
            os.replace(rollback,current)
        raise
