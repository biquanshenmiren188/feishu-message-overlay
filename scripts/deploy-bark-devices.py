"""Guarded multi-device migration; preserve bindings, rules and unrelated assets.

Run on the authorized host: python deploy-bark-devices.py STAGE [--apply].
Rollback transforms the CURRENT device rows, never restores stale user data.
"""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location('base', Path(__file__).with_name('deploy-price-alarms.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
DATA = Path('/var/lib/radar-alarms')
DB = DATA / 'alarms.sqlite3'
PYTHON = '/opt/radar-webpush-test/venv/bin/python'


def config(path=DB):
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        value = {name: db.execute('SELECT ' + cols + ' FROM ' + name + ' ORDER BY ' + order).fetchall()
                 for name, cols, order in [('profiles', '*', 'id'), ('rules', 'id,profile,config,created', 'id'),
                                          ('devices', 'profile,fingerprint,secret,label', 'profile,fingerprint')]}
        return base.sha(json.dumps(value, sort_keys=True).encode())


def snapshot(target):
    with sqlite3.connect(DB) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    target.chmod(0o600)


def legacy_schema():
    # Called only with the alarm service stopped. Preserve all CURRENT user changes.
    with sqlite3.connect(DB) as db:
        if 'id' not in {r[1] for r in db.execute('PRAGMA table_info(devices)')}:
            return
        if db.execute('SELECT 1 FROM devices GROUP BY profile HAVING COUNT(*)>1').fetchone():
            raise RuntimeError('Multiple devices now exist: old backend rollback refused; retain new backend')
        db.execute('BEGIN IMMEDIATE')
        db.execute('ALTER TABLE devices RENAME TO devices_multi')
        db.execute('CREATE TABLE devices (profile TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, secret TEXT NOT NULL, label TEXT NOT NULL)')
        db.execute('INSERT INTO devices SELECT profile,fingerprint,secret,label FROM devices_multi')
        db.execute('DROP TABLE devices_multi')


stage = Path(sys.argv[1]).resolve(); m = json.loads((stage / 'manifest.json').read_text())
expected = {'robot-push/alarms/' + n for n in ('index.html', 'app.js', 'snapshot.js', 'devices.js', 'devices.css')}
assert set(m['files']) == expected
assert set(m['backend']) == set(m['backendBaseline']) | {'test_devices.py'}
for kind in ('files', 'backend'):
    for name, digest in m[kind].items():
        assert base.sha((stage / ('static' if kind == 'files' else 'backend') / name).read_bytes()) == digest, name
subprocess.run([PYTHON, '-m', 'unittest', 'discover', '-s', str(stage / 'backend'), '-p', 'test_*.py'], check=True)

with open('/var/lib/funding-radar-storage/guard.lock', 'a') as guard:
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    old = base.CURRENT.resolve(); oldb = Path('/opt/radar-alarms/current').resolve()
    assert str(old) == m['previous'] and str(oldb) == m['previousBackend']
    for name, digest in m['baseline'].items(): assert base.sha((old / name).read_bytes()) == digest, name
    for name, digest in m['backendBaseline'].items(): assert base.sha((oldb / name).read_bytes()) == digest, name
    for name in expected - set(m['baseline']): assert not (old / name).exists(), name
    # Rehearse migration against a private copy of actual production data, with no sender.
    with tempfile.TemporaryDirectory(prefix='radar-device-migration-') as temp:
        root = Path(temp); snapshot(root / 'alarms.sqlite3')
        shutil.copyfile(DATA / 'bark-encryption.key', root / 'bark-encryption.key')
        (root / 'bark-encryption.key').chmod(0o600)
        before_copy = config(root / 'alarms.sqlite3')
        subprocess.run([PYTHON, '-c', 'import sys;sys.path.insert(0,sys.argv[1]);from store import Store;s=Store(sys.argv[2]);s.db.close()', str(stage / 'backend'), str(root)], check=True)
        assert before_copy == config(root / 'alarms.sqlite3'), 'Migration changed existing bindings/rules'
    if '--apply' not in sys.argv:
        print('Preflight and production-copy migration passed'); sys.exit(0)
    label = '20261114-bark-devices-' + str(time.time_ns())
    new = base.ROOT / 'releases' / label
    newb = Path('/opt/radar-alarms/releases') / m['source']
    backup = base.ROOT / 'backups' / label; backup.mkdir(mode=0o700)
    (backup / 'manifest.json').write_text(json.dumps(m, indent=2))
    original, links = base.inventory(old); states = base.state_digest(); services = base.pids(); before = config()
    snapshot(backup / 'alarms.sqlite3')
    shutil.copytree(old, new, symlinks=True)
    shutil.copytree(oldb, newb, ignore=shutil.ignore_patterns('__pycache__'))
    for kind, destination in (('files', new), ('backend', newb)):
        for name in m[kind]:
            target = destination / name; assert not target.is_symlink()
            shutil.copyfile(stage / ('static' if kind == 'files' else 'backend') / name, target); target.chmod(0o644)
    copied, copied_links = base.inventory(new)
    assert copied_links == links
    assert all(copied[n] == h for n, h in original.items() if n not in expected and n != 'market-display-cache.json')
    try:
        base.switch(Path('/opt/radar-alarms/current'), newb)
        subprocess.run(['systemctl', 'restart', 'radar-alarms'], check=True)
        for _ in range(40):
            try:
                health = json.load(urlopen('http://127.0.0.1:18886/radar/alarms-api/health', timeout=2))
                assert health['version'] == 13 and health['multiDevice'] is True
                assert health['repeatIntervalSeconds'] == 30 and health['notificationLevel'] == 'critical'
                assert health['fallbackMultiSelect'] is True and health['denominationConversion'] is True
                break
            except Exception: time.sleep(.5)
        else: raise RuntimeError('New backend health failed')
        assert before == config(), 'Existing bindings/rules changed during deployment'
        assert base.CURRENT.resolve() == old and states == base.state_digest() and services == base.pids()
        base.switch(base.CURRENT, new)
        assert before == config() and states == base.state_digest() and services == base.pids()
        for kind, destination in (('files', new), ('backend', newb)):
            assert all(base.sha((destination / n).read_bytes()) == h for n, h in m[kind].items())
        report = dict(release=str(new), previous=str(old), backend=str(newb), previousBackend=str(oldb), source=m['source'],
                      health=health, rulesAndBindingsPreserved=True, productionCopyMigrationPassed=True,
                      unrelatedServicesUnchanged=True, preservedStaticFiles=len(original) - len(expected & set(original)))
        (backup / 'deployment.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report))
    except BaseException:
        if base.CURRENT.resolve() == new: base.switch(base.CURRENT, old)
        subprocess.run(['systemctl', 'stop', 'radar-alarms'], check=True)
        try:
            legacy_schema()
            base.switch(Path('/opt/radar-alarms/current'), oldb)
        finally:
            subprocess.run(['systemctl', 'start', 'radar-alarms'], check=True)
        raise
