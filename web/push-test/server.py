"""Finite, owner-paired Web Push experiment. No real-feed readers or arbitrary messages."""
import base64
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BASE = '/radar/push-test/'
ORIGIN = 'https://leida.shenmiren.work'
SAMPLES = (
    ('ARC', 'SF', 'GATE→BITGET', 'R1', '+0.33%'),
    ('BLUR', 'FF', 'BINANCE→OKX', 'R0', '+0.41%'),
    ('DGAI', 'FS', 'OKX→BITGET', 'R0', '+0.39%'),
    ('ZEREBRO', 'SF', 'GATE→ASTER', 'R1', '+0.23%'),
    ('BTC', 'FF', 'BINANCE→OKX', 'R0', '+0.10%'),
    ('CNPY', 'SF', 'BITGET→OKX', 'R0', '+0.39%'),
    ('ETH', 'FF', 'BINANCE→OKX', 'R2', '+0.52%'),
)


def rows_for(step, first_at):
    assert 1 <= step <= 7
    rows = []
    for i in range(max(0, step - 6), step):
        clock = datetime.fromtimestamp(first_at + 30 * i, timezone(timedelta(hours=8))).strftime('%H:%M:%S')
        rows.append(' '.join(SAMPLES[i]) + ' ' + clock)
    return rows


def compact_rows(rows):
    names = {'BINANCE':'BN', 'BITGET':'BG', 'BYBIT':'BY', 'GATE':'GT',
             'ASTER':'AS', 'OKX':'OK', 'HYPERLIQUID':'HY', 'HYPER':'HY', 'HL':'HY'}
    result = []
    for row in rows:
        symbol, kind, route, rank, percent, stamp = row.split()
        route = '→'.join(names.get(venue.upper(), venue) for venue in route.split('→'))
        result.append(f'{stamp[:5]} {percent} {rank} {kind} {route} {symbol}')
    return result


def validate_subscription(value):
    from cryptography.hazmat.primitives.asymmetric import ec
    if not isinstance(value, dict):
        raise ValueError('订阅格式错误')
    endpoint = value.get('endpoint', '')
    if not isinstance(endpoint, str) or any(ord(char) <= 32 for char in endpoint):
        raise ValueError('推送地址格式错误')
    u = urlsplit(endpoint)
    # Preserve Apple; accept only the production Web Push services used by
    # Android Chrome (both current /wp/ and legacy /fcm/send/) and Firefox.
    provider = bool(u.hostname and u.hostname.endswith('.push.apple.com')) or (
        u.hostname == 'fcm.googleapis.com' and u.path.startswith(('/wp/', '/fcm/send/'))) or (
        u.hostname == 'updates.push.services.mozilla.com' and u.path.startswith(('/wpush/', '/push/', '/v1/')))
    if (u.scheme != 'https' or not provider
            or u.username or u.password or u.port not in (None, 443) or u.fragment or len(endpoint) > 2048):
        raise ValueError('不支持此推送服务，请在安卓 Chrome、Firefox 或 iPhone 主屏幕雷达中开启通知')
    keys = value.get('keys', {})
    decoded = {}
    for key, size in [('auth', 16), ('p256dh', 65)]:
        raw = keys.get(key, '')
        if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', raw):
            raise ValueError('订阅密钥格式错误')
        decoded[key] = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
        if len(decoded[key]) != size:
            raise ValueError('订阅密钥长度错误')
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded['p256dh'])
    return {'endpoint': endpoint, 'keys': {k: keys[k] for k in ('auth', 'p256dh')}}


class Trial:
    def __init__(self, state_dir, config_path, sender=None, *, config=None):
        self.directory = Path(state_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'state.json'
        self.config = dict(config) if config is not None else json.loads(Path(config_path).read_text())
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.sender = sender or self.send_webpush
        self.pair_attempts = []
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'seq': 0, 'sends': [], 'receipts': [], 'runs': 0}
        c = self.state.get('campaign')
        if c and c['state'] in ('running', 'scheduled'):
            c['state'] = 'interrupted'
            self.save()

    def save(self):
        tmp = self.path.with_suffix('.next')
        tmp.write_text(json.dumps(self.state, ensure_ascii=False))
        tmp.chmod(0o600)
        os.replace(tmp, self.path)

    def pair(self, code):
        with self.lock:
            now = time.time()
            self.pair_attempts = [x for x in self.pair_attempts if x > now - 300]
            if len(self.pair_attempts) >= 10:
                raise ValueError('尝试过多，请五分钟后再试')
            self.pair_attempts.append(now)
            if now > self.config['expiresAt']:
                raise ValueError('本次测试已到期')
            if not isinstance(code, str) or not hmac.compare_digest(code, self.config['pairCode']):
                raise ValueError('测试码不正确')
            if not self.state.get('token'):
                self.state['token'] = secrets.token_urlsafe(32)
                self.save()
            return self.state['token']

    def authenticate(self, token):
        return (time.time() < self.config['expiresAt'] and bool(self.state.get('token'))
                and hmac.compare_digest(token, self.state['token']))

    def public_status(self):
        with self.lock:
            return {'publicKey': self.config['publicKey'], 'subscribed': bool(self.state.get('subscription')),
                    'campaign': self.state.get('campaign'), 'sends': self.state['sends'][-14:],
                    'receipts': self.state['receipts'][-14:], 'observation': self.state.get('observation')}

    def subscribe(self, value):
        sub = validate_subscription(value)
        with self.lock:
            if self.state.get('subscription') and self.state['subscription'] != sub:
                raise ValueError('已绑定另一份订阅，请先联系测试管理员重置')
            self.state['subscription'] = sub
            self.save()

    def start(self):
        with self.lock:
            if not self.state.get('subscription'):
                raise ValueError('请先启用通知')
            if self.state.get('campaign', {}).get('state') in ('scheduled', 'running'):
                raise ValueError('测试正在进行，不会重复启动')
            if self.state['runs'] >= 3:
                raise ValueError('已完成三轮测试，已停发，请先查看诊断结果')
            self.stop_event = threading.Event()
            self.state['runs'] += 1
            now = time.time()
            run = secrets.token_hex(6)
            self.state['campaign'] = {'run': run, 'state': 'scheduled', 'sent': 0, 'startedAt': now, 'nextAt': now + 30, 'body': ''}
            self.state.pop('observation', None)
            self.save()
            threading.Thread(target=self.run_campaign, args=(run, now + 30, self.stop_event), daemon=True).start()

    def resend(self, compact=True, rows=4):
        if type(rows) is not int or not 1 <= rows <= 6:
            raise ValueError('示例条数必须在 1 到 6 之间')
        with self.lock:
            if not self.state.get('subscription'):
                raise ValueError('请先启用通知')
            if self.state.get('campaign', {}).get('state') in ('scheduled', 'running'):
                raise ValueError('请等待当前测试结束')
            if time.time() - self.state.get('lastResendAt', 0) < 30:
                raise ValueError('请间隔 30 秒再补推')
            self.state['lastResendAt'] = time.time()
            self.state['seq'] += 1
            payload = {'kind': 'radar-six-test', 'seq': self.state['seq'],
                       'run': secrets.token_hex(6), 'rows': rows_for(7, time.time()-180)}
            if compact:
                payload['title'] = ''
                payload['rows'] = compact_rows(payload['rows'])
            payload['rows'] = payload['rows'][-rows:]
            self.save()
            status, error = None, None
            try:
                status = self.sender(self.state['subscription'], payload)
            except Exception as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                error = type(exc).__name__
            result = {'at': time.time(), 'seq': payload['seq'], 'run': payload['run'],
                      'rows': len(payload['rows']), 'http': status, 'error': error}
            self.state['sends'].append(result)
            self.state['sends'] = self.state['sends'][-30:]
            self.save()
            return result

    def stop(self):
        with self.lock:
            self.stop_event.set()
            if self.state.get('campaign', {}).get('state') in ('scheduled', 'running'):
                self.state['campaign']['state'] = 'stopped'
                self.save()

    def send_webpush(self, subscription, payload):
        import requests
        from pywebpush import webpush
        from delivery import TTL, TOPIC, vapid_headers
        class NoRedirect(requests.Session):
            def request(self, *args, **kwargs):
                kwargs['allow_redirects'] = False
                return super().request(*args, **kwargs)
        with NoRedirect() as session:
            with getattr(self, 'vapid_lock', self.lock):
                headers = vapid_headers(getattr(self, 'vapid_directory', self.directory), self.config['privateKeyPath'], subscription['endpoint'], ORIGIN)
            headers.update(Urgency='high', Topic=TOPIC)
            response = webpush(subscription_info=subscription, data=json.dumps(payload, ensure_ascii=False),
                               ttl=TTL, headers=headers, timeout=12, requests_session=session)
            if response.status_code != 201:
                raise RuntimeError('push_not_accepted')
            return response.status_code

    def run_campaign(self, run, first_at, stop):
        for step in range(1, 8):
            if stop.wait(max(0, first_at + (step - 1) * 30 - time.time())):
                return
            with self.lock:
                if time.time() >= self.config['expiresAt'] or self.state['campaign']['run'] != run or stop.is_set():
                    return
                self.state['seq'] += 1
                payload = {'kind': 'radar-six-test', 'seq': self.state['seq'], 'run': run,
                           'title': '', 'rows': compact_rows(rows_for(step, first_at))[-4:]}
                assert len(json.dumps(payload, ensure_ascii=False).encode()) < 3000
                self.state['campaign']['state'] = 'running'
                self.save()
                subscription = self.state['subscription']
            status = None
            error = None
            try:
                status = self.sender(subscription, payload)
            except Exception as exc:
                response = getattr(exc, 'response', None)
                status = getattr(response, 'status_code', None)
                error = type(exc).__name__  # Never write endpoint, keys, or exception text.
            with self.lock:
                self.state['sends'].append({'at': time.time(), 'seq': payload['seq'], 'run': run, 'rows': len(payload['rows']), 'http': status, 'error': error})
                self.state['sends'] = self.state['sends'][-30:]
                c = self.state['campaign']
                if c['run'] != run:
                    self.save()
                    return
                if error:
                    c['state'] = 'failed'
                    self.save()
                    return
                c.update(sent=step, body='\n'.join(payload['rows']), nextAt=first_at + step * 30)
                if not stop.is_set():
                    c['state'] = 'complete' if step == 7 else 'running'
                self.save()

    def receipt(self, value):
        safe = {'at': time.time()}
        for key in ('seq', 'rows', 'before', 'closeCalls', 'after', 'eventAt'):
            x = value.get(key)
            if isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 10000000000:
                safe[key] = x
        for key in ('run', 'stage', 'version', 'error', 'operation'):
            x = value.get(key)
            if isinstance(x, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', x):
                safe[key] = x
        safe['enumerationError'] = value.get('enumerationError') is True
        for key in ('bodyHash', 'shownHash'):
            x = value.get(key)
            if isinstance(x, str) and re.fullmatch(r'[a-f0-9]{64}', x):
                safe[key] = x
        with self.lock:
            self.state['receipts'].append(safe)
            self.state['receipts'] = self.state['receipts'][-2000:]
            self.save()


def handler(trial):
    desktop = None
    if hasattr(trial, 'accounts'):
        from desktop_rules import DesktopRules
        from desktop_binding import DesktopProfiles
        desktop = DesktopRules(trial.directory)
        desktops = DesktopProfiles(trial, desktop)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # A closed peer cannot receive another error response. The
                # operation may already be committed; never run it again here.
                self.close_connection = True

        def do_GET(self):
            # This path is deliberately outside every public /radar proxy route.
            if self.path == '/internal/desktop-state' and self.client_address[0] == '127.0.0.1' and desktop:
                try:return self.reply(200, desktop.evaluate())
                except Exception:return self.reply(503, {'error':'desktop_rules_unavailable'})
            if self.path == BASE + 'api/health':
                return self.reply(200, {'ok': True, 'mode': 'live' if hasattr(trial, 'configure') or hasattr(trial, 'resolve') else 'synthetic-only'})
            if self.path == BASE + 'api/card-oi' and desktop:
                try:return self.reply(200, desktop.public_card_oi())
                except Exception:return self.reply(503, {'error':'双边 OI 暂不可用'})
            account = self.authorized_account()
            if account is None:
                return self.reply(401, {'error': '请先用测试码连接'})
            if self.path == BASE + 'api/desktop-settings' and desktop:
                return self.reply(200, desktops.policy(account).status())
            if self.path == BASE + 'api/coin-blocks' and desktop:
                return self.reply(200, desktops.policy(account).coin_state(account))
            if self.path == BASE + 'api/card-decisions' and desktop:
                try:return self.reply(200, desktops.policy(account).web_cards())
                except Exception:return self.reply(503, {'error':'行情卡片规则暂时无法同步'})
            if self.path == BASE + 'api/status':
                return self.reply(200, account.public_status())
            if self.path == BASE + 'api/binding':
                # Owner-only, no-store: do not include the pairing code in routine
                # status/diagnostics or static assets. Existing devices need no re-pair.
                return self.reply(200, {'pushCode': account.config['pairCode']})
            self.reply(404, {'error': '不存在'})

        def authorized_account(self):
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            if hasattr(trial, 'resolve'):
                return trial.resolve(token)
            return trial if trial.authenticate(token) else None

        def do_POST(self):
            if self.headers.get('Origin') not in (None, ORIGIN):
                return self.reply(403, {'error': '来源不匹配'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    return self.reply(413, {'error': '请求大小错误'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('请求格式错误')
                # Only the existing authenticated publisher can bridge here.
                # This loopback path is outside all public /radar proxy routes.
                if self.path == '/internal/desktop-binding' and self.client_address[0] == '127.0.0.1' and desktop:
                    return self.reply(200, desktops.state(data))
                if self.path == '/internal/coin-rules' and self.client_address[0] == '127.0.0.1' and desktop:
                    if 'pushCode' in data:
                        return self.reply(200, desktops.coins(data))
                    from coin_control import dispatch
                    return self.reply(200, dispatch(desktop, trial.accounts['legacy'], data))
                if not self.path.startswith(BASE + 'api/'):
                    return self.reply(404, {'error': '不存在'})
                route = self.path.removeprefix(BASE + 'api/')
                if route == 'create-code' and hasattr(trial, 'create_code'):
                    # Available to visitors behind the existing website access policy.
                    return self.reply(200, trial.create_code(data.get('requestId')))
                if self.path == BASE + 'api/pair':
                    if hasattr(trial, 'resolve'):
                        return self.reply(200, {'token': trial.pair(data.get('code'), trial.client_key(self.headers, self.client_address[0]))})
                    return self.reply(200, {'token': trial.pair(data.get('code'))})
                account = self.authorized_account()
                if account is None:
                    return self.reply(401, {'error': '请先用测试码连接'})
                if route == 'desktop-settings' and desktop:
                    return self.reply(200, desktops.policy(account).configure(data))
                if route == 'edit-coins' and desktop:
                    return self.reply(200, desktops.policy(account).edit_coins(data,account))
                if route == 'block-coins' and desktop:
                    return self.reply(200, desktops.policy(account).block_coins(data,account))
                if route == 'switch-subscription' and hasattr(trial, 'transfer_subscription'):
                    return self.reply(200, trial.transfer_subscription(account, data))
                if route == 'settings' and hasattr(account, 'configure'):
                    return self.reply(200, account.configure(data))
                if route == 'device' and hasattr(account, 'device_status'):
                    return self.reply(200, account.device_status(data))
                if route == 'verify' and hasattr(account, 'verify_delivery'):
                    return self.reply(200, account.verify_delivery())
                if route == 'subscribe':
                    if 'replaceFingerprint' in data and hasattr(account, 'repair_subscription'):
                        account.repair_subscription(data.get('subscription'), data['replaceFingerprint'])
                    else:
                        account.subscribe(data.get('subscription'))
                elif route == 'start':
                    account.start()
                elif route == 'resend':
                    return self.reply(200, account.resend(compact=data.get('compact', True) is True, rows=data.get('rows', 4)))
                elif route == 'stop':
                    account.stop()
                elif route == 'receipt-batch':
                    records = data.get('records')
                    if not isinstance(records, list) or not 1 <= len(records) <= 20 or any(not isinstance(r, dict) for r in records):
                        raise ValueError('Invalid receipt batch')
                    for record in records:
                        account.receipt(record)
                elif route == 'receipt':
                    account.receipt(data)
                elif route == 'observation' and data.get('result') in ('one-four', 'one-six', 'duplicates', 'missing-or-truncated'):
                    with account.lock:
                        account.state['observation'] = {'result': data['result'], 'at': time.time()}
                        account.save()
                else:
                    return self.reply(404, {'error': '不存在'})
                self.reply(200, {'ok': True})
            except ValueError as exc:
                self.reply(400, {'error': str(exc)[:160]})
            except Exception:
                self.reply(500, {'error': '测试服务处理失败，已记录状态'})
    return Handler


if __name__ == '__main__':
    os.umask(0o077)
    factory = Trial
    if os.environ.get('RADAR_LIVE_FEED'):
        from profiles import Profiles
        factory = Profiles
    app = factory(os.environ.get('RADAR_TEST_STATE', '/var/lib/radar-webpush-test'),
                os.environ.get('RADAR_TEST_CONFIG', '/etc/radar-webpush-test/config.json'))
    if factory is not Trial:
        threading.Thread(target=app.run_feed, args=(os.environ['RADAR_LIVE_FEED'],), daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', 18885), handler(app)).serve_forever()
