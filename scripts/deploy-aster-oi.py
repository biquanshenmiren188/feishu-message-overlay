"""Patch only the shared OI reader; preserve static release, rules and bindings.

Run on host: python3 deploy-aster-oi.py STAGE SOURCE_SHA
STAGE contains advanced_rules.py and plan.json with old/new SHA256 hashes.
Candidate checks must pass before publication. Rollback restores code only.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.request

TARGET=Path('/opt/radar-webpush-test/advanced_rules.py')
STATE=Path('/var/lib/radar-webpush-test')
CURRENT=Path('/opt/funding-radar-web/current')
SERVICE='radar-webpush-test'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def settings_digest():
    values={}
    for path in [STATE/'state.json',*sorted((STATE/'profiles').glob('*/state.json'))]:
        if not path.exists():continue
        data=json.loads(path.read_text());live=data.get('live',{})
        values[str(path)]={key:data.get(key) for key in ('token','subscription','subscriptions')}
        values[str(path)].update(settings=live.get('settings'),revision=live.get('revision'))
    for path in [STATE/'desktop-rules.json',*sorted((STATE/'profiles').glob('*/desktop-rules.json'))]:
        if path.exists():
            data=json.loads(path.read_text())
            values[str(path)]={key:data.get(key) for key in ('desktop','cards','revision','coinOperations')}
    for path in [STATE/'profiles.json',Path('/etc/radar-webpush-test/config.json')]:
        if path.exists():values[str(path)]=digest(path)
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()

def other_pids():
    units=subprocess.check_output(['systemctl','list-units','--type=service','--state=running','--no-legend','--plain'],text=True)
    names=sorted(line.split()[0] for line in units.splitlines() if line.strip() and line.split()[0]!=SERVICE+'.service')
    return subprocess.check_output(['systemctl','show',*names,'--property=Id,MainPID'],text=True)

def atomic(raw, metadata):
    temporary=TARGET.with_suffix('.oi-next')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,stat.S_IMODE(metadata.st_mode));os.chown(temporary,metadata.st_uid,metadata.st_gid)
        os.replace(temporary,TARGET)
    finally:temporary.unlink(missing_ok=True)

def healthy():
    for _ in range(20):
        try:
            with urllib.request.urlopen('http://127.0.0.1:18885/radar/push-test/api/health',timeout=2) as r:
                if json.load(r).get('ok'):return
        except (OSError,ValueError):pass
        time.sleep(1)
    raise RuntimeError('Web Push health check failed')

def main():
    stage=Path(sys.argv[1]).resolve();sha=sys.argv[2]
    assert re.fullmatch('[a-f0-9]{40}',sha),'Invalid source SHA'
    plan=json.loads((stage/'plan.json').read_text())
    assert digest(stage/'advanced_rules.py')==plan['candidate'],'Candidate hash mismatch'
    assert json.loads((stage/'validation.json').read_text())['candidateHash']==plan['candidate'],'Candidate not validated'
    compile((stage/'advanced_rules.py').read_bytes(),str(TARGET),'exec')
    with open('/var/lib/funding-radar-storage/guard.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert digest(TARGET)==plan['baseline'],'Live code changed'
        current=str(CURRENT.resolve());pids=other_pids();before=settings_digest()
        backup=Path('/opt/funding-radar-web/backups')/('20261026-aster-oi-'+str(int(time.time())))
        backup.mkdir(mode=0o700)
        old=TARGET.read_bytes();metadata=TARGET.stat()
        (backup/'advanced_rules.py').write_bytes(old)
        (backup/'plan.json').write_text(json.dumps(plan,indent=2))
        stopped=False
        try:
            stopped=True
            subprocess.run(['systemctl','stop',SERVICE],check=True)
            assert settings_digest()==before,'Rules/bindings changed; no code applied'
            atomic((stage/'advanced_rules.py').read_bytes(),metadata)
            subprocess.run(['systemctl','start',SERVICE],check=True);healthy()
            assert digest(TARGET)==plan['candidate'],'Installed hash mismatch'
            assert str(CURRENT.resolve())==current,'Static release changed'
            assert settings_digest()==before,'Rules/bindings changed during publication'
            assert other_pids()==pids,'Unrelated service changed'
            result=dict(source_sha=sha,backendHash=digest(TARGET),backup=str(backup),
                        staticRelease=current,staticReleaseUnchanged=True,rulesAndBindingsPreserved=True,
                        unrelatedServicesUnchanged=True,restartedServices=[SERVICE])
            (backup/'result.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result))
        except BaseException:
            if stopped:
                subprocess.run(['systemctl','stop',SERVICE],check=True)
                atomic(old,metadata)
                subprocess.run(['systemctl','start',SERVICE],check=True);healthy()
            raise

if __name__=='__main__':main()
