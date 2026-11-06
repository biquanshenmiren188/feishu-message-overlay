"""Push-code management facade. Legacy identities and delivery remain authoritative.

No tokens, codes, subscription endpoints or Bark keys are stored here.
"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener

BASE = '/radar/push-center-api/'
ORIGIN = 'https://leida.shenmiren.work'


class Failure(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def upstream(service, route, token='', data=None, client='127.0.0.1'):
    port, prefix = (18885, '/radar/push-test/api/') if service == 'push' else (18886, '/radar/alarms-api/')
    req = Request(f'http://127.0.0.1:{port}{prefix}{route}',
                  data=None if data is None else json.dumps(data).encode(),
                  headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json',
                           'Origin': ORIGIN, 'CF-Connecting-IP': client})
    try:
        with build_opener(NoRedirect).open(req, timeout=6) as response:
            return json.loads(response.read(2000000))
    except HTTPError as exc:
        try: message = json.loads(exc.read(8192)).get('error', '服务请求失败')
        except Exception: message = '服务请求失败'
        raise Failure(exc.code, message) from None
    except Exception:
        raise Failure(503, '连接服务暂不可用，请稍后重试') from None


class Store:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(Path(directory)/'center.sqlite3'), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT NOT NULL,revision INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS history(profile TEXT NOT NULL,request TEXT NOT NULL,digest TEXT NOT NULL,at REAL NOT NULL,action TEXT NOT NULL,PRIMARY KEY(profile,request));
        ''')

    def view(self, profile):
        with self.lock:
            p = self.db.execute('SELECT name,revision FROM profiles WHERE id=?', (profile,)).fetchone()
            logs = self.db.execute('SELECT at,action FROM history WHERE profile=? ORDER BY at DESC LIMIT 50', (profile,)).fetchall()
            return dict(name=p['name'] if p else ('主推送码' if profile == 'legacy' else '我的推送码'),
                        revision=p['revision'] if p else 0, history=[dict(r) for r in logs])

    @staticmethod
    def request(data):
        request = data.get('requestId')
        if not isinstance(request, str) or not re.fullmatch('[a-f0-9]{32}', request):
            raise Failure(400, '请求编号无效')
        return request

    def rename(self, profile, data):
        request = self.request(data)
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 30 or any(ord(c) < 32 for c in name):
            raise Failure(400, '名称应为 1 至 30 字')
        digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        with self.lock, self.db:
            old = self.db.execute('SELECT digest FROM history WHERE profile=? AND request=?', (profile, request)).fetchone()
            if old:
                if old['digest'] != digest: raise Failure(409, '请求编号已用于其他操作')
                return self.view(profile)
            current = self.view(profile)
            if type(data.get('revision')) is not int or data['revision'] != current['revision']:
                raise Failure(409, '名称已在其他页面修改，请刷新后重试')
            self.db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?,?)', (profile, name.strip(), current['revision']+1))
            self.db.execute('INSERT INTO history VALUES (?,?,?,?,?)', (profile, request, digest, time.time(), '修改推送码名称'))
            self.prune(profile)
            return self.view(profile)

    def prune(self, profile):
        self.db.execute('DELETE FROM history WHERE profile=? AND at<?', (profile, time.time()-30*86400))

    def record(self, profile, request, action):
        with self.lock, self.db:
            self.db.execute('INSERT OR IGNORE INTO history VALUES (?,?,?,?,?)', (profile, request, action, time.time(), action))
            self.prune(profile)


def make_handler(store, call=upstream):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def setup(self):
            super().setup()
            self.connection.settimeout(10)
        def reply(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            for key, value in [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Content-Length', str(len(raw)))]:
                self.send_header(key, value)
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass

        def dispatch(self, post=False):
            try:
                if self.headers.get('Origin') not in (None, ORIGIN): raise Failure(403, '来源不匹配')
                if not self.path.startswith(BASE): raise Failure(404, '接口不存在')
                route = self.path[len(BASE):]
                allowed = ('pair', 'create-code', 'rename', 'bark', 'verify-phone') if post else ('health', 'state')
                if route not in allowed: raise Failure(404, '接口不存在')
                if route == 'health': return self.reply(200, dict(ok=True, version=1))
                data = None
                if post:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 8192: raise Failure(413, '请求大小错误')
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict): raise Failure(400, '请求格式错误')
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                try: client = str(ipaddress.ip_address(self.headers.get('CF-Connecting-IP', self.client_address[0])))
                except ValueError: client = self.client_address[0]
                if route in ('pair', 'create-code'):
                    result = call('push', route, '', data, client)
                    return self.reply(200, result)
                if not re.fullmatch('[A-Za-z0-9_-]{20,100}', token): raise Failure(401, '请先连接推送码')
                status = call('push', 'status', token)
                profile = status.get('profileId')
                if profile != 'legacy' and not (isinstance(profile, str) and re.fullmatch('[a-f0-9]{32}', profile)):
                    raise Failure(503, '推送码身份暂不可用')
                if route == 'rename': return self.reply(200, store.rename(profile, data))
                if route == 'bark':
                    request = store.request(data)
                    action = data.get('action')
                    if action not in ('bind', 'unbind', 'test'): raise Failure(400, '设备操作无效')
                    result = call('alarm', 'change', token, data)
                    store.record(profile, request, {'bind':'绑定或更新 Bark 设备','unbind':'解除 Bark 设备绑定','test':'提交 Bark 测试通知'}[action])
                    return self.reply(200, result)
                if route == 'verify-phone':
                    result = call('push', 'verify', token, {})
                    return self.reply(200, result)
                binding = call('push', 'binding', token)
                result = dict(profileId=profile, pushCode=binding['pushCode'], **store.view(profile),
                              phone=dict(subscribed=bool(status.get('subscribed')), enabled=bool(status.get('settings', {}).get('notify_enabled')), device=status.get('device')))
                # A failing device service must never look like an unbound device.
                try:
                    desktop = call('push', 'desktop-settings', token)
                    result['desktop'] = dict(available=True, connected=bool(desktop.get('connected')))
                except Failure as exc:
                    result['desktop'] = dict(available=False, error=str(exc))
                try:
                    alarm = call('alarm', 'state', token)
                    result['bark'] = dict(available=True, revision=alarm['revision'], device=alarm['device'], enabled=alarm['enabled'])
                except Failure as exc:
                    result['bark'] = dict(available=False, error=str(exc))
                return self.reply(200, result)
            except Failure as exc: self.reply(exc.status, dict(error=str(exc)))
            except (ValueError, TypeError): self.reply(400, dict(error='请求格式错误'))
            except Exception: self.reply(503, dict(error='推送中心暂不可用，请稍后重试'))
        def do_GET(self): self.dispatch()
        def do_POST(self): self.dispatch(True)
    return Handler


if __name__ == '__main__':
    os.umask(0o077)
    store = Store(os.environ.get('RADAR_PUSH_CENTER_STATE', '/var/lib/radar-push-center'))
    ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('RADAR_PUSH_CENTER_PORT', 18887))), make_handler(store)).serve_forever()
