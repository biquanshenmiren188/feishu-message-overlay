"""Owner-only web settings; no PushWard key is exposed to the browser."""
import copy
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from decimal import Decimal
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PREFIX = '/radar/api/pushward'
DEFAULTS = dict(rows=6, excluded_ranks=[], excluded_modes=[], min_percent=None,
                excluded_coins=[], excluded_exchanges=[], notify_enabled=True, notify_interval_seconds=30)
EXCHANGES = ['BINANCE', 'BITGET', 'BYBIT', 'OKX', 'GATE', 'ASTER', 'HL']
INTERVALS = [30, 60, 180, 300, 600, 1800]


def normalize_rank(value):
    match = re.fullmatch(r'R(\d{1,24})(\+?)', value.upper(), re.ASCII)
    if not match:
        raise ValueError('等级格式无效')
    return 'R'+str(int(match[1]))+match[2]


def validate(raw):
    if not isinstance(raw, dict) or set(raw) != set(DEFAULTS):
        raise ValueError('设置字段不完整，请重新打开设置')
    out = copy.deepcopy(raw)
    if type(out['rows']) is not int or not 1 <= out['rows'] <= 6:
        raise ValueError('显示条数必须在 1–6 条之间')
    if type(out['notify_enabled']) is not bool:
        raise ValueError('提醒开关无效')
    if type(out['notify_interval_seconds']) is not int or out['notify_interval_seconds'] not in INTERVALS:
        raise ValueError('请选择有效的提醒间隔')
    for field, allowed in [('excluded_modes', ['SF', 'FS', 'FF']), ('excluded_exchanges', EXCHANGES)]:
        values = out[field]
        if not isinstance(values, list) or len(values) > len(allowed) or any(type(v) is not str or v not in allowed for v in values):
            raise ValueError('筛选选项无效')
        out[field] = [v for v in allowed if v in values]
    ranks = out['excluded_ranks']
    if not isinstance(ranks, list) or len(ranks) > 100 or any(not isinstance(v, str) for v in ranks):
        raise ValueError('屏蔽等级无效')
    out['excluded_ranks'] = sorted(set(normalize_rank(v) for v in ranks))
    coins = out['excluded_coins']
    if not isinstance(coins, list) or len(coins) > 50 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,23}', v) for v in coins):
        raise ValueError('币种最多 50 个，只填币种代码，例如 BTC、ETH')
    out['excluded_coins'] = sorted(set(v.upper() for v in coins))
    v = out['min_percent']
    if v is not None and (type(v) not in (int, float) or not math.isfinite(v) or not -100 <= v <= 100):
        raise ValueError('最低百分比需在 -100 到 100 之间，留空表示不限')
    return out


def matches(row, settings):
    return (row['rank'] not in settings['excluded_ranks'] and row['rank'].rstrip('+') not in settings['excluded_ranks'] and row['mode'] not in settings['excluded_modes']
            and row['coin'] not in settings['excluded_coins']
            and row['buy'] not in settings['excluded_exchanges'] and row['sell'] not in settings['excluded_exchanges']
            and (settings['min_percent'] is None or Decimal(row['value'].rstrip('%')) >= Decimal(str(settings['min_percent']))))


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.value = dict(revision=0, settings=copy.deepcopy(DEFAULTS))
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if type(value.get('revision')) is not int or value['revision'] < 0:
                raise ValueError('invalid_settings_revision')
            raw = value['settings']
            if 'ranks' in raw:
                # Migrate the initial live allow-list draft to the owner's requested
                # receive-all/block-list behavior, retaining non-filter preferences.
                if raw.get('coins') or raw.get('exchanges') or set(raw.get('modes', [])) != {'SF','FS','FF'}:
                    raise ValueError('custom_allow_list_requires_explicit_migration')
                new = copy.deepcopy(DEFAULTS)
                for key in ('rows','min_percent','notify_enabled','notify_interval_seconds'):
                    new[key] = raw[key]
                self.value['revision'] = value['revision']
                self.save(new, value['revision'])
            else:
                self.value = dict(revision=value['revision'], settings=validate(raw))

    def get(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def save(self, raw, revision):
        settings = validate(raw)
        with self.lock:
            if type(revision) is not int or revision != self.value['revision']:
                raise Conflict()
            value = dict(revision=revision+1, settings=settings)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.next')
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=True); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self.value = value
            return copy.deepcopy(value)


class SettingsServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, store, secret, directory, origin):
        if len(secret) < 24:
            raise ValueError('admin_secret_too_short')
        self.store, self.secret, self.directory, self.origin = store, secret, Path(directory), origin
        self.login_attempts = {}
        self.auth_lock = threading.Lock()
        super().__init__(address, SettingsHandler)

    def token(self):
        value = str(int(time.time()))+'.'+secrets.token_hex(16)
        return value+'.'+hmac.new(self.secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def authorized(self, token):
        if not re.fullmatch(r'\d{10}\.[a-f0-9]{32}\.[a-f0-9]{64}', token):
            return False
        value, sig = token.rsplit('.', 1)
        age = time.time()-int(value.split('.')[0])
        return 0 <= age < 30*86400 and hmac.compare_digest(sig, hmac.new(self.secret.encode(), value.encode(), hashlib.sha256).hexdigest())


class SettingsHandler(BaseHTTPRequestHandler):
    server_version = 'RadarSettings/1'
    def log_message(self, *_):
        pass

    def setup(self):
        super().setup(); self.connection.settimeout(6)

    def reply(self, status, body, cookie=None):
        raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'private, no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie is not None:
            self.send_header('Set-Cookie', f'radar_push_admin={cookie}; Path={PREFIX}; Max-Age={2592000 if cookie else 0}; HttpOnly; Secure; SameSite=Strict')
        self.end_headers(); self.wfile.write(raw)

    def authenticated(self):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies['radar_push_admin'].value if 'radar_push_admin' in cookies else ''
            return self.server.authorized(token)
        except Exception:
            return False

    def do_GET(self):
        if self.path != PREFIX+'/settings':
            return self.reply(404, dict(error='not_found'))
        if not self.authenticated():
            return self.reply(401, dict(error='请先输入管理口令'))
        value = self.server.store.get()
        try:
            status = json.loads((self.server.directory/'status.json').read_text())
            value['status'] = {k:status.get(k) for k in ('settingsRevision','checkedAt','sourceConnected','rows','pending','activityError','quota','lastActivityAcceptedAt')}
        except (OSError, ValueError):
            value['status'] = {}
        return self.reply(200, value)

    def do_POST(self):
        if self.path not in (PREFIX+'/login', PREFIX+'/logout', PREFIX+'/settings'):
            return self.reply(404, dict(error='not_found'))
        if self.headers.get('Origin') != self.server.origin or self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(403, dict(error='请求来源无效，请从 BOT 页面打开设置'))
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 1 <= length <= 8192:
                return self.reply(413, dict(error='请求过大'))
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('请求不完整')
            data = json.loads(raw)
            if self.path.endswith('/login'):
                ip = self.headers.get('X-Real-IP', self.client_address[0])[:64]
                now = time.time()
                with self.server.auth_lock:
                    attempts = self.server.login_attempts
                    for k in list(attempts):
                        if now-attempts[k][0] > 60: del attempts[k]
                    start, count = attempts.get(ip, (now, 0))
                    if count >= 10 or len(attempts) >= 2000:
                        return self.reply(429, dict(error='尝试过多，请一分钟后重试'))
                    attempts[ip] = (start, count+1)
                password = data.get('password') if isinstance(data, dict) else None
                if not isinstance(password, str) or not hmac.compare_digest(password.encode(), self.server.secret.encode()):
                    return self.reply(401, dict(error='管理口令不正确'))
                return self.reply(200, dict(ok=True), self.server.token())
            if not self.authenticated():
                return self.reply(401, dict(error='登录已失效，请重新输入管理口令'))
            if self.path.endswith('/logout'):
                return self.reply(200, dict(ok=True), '')
            if not isinstance(data, dict) or set(data) != {'revision', 'settings'}:
                raise ValueError('设置字段不完整')
            return self.reply(200, self.server.store.save(data['settings'], data['revision']))
        except Conflict:
            return self.reply(409, dict(error='设置已在另一台设备修改，请关闭后重新打开，再保存'))
        except (ValueError, TypeError, UnicodeError):
            return self.reply(400, dict(error='设置无效：检查条数、筛选项、最低百分比和提醒间隔'))
        except OSError:
            return self.reply(503, dict(error='保存失败，原设置仍保留，请稍后重试'))
