"""One read-only upstream poller; browsers only read its atomic, credential-free cache."""
import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

URL = 'https://basispulse.yielding.pro/openapi/v1/opportunities'
INTERVAL = 5
MAX_BYTES = 4 * 1024 * 1024
CARD_KEYS = ('id longMarketKey shortMarketKey spanId asset pair strategy trigger longMarket shortMarket rawBps residualBps indexBps entryNetBps funding8hBps enteredAt updatedAt validUntil evaluation radarUrl radarExact').split()
DETAIL_KEYS = ('early windowSeconds windowEnd validSeconds okSeconds longestUnknown netBps marketBps p75Bps indexBps spotIndex transferText').split()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward service credentials to a login/other host.


def pick(value, keys):
    if not isinstance(value, dict):
        return {}
    return {k: value[k] for k in keys if k in value}


def normalize(data):
    if not isinstance(data, dict) or type(data.get('complete')) is not bool or not isinstance(data.get('active'), list) or len(data['active']) > 1000:
        raise ValueError('schema')
    datetime.fromisoformat(data['sampledAt'].replace('Z', '+00:00'))
    cards = []
    ids = set()
    invalid_cards = 0
    for raw in data['active']:
        if not isinstance(raw, dict) or not isinstance(raw.get('id'), str) or not raw['id'] or raw['id'] in ids:
            raise ValueError('card_id')
        try:
            for key in ('enteredAt', 'updatedAt', 'validUntil'):
                value = raw.get(key)
                if not isinstance(value, str) or datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
                    raise ValueError('timestamp')
        except (ValueError, TypeError):
            invalid_cards += 1
            continue
        ids.add(raw['id'])
        card = pick(raw, CARD_KEYS)
        card['v2Residual'] = pick(raw.get('v2Residual'), ('bps', 'level', 'windowSeconds'))
        details = raw.get('details') or {}
        card['details'] = pick(details, DETAIL_KEYS)
        warnings = details.get('newsWarnings')
        card['details']['newsWarnings'] = [{k: v[:2000] for k, v in pick(w, ('exchange', 'summary', 'status', 'deadline')).items() if isinstance(v, str)} for w in warnings[:20] if isinstance(w, dict)] if isinstance(warnings, list) else []
        card['details']['legs'] = [pick(leg, ('exchange', 'market', 'symbol', 'spot', 'rate', 'hours', 'volume', 'oi')) for leg in details.get('legs', [])[:2]]
        card['details']['transferWallets'] = [pick(wallet, ('key', 'text', 'checkedAt', 'expiresAt', 'refreshFailed')) for wallet in details.get('transferWallets', [])[:20]]
        cards.append(card)
    return {**pick(data, ('sampledAt', 'complete', 'freshShards', 'totalShards')), 'active': cards, 'complete': data['complete'] and invalid_cards == 0, 'invalidCards': invalid_cards}


def retry_delay(failures, retry_after=None, now=None):
    delay = min(120, 5 * 2 ** min(failures - 1, 5))
    if retry_after:
        try:
            wait = float(retry_after)
        except ValueError:
            from email.utils import parsedate_to_datetime
            try:
                wait = parsedate_to_datetime(retry_after).timestamp() - (time.time() if now is None else now)
            except (ValueError, TypeError, OverflowError):
                wait = 0
        if math.isfinite(wait):
            delay = max(delay, wait)
    return max(5, delay)


def retain_removed(snapshot, previous, now):
    """Publish one expiry clock and full 30-second history to every reader."""
    def stamp(value):
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    def identity(card):
        return card.get('pair') or card['id']
    sampled = stamp(snapshot['sampledAt'])
    if previous and sampled < stamp(previous['sampledAt']):
        return previous
    active = {identity(card): card for card in snapshot['active']}
    retained = {}
    for entry in (previous or {}).get('retained', []):
        retained[identity(entry['card'])] = entry
    for card in (previous or {}).get('active', []):
        key = identity(card)
        if key in active:
            continue
        if not snapshot['complete'] and now < stamp(card['validUntil']):
            active[key] = card
        else:
            expired = min(sampled, stamp(card['validUntil']))
            retained.setdefault(key, {'card': card, 'expiredAt': datetime.fromtimestamp(expired, timezone.utc).isoformat()})
    retained = [entry for key, entry in retained.items()
                if key not in active and now < min(stamp(entry['expiredAt']), stamp(entry['card']['validUntil'])) + 30]
    retained.sort(key=lambda entry: stamp(entry['expiredAt']), reverse=True)
    result = dict(snapshot, active=list(active.values())[:1000], retained=retained[:1000], retentionSeconds=30)
    # Existing readers have a 4 MiB cache limit. Drop oldest history first.
    while result['retained'] and len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES - 1024:
        result['retained'].pop()
    return result


def write_cache(path, data):
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encoded)
    temporary.chmod(0o640)
    os.replace(temporary, path)


def main():
    import fcntl
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/robot-push/basispulse.json')
    parser.add_argument('--output', default='/var/lib/robot-push/basispulse.json')
    args = parser.parse_args()
    path = Path(args.output)
    with path.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = json.loads(Path(args.config).read_text())
        headers = {'CF-Access-Client-Id': config['clientId'], 'CF-Access-Client-Secret': config['clientSecret'], 'Accept': 'application/json', 'User-Agent': 'FundingRadar-BasisPulse/1.0'}
        opener = build_opener(NoRedirect())
        snapshot = None
        received = None
        try:
            existing = json.loads(path.read_text())
            if isinstance(existing.get('snapshot'), dict):
                snapshot = existing['snapshot']
                received = existing.get('receivedAt')
        except (OSError, ValueError, TypeError):
            pass
        failures = 0
        write_cache(path, {'status': 'connecting', 'receivedAt': received, 'snapshot': snapshot})
        while True:
            status, delay = 'connected', INTERVAL
            try:
                with opener.open(Request(URL, headers=headers), timeout=10) as response:
                    body = response.read(MAX_BYTES + 1)
                    if len(body) > MAX_BYTES:
                        raise ValueError('body_limit')
                    next_snapshot = normalize(json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite'))))
                    snapshot = retain_removed(next_snapshot, snapshot, time.time())
                if snapshot.get('invalidCards'):
                    print('source invalid timestamps:', snapshot['invalidCards'], flush=True)
                received = datetime.now(timezone.utc).isoformat()
                failures = 0
            except HTTPError as error:
                print('upstream HTTP', error.code, flush=True)
                failures += 1
                status = 'auth_required' if error.code in (301, 302, 303, 307, 308, 401, 403) else 'reconnecting'
                delay = retry_delay(failures, error.headers.get('Retry-After'))
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
                print('upstream failure', type(error).__name__, flush=True)
                failures += 1
                status = 'reconnecting'
                delay = retry_delay(failures)
            write_cache(path, {'status': status, 'receivedAt': received, 'snapshot': snapshot})
            time.sleep(delay)  # One process, no bursts; at most 12 requests in any minute.


if __name__ == '__main__':
    main()
