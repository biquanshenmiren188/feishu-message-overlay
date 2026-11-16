"""Apply only BOT service resource limits live, without restarting any service.

Run on the host with the deployment commit and --apply. No source/queue edits.
systemctl set-property persists overrides and updates the running cgroup.
"""
import fcntl, hashlib, json, re, sqlite3, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

SERVICE = 'radar-webpush-test.service'
OLD = {'CPUQuotaPerSecUSec': '200ms', 'MemoryMax': '134217728', 'TasksMax': '16'}
NEW = {'CPUQuotaPerSecUSec': '1s', 'MemoryMax': '268435456', 'TasksMax': '64'}

def show():
    raw = subprocess.check_output(['systemctl', 'show', SERVICE,
        '--property=' + ','.join(OLD)], text=True)
    return dict(line.split('=', 1) for line in raw.splitlines())

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def protected_state():
    root = Path('/var/lib/radar-webpush-test'); values = {}
    for p in [root/'state.json', *sorted((root/'profiles').glob('*/state.json'))]:
        data = json.loads(p.read_text()); live = data.get('live', {})
        values[str(p)] = {k: data.get(k) for k in ('token', 'subscription')}
        values[str(p)]['live'] = {k: live.get(k) for k in ('settings', 'revision')}
    for p in [root/'desktop-rules.json', *sorted((root/'profiles').glob('*/desktop-rules.json'))]:
        if p.exists():
            data = json.loads(p.read_text())
            values[str(p)] = {k:data.get(k) for k in ('desktop','cards','revision')}
    for p in [root/'profiles.json', Path('/etc/radar-webpush-test/config.json')]:
        values[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    with sqlite3.connect('file:/var/lib/radar-alarms/alarms.sqlite3?mode=ro', uri=True) as db:
        values['alarms'] = [db.execute(q).fetchall() for q in (
            'SELECT * FROM profiles ORDER BY id', 'SELECT id,profile,config FROM rules ORDER BY id',
            'SELECT * FROM devices ORDER BY id')]
    return digest(values)

def pids():
    return subprocess.check_output(['systemctl','show',SERVICE,'radar-alarms','robot-push',
        '--property=Id,MainPID'], text=True)

def main():
    source = sys.argv[1]; assert re.fullmatch('[a-f0-9]{40}', source)
    with open('/var/lib/funding-radar-storage/guard.lock', 'a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert show() == OLD, 'Unexpected resource baseline'
        before = protected_state(); services = pids()
        links = {p:str(Path(p).resolve()) for p in ('/opt/funding-radar-web/current','/opt/radar-alarms/current')}
        if '--apply' not in sys.argv:
            print(json.dumps(dict(preflight=True, before=OLD, after=NEW))); return
        backup = Path('/opt/radar-webpush-test') / ('backup-resource-budget-' + str(time.time_ns()))
        backup.mkdir(mode=0o700)
        (backup/'before.json').write_text(json.dumps(dict(source=source,limits=OLD,pids=services,links=links)))
        try:
            subprocess.run(['systemctl','set-property',SERVICE,'CPUQuota=100%','MemoryMax=256M','TasksMax=64'], check=True)
            assert show() == NEW
            assert before == protected_state(), 'Configuration changed during deployment'
            assert pids() == services, 'A service restarted'
            assert all(str(Path(p).resolve()) == target for p,target in links.items())
            for url in ('http://127.0.0.1:18885/radar/push-test/api/health',
                        'http://127.0.0.1:18886/radar/alarms-api/health'):
                with urlopen(url,timeout=10) as response: assert json.load(response)['ok']
            report = dict(source=source,before=OLD,after=NEW,backup=str(backup),
                servicesUnchanged=True,bindingsAndRulesPreserved=True,releases=links)
            (backup/'deployment.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report))
        except BaseException:
            # Only revert our exact applied values; never overwrite later edits.
            if show() == NEW:
                subprocess.run(['systemctl','set-property',SERVICE,'CPUQuota=20%','MemoryMax=128M','TasksMax=16'],check=True)
            raise

if __name__ == '__main__': main()
