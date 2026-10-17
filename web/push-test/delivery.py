"""Apple transport policy and non-secret subscription identity."""
import hashlib
import json
import os
import time
from urllib.parse import urlsplit

TTL = 300
TOPIC = 'radar-bot-latest'


def fingerprint(subscription):
    if not subscription:
        return None
    # Match the browser's stable JSON order; never return the endpoint or keys.
    raw = json.dumps([subscription['endpoint'], subscription['keys']['p256dh'],
                      subscription['keys']['auth']], separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def with_fallback(payload, origin):
    """Retain legacy worker fields; Apple can display even if its JS cannot run."""
    return dict(payload, web_push=8030, mutable=True, notification={
        'title': '雷达', 'body': '\n'.join(payload['rows']),
        'navigate': origin+'/radar/push-test/', 'tag': TOPIC, 'silent': False,
        # Older WebKit releases looked inside notification instead of the root.
        'mutable': True, 'data': {'kind': payload['kind'], 'seq': payload['seq'],
                                  'run': payload['run'], 'url': '/radar/push-test/'}})


def vapid_headers(directory, key_path, endpoint, origin, signer=None, now=None):
    """Apple requires JWT reuse for >=1 hour, including across service restarts."""
    from pathlib import Path
    now = time.time() if now is None else now
    u = urlsplit(endpoint)
    audience = f'{u.scheme}://{u.netloc}'
    key_hash = hashlib.sha256(Path(key_path).read_bytes()).hexdigest()
    path = directory/'vapid-cache.json'
    try:
        cache = json.loads(path.read_text())
    except (OSError, ValueError):
        cache = {}
    item = cache.get(audience, {})
    if (item.get('key') == key_hash and 0 <= now-item.get('at', 0) < 3600
            and item.get('expires', 0) > now+60 and isinstance(item.get('headers'), dict)):
        return item['headers'].copy()
    if signer is None:
        from py_vapid import Vapid
        signer = Vapid.from_file(private_key_file=key_path).sign
    expires = int(now)+12*3600
    headers = signer({'aud': audience, 'sub': origin, 'exp': expires})
    cache = {k:v for k,v in cache.items() if v.get('expires', 0) > now}
    cache[audience] = dict(key=key_hash, at=now, expires=expires, headers=headers)
    tmp = path.with_suffix('.next')
    tmp.write_text(json.dumps(cache));tmp.chmod(0o600);os.replace(tmp, path)
    return headers.copy()
