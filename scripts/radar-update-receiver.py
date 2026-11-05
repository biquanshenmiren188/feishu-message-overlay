#!/usr/bin/env python3
"""Forced SSH command: receive a bounded verified ZIP, sign, atomically publish.

No shell commands or paths are accepted from SSH_ORIGINAL_COMMAND or the client.
Signing key is root-only and never leaves the server. Run tests without production paths.
"""
import base64
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path('/var/lib/radar-desktop-updates')
KEY = Path('/etc/radar-desktop-update/signing.pem')
MAXIMUM = 256 * 1024 * 1024

def version(tag):
    if not isinstance(tag, str) or not re.fullmatch(r'v\d{4}\.\d{2}\.\d{2}\.\d{1,6}', tag):
        raise ValueError('Invalid version')
    v = tuple(map(int, tag[1:].split('.')))
    datetime.date(*v[:3])
    return v

def validate_metadata(meta):
    version(meta['Version'])
    if type(meta['Size']) is not int or not 0 < meta['Size'] <= MAXIMUM:
        raise ValueError('Invalid size')
    for field, pattern in [('Sha256', r'[a-f0-9]{64}'), ('SourceCommit', r'[a-f0-9]{40}')]:
        if not re.fullmatch(pattern, meta[field]):
            raise ValueError('Invalid ' + field)
    return {k: meta[k] for k in ('Version', 'Size', 'Sha256', 'SourceCommit')} | {'Protocol': 1}

def validate_package(path, tag):
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if not 0 < len(entries) <= 30000 or sum(e.file_size for e in entries) > 1024**3:
            raise ValueError('ZIP limits exceeded')
        names = set()
        for entry in entries:
            name = entry.filename.rstrip('/')
            parts = name.split('/')
            if (not name or '\\' in name or ':' in name or name.startswith('/')
                    or any(p in ('', '.', '..') or p.endswith(('.', ' ')) or re.match(r'^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)', p, re.I) for p in parts)
                    or name.casefold() in names or ((entry.external_attr >> 16) & 0xF000) == 0xA000
                    or entry.external_attr & 0x400):
                raise ValueError('Unsafe ZIP entry')
            if name.casefold() == 'storage-location.json' or name.lower().endswith('.dpapi') or PurePosixPath(name).name.lower() == '.env':
                raise ValueError('Private configuration in ZIP')
            names.add(name.casefold())
        if z.getinfo('update-manifest.json').file_size > 8*1024*1024:
            raise ValueError('Manifest too large')
        manifest = json.loads(z.read('update-manifest.json'))
        files = manifest['Files']
        if manifest['Protocol'] != 1 or manifest['Version'] != tag or 'FeishuMessageOverlay.exe' not in files:
            raise ValueError('Invalid manifest')
        actual = {e.filename for e in entries if not e.is_dir() and e.filename != 'update-manifest.json'}
        if actual != set(files):
            raise ValueError('Unlisted package files')
        for name, expected in files.items():
            with z.open(name) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != expected.lower():
                raise ValueError('Manifest hash mismatch')

def receive(stream, root=ROOT, key=KEY):
    line = stream.readline(4097)
    if len(line) > 4096 or not line.endswith(b'\n'):
        raise ValueError('Invalid header')
    meta = validate_metadata(json.loads(line))
    root.mkdir(parents=True, exist_ok=True)
    with open(root / '.publish.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        latest = root / 'latest.json'
        current = None
        if latest.exists():
            current = json.loads(base64.b64decode(json.loads(latest.read_bytes())['payload']))
            if version(meta['Version']) < version(current['Version']):
                raise ValueError('Refusing release downgrade')
        stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
        try:
            name = 'FeishuMessageOverlay-' + meta['Version'] + '-win-x64.zip'
            package = stage / name
            remaining = meta['Size']
            with package.open('wb') as target:
                while remaining:
                    block = stream.read(min(65536, remaining))
                    if not block:
                        raise ValueError('Incomplete upload')
                    remaining -= len(block)
                    target.write(block)
                target.flush(); os.fsync(target.fileno())
            if stream.read(1):
                raise ValueError('Trailing upload data')
            with package.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != meta['Sha256']:
                    raise ValueError('Upload checksum mismatch')
            validate_package(package, meta['Version'])
            destination = root / meta['Version']
            if destination.exists():
                existing = json.loads(base64.b64decode(json.loads((destination / 'release.json').read_bytes())['payload']))
                if existing != meta:
                    raise ValueError('Published versions are immutable')
                envelope = (destination / 'release.json').read_bytes()
            else:
                payload = json.dumps(meta, separators=(',', ':'), sort_keys=True).encode()
                signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key), '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:32'], input=payload, check=True, capture_output=True).stdout
                envelope = json.dumps({'payload': base64.b64encode(payload).decode(), 'signature': base64.b64encode(signed).decode()}, separators=(',', ':')).encode()
                (stage / 'release.json').write_bytes(envelope)
                (stage / 'SHA256SUMS.txt').write_text(meta['Sha256'] + '  ' + name + '\n')
                for path in stage.iterdir():
                    path.chmod(0o644)
                stage.chmod(0o755)
                os.rename(stage, destination)
            # Keep the previous signed latest for explicit operator recovery.
            if latest.exists() and (not current or current['Version'] != meta['Version']):
                shutil.copy2(latest, root / 'previous.json')
            pending = root / '.latest.tmp'
            with pending.open('wb') as out:
                out.write(envelope); out.flush(); os.fsync(out.fileno())
            pending.chmod(0o644)
            os.replace(pending, latest)
            fd = os.open(root, os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
            return {'published': meta['Version'], 'sha256': meta['Sha256'], 'sourceCommit': meta['SourceCommit']}
        finally:
            if stage.exists():
                shutil.rmtree(stage)

if __name__ == '__main__':
    signal.alarm(600)
    try:
        print(json.dumps(receive(sys.stdin.buffer)))
    except Exception as error:
        print('Publication rejected: ' + str(error), file=sys.stderr)
        sys.exit(1)
