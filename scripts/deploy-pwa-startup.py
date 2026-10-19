"""Incremental PWA startup deployment. Run on the existing host as root.

Prepare: python3 deploy-pwa-startup.py --stage /tmp/<task-stage>
Apply after candidate validation: add --apply --source-sha <pushed Git SHA>.
The stage must contain worker-source.js. No credentials or live data are packaged.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import urljoin, urlsplit

ROOT = Path('/opt/funding-radar-web')
PUBLIC = Path('/opt/radar-webpush-test/public')
NGINX = Path('/etc/nginx/snippets/radar-webpush-test.conf')
CACHE_CONF = Path('/etc/nginx/snippets/radar-startup-cache.conf')
INCLUDE = 'include /etc/nginx/snippets/radar-startup-cache.conf;'
ORIGIN = 'https://leida.shenmiren.work'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def asset_path(root, url):
    path = urlsplit(url).path
    assert path.startswith('/radar/')
    result = (root / path[len('/radar/'):]).resolve()
    assert result.is_relative_to(root.resolve()) and result.is_file(), path
    return result


def combine_css(root, html):
    links = re.findall(r'<link\b[^>]*rel="stylesheet"[^>]*>', html)
    assert len(links) >= 1, 'no stylesheets'
    parts = []
    for tag in links:
        href = re.search(r'href="([^"]+)"', tag)[1]
        url = urljoin(ORIGIN + '/radar/robot-push/', href)
        assert urlsplit(url).netloc == urlsplit(ORIGIN).netloc
        css = asset_path(root, url).read_text()
        assert '@import' not in css, 'resolve imports explicitly before deployment'

        def rebase(match):
            target = match[1].strip().strip('\'"')
            if target.startswith(('data:', '#', '/', 'http:', 'https:')):
                return match[0]
            full = urlsplit(urljoin(url, target))
            return 'url("' + full.path + ('?' + full.query if full.query else '') + ('#' + full.fragment if full.fragment else '') + '")'

        parts.append(re.sub(r'url\(([^)]+)\)', rebase, css))
    raw = ('\n'.join(parts) + '\n').encode()
    url = '/radar/robot-push/startup-assets/bot-shell-' + sha(raw)[:12] + '.css'
    updated = html.replace(links[0], '<link rel="stylesheet" href="' + url + '">', 1)
    for tag in links[1:]:
        updated = updated.replace(tag, '', 1)
    return updated, url, raw, len(links)


def build(stage):
    old = (ROOT / 'current').resolve()
    original_html = (old / 'robot-push/index.html').read_bytes()
    original_worker = (PUBLIC / 'sw.js').read_bytes()
    source = (stage / 'worker-source.js').read_text()
    # Current production has additional push diagnostics not yet in main.
    # Keep its complete notification/database implementation byte-for-byte.
    marker = b'function db()'
    assert original_worker.count(marker) == 1 and source.count(marker.decode()) == 1
    worker = source.split(marker.decode(), 1)[0].encode() + marker + original_worker.split(marker, 1)[1]
    html, css_url, css, count = combine_css(old, original_html.decode())
    assert '<base href="/radar/robot-push/">' in html and 'id="feed"' in html
    assert re.search(r'<section\b[^>]*id="feed"[^>]*>\s*</section>', html)
    urls = [css_url]
    for path in re.findall(r'(?:src|href)="(/radar/[^"?]+)"', html):
        match = re.search(r'-([a-f0-9]{12,64})\.(?:js|css)$', path)
        if match and path != css_url:
            raw = asset_path(old, path).read_bytes()
            assert sha(raw).startswith(match[1]), 'hash filename mismatch: ' + path
            urls.append(path)
    rules = ['# Generated exact routes for verified content-hashed BOT assets.']
    for path in sorted(set(urls)):
        assert re.fullmatch(r'/radar/[a-zA-Z0-9_./-]+', path)
        rules.extend([
            'location = ' + path + ' {',
            '    alias /opt/funding-radar-web/current/' + path[len('/radar/'):] + ';',
            '    add_header Cache-Control "private, max-age=31536000, immutable";',
            '    add_header X-Content-Type-Options nosniff;',
            '}',
        ])
    old_nginx = NGINX.read_bytes()
    nginx = old_nginx.decode()
    if INCLUDE not in nginx:
        nginx += '\n' + INCLUDE + '\n'
    payload = {'bot.html': html.encode(), 'shell.css': css, 'sw.js': worker,
               'cache.conf': ('\n'.join(rules) + '\n').encode(), 'nginx.conf': nginx.encode()}
    for name, raw in payload.items():
        (stage / name).write_bytes(raw)
    baseline = {
        'previous': str(old), 'htmlSha': sha(original_html), 'workerSha': sha(original_worker),
        'nginxSha': sha(old_nginx), 'manifestSha': sha((PUBLIC / 'manifest.webmanifest').read_bytes()),
        'cacheConfSha': sha(CACHE_CONF.read_bytes()) if CACHE_CONF.exists() else None,
        'cssUrl': css_url, 'headStylesBefore': count, 'headStylesAfter': 1,
        'hashes': {name: sha(raw) for name, raw in payload.items()},
        'notificationSuffixPreserved': worker.split(marker, 1)[1] == original_worker.split(marker, 1)[1],
        'immutableUrls': sorted(set(urls)),
    }
    (stage / 'candidate.json').write_text(json.dumps(baseline, indent=2))
    return baseline


def identity_digest():
    # Compare private state without printing, staging, or copying credentials.
    root = Path('/var/lib/radar-webpush-test')
    result = {}
    for path in [root / 'state.json', *sorted((root / 'profiles').glob('*/state.json'))]:
        data = json.loads(path.read_text())
        result[str(path.relative_to(root))] = {k: data.get(k) for k in ['token', 'subscription']}
        result[str(path.relative_to(root))]['settings'] = data.get('live', {}).get('settings')
    return sha(json.dumps(result, sort_keys=True).encode())


def atomic_write(path, raw):
    temporary = path.with_name(path.name + '.startup-next')
    temporary.write_bytes(raw)
    temporary.chmod(0o644)
    os.replace(temporary, path)


def switch(target):
    temporary = ROOT / 'current.startup-next'
    temporary.symlink_to(target)
    os.replace(temporary, ROOT / 'current')


def apply(stage, source_sha):
    assert re.fullmatch(r'[a-f0-9]{40}', source_sha), 'full pushed commit required'
    data = json.loads((stage / 'candidate.json').read_text())
    old = Path(data['previous'])
    targets = {'sw.js': PUBLIC / 'sw.js', 'index.html': PUBLIC / 'index.html',
               'nginx.conf': NGINX, 'cache.conf': CACHE_CONF}
    with open('/var/lib/funding-radar-storage/guard.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert (ROOT / 'current').resolve() == old, 'release changed; reprepare'
        assert sha((old / 'robot-push/index.html').read_bytes()) == data['htmlSha']
        assert sha((PUBLIC / 'sw.js').read_bytes()) == data['workerSha']
        assert sha(NGINX.read_bytes()) == data['nginxSha']
        assert sha((PUBLIC / 'manifest.webmanifest').read_bytes()) == data['manifestSha']
        assert (sha(CACHE_CONF.read_bytes()) if CACHE_CONF.exists() else None) == data['cacheConfSha']
        assert all(sha((stage / name).read_bytes()) == digest for name, digest in data['hashes'].items())
        pids = {name: command(['systemctl', 'show', name, '-p', 'MainPID', '--value'])
                for name in ['robot-push', 'radar-webpush-test']}
        identity = identity_digest()
        version = '20261019-pwa-startup-' + str(int(time.time()))
        release = ROOT / 'releases' / version
        backup = ROOT / 'backups' / version
        backup.mkdir(mode=0o700)
        existing = {name: target.exists() for name, target in targets.items()}
        for name, target in targets.items():
            if target.exists():
                shutil.copyfile(target, backup / name)
        try:
            shutil.copytree(old, release, symlinks=True)
            (release / 'robot-push/index.html').write_bytes((stage / 'bot.html').read_bytes())
            css = release / data['cssUrl'][len('/radar/'):]
            css.parent.mkdir(parents=True, exist_ok=True)
            css.write_bytes((stage / 'shell.css').read_bytes())
            preserved = 0
            for path in old.rglob('*'):
                if path.is_file() and path.relative_to(old).as_posix() != 'robot-push/index.html':
                    assert sha(path.read_bytes()) == sha((release / path.relative_to(old)).read_bytes()), str(path)
                    preserved += 1
            atomic_write(PUBLIC / 'index.html', (stage / 'bot.html').read_bytes())
            atomic_write(PUBLIC / 'sw.js', (stage / 'sw.js').read_bytes())
            atomic_write(NGINX, (stage / 'nginx.conf').read_bytes())
            atomic_write(CACHE_CONF, (stage / 'cache.conf').read_bytes())
            command(['nginx', '-t'])
            switch(release)
            command(['systemctl', 'reload', 'nginx'])
            assert identity_digest() == identity, 'binding/settings changed during deploy'
            assert all(command(['systemctl', 'show', name, '-p', 'MainPID', '--value']) == pid for name, pid in pids.items())
            assert sha((PUBLIC / 'manifest.webmanifest').read_bytes()) == data['manifestSha']
            result = {**data, 'release': str(release), 'backup': str(backup), 'sourceSha': source_sha,
                      'preservedFiles': preserved, 'subscriptionSettingsPreserved': True, 'servicesUnchanged': True}
            (release / 'pwa-startup-release.json').write_text(json.dumps(result, indent=2))
            (backup / 'deployment.json').write_text(json.dumps(result, indent=2))
            (stage / 'deployed.json').write_text(json.dumps(result, indent=2))
            return result
        except Exception:
            for name, target in targets.items():
                if existing[name]:
                    atomic_write(target, (backup / name).read_bytes())
                elif target.exists():
                    target.unlink()
            if (ROOT / 'current').resolve() == release:
                switch(old)
            command(['nginx', '-t'])
            command(['systemctl', 'reload', 'nginx'])
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--source-sha', default='')
    args = parser.parse_args()
    print(json.dumps(apply(args.stage, args.source_sha) if args.apply else build(args.stage), indent=2))
