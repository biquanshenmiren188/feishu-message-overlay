"""Isolated alarm service. Existing Web Push is used only for bearer authentication."""
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener
from market import Market, NoRedirect
from store import Store, Conflict
import tbtc_alert

BASE = '/radar/alarms-api/'
ORIGIN = 'https://leida.shenmiren.work'


def authenticate(token):
    if not re.fullmatch('[A-Za-z0-9_-]{20,100}', token):
        return None
    req = Request('http://127.0.0.1:18885/internal/alarm-identity', headers={'Authorization': 'Bearer ' + token})
    try:
        with build_opener(NoRedirect).open(req, timeout=5) as response:
            profile = json.loads(response.read(4096)).get('profileId')
            return profile if profile == 'legacy' or isinstance(profile, str) and re.fullmatch('[a-f0-9]{32}', profile) else None
    except HTTPError as exc:
        if exc.code == 401:
            return None
        raise


def send_event(store, event, market=None):
    quotes = market.snapshot()[0] if market is not None else None
    if not store.begin_send(event, quotes):
        return
    payload = json.loads(event['payload'])
    body = {k: payload[k] for k in ('id', 'title', 'body', 'group', 'level', 'url')}
    body.update(level='critical', volume=5, call='1')
    body.update(device_key=store.cipher.decrypt(event['secret'].encode()).decode(), isArchive='1')
    req = Request('https://api.day.app/push', data=json.dumps(body, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    if event['rule_id']==tbtc_alert.SALE_RULE:
        store.record_sale_send(event['id'])
    try:
        with build_opener(NoRedirect).open(req, timeout=10) as response:
            result = json.loads(response.read(65536))
            if result.get('code') == 200:
                store.finish(event, 'accepted')
            else:
                store.finish(event, 'failed', 'Bark 拒绝请求，请检查设备绑定')
    except HTTPError as exc:
        store.finish(event, 'retry' if not payload.get('repeatInterval') and (exc.code == 429 or exc.code >= 500) else 'failed', 'Bark HTTP ' + str(exc.code))
    except (TimeoutError, URLError, OSError, ValueError):
        # Timeout/invalid responses may follow successful acceptance. Do not blindly resend.
        store.finish(event, 'unknown', '未取得明确响应，结果未知；未自动重复发送')
    except Exception:
        store.finish(event, 'unknown', '响应格式异常，结果未知；未自动重复发送')


def make_handler(store, market, auth=authenticate):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            if hasattr(self, 'started'):
                total=(time.perf_counter()-self.started)*1000
                auth_ms=getattr(self,'auth_ms',0)
                self.send_header('Server-Timing',f'auth;dur={auth_ms:.1f}, app;dur={max(0,total-auth_ms):.1f}, total;dur={total:.1f}')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def dispatch(self, post=False):
            self.started=time.perf_counter();self.auth_ms=0
            route = urlsplit(self.path)
            if route.path=='/internal/tbtc-sales' and post:
                if (self.client_address[0]!='127.0.0.1' or self.headers.get('Host')!='127.0.0.1:18886'
                        or self.headers.get('Origin') or self.headers.get('X-Forwarded-For')
                        or self.headers.get('Content-Length')!='0'):
                    return self.reply(403,{})
                # The webhook is a wake-up signal. Only our scanner's verified
                # snapshot supplies the amounts and transaction identifiers.
                batch=self.headers.get('X-Radar-Sale-Batch')
                if batch is not None and not re.fullmatch('[0-9a-f]{32}',batch):
                    return self.reply(400,{})
                with store.lock,store.db:
                    tbtc_alert.enqueue_sales(store,time.time(),batch)
                return self.reply(200,{'ok':True})
            if route.path == BASE + 'health' and not post:
                return self.reply(200, dict(ok=True, version=15, alarmContent=True, alarmContentTemplate=True, multiDevice=True, quoteRouting="same-asset-spot-v3", denominationConversion=True, fallbackSelection=True, fallbackMultiSelect=True, authoritativeFeedStatus=True, monitoringMode="per-rule", repeatIntervalSeconds=30, notificationLevel="critical", ringingSeconds=30))
            if self.headers.get('Origin') not in (None, ORIGIN):
                return self.reply(403, dict(error='来源不匹配'))
            if route.path not in (BASE + 'state', BASE + 'catalog', BASE + 'change', BASE + 'history', BASE + 'event', BASE + 'devices', BASE + 'tbtc'):
                return self.reply(404, dict(error='接口不存在'))
            try:
                profile = auth(self.headers.get('Authorization', '').removeprefix('Bearer '))
                self.auth_ms=(time.perf_counter()-self.started)*1000
                if not profile:
                    return self.reply(401, dict(error='请先连接推送码'))
                query = parse_qs(route.query)
                if route.path == BASE+'tbtc':
                    if not post and query.get('view')==['history']:
                        return self.reply(200,tbtc_alert.history(store,profile,query))
                    if not post: return self.reply(200,tbtc_alert.state(store,profile))
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=8192: return self.reply(413,dict(error='请求过大'))
                    data=json.loads(self.rfile.read(size))
                    if not isinstance(data,dict): raise ValueError('请求格式错误')
                    if query.get('action')==['page-alert']:
                        return self.reply(200,tbtc_alert.record_page(store,profile,data))
                    return self.reply(200,tbtc_alert.configure(store,profile,data))
                if not post and route.path == BASE + 'devices':
                    with store.lock:
                        return self.reply(200, dict(devices=store.device_list(profile, reveal=True), revision=store.view(profile)['revision']))
                if not post and route.path == BASE + 'history':
                    return self.reply(200, store.history(profile, query))
                if not post and route.path == BASE + 'event':
                    return self.reply(200, store.event_detail(profile, query.get('id',[''])[0]))
                if not post and route.path == BASE + 'state' and query.get('events') == ['latest-test']:
                    value = store.view(profile, compact=True)
                    value.update(serverTime=time.time(), sampleInterval=2)
                    return self.reply(200, value)
                quotes, health = market.snapshot()
                if not post and route.path == BASE + 'state':
                    value = store.view(profile)
                    value.update(market=health, serverTime=time.time(), sampleInterval=2)
                    return self.reply(200, value)
                if not post and route.path == BASE + 'catalog':
                    query = parse_qs(route.query)
                    exchange, kind = query.get('exchange', ['binance'])[0], query.get('market', ['future'])[0]
                    return self.reply(200, dict(items=[q for key, q in quotes.items() if key[:2] == (exchange, kind)], health=health.get(exchange + '/' + kind)))
                if not post or route.path != BASE + 'change':
                    return self.reply(405, dict(error='请求方法错误'))
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 8192:
                    return self.reply(413, dict(error='请求过大'))
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict):
                    raise ValueError('请求格式错误')
                return self.reply(200, store.mutate(profile, value, quotes))
            except Conflict as exc:
                return self.reply(409, dict(error=str(exc)))
            except (ValueError, TypeError) as exc:
                return self.reply(400, dict(error=str(exc) if isinstance(exc, ValueError) else '字段格式错误'))
            except Exception:
                return self.reply(503, dict(error='报警服务暂不可用，请稍后重试'))

        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch(True)
    return Handler


def main():
    store = Store(os.environ.get('RADAR_ALARMS_STATE', '/var/lib/radar-alarms'))
    tbtc_alert.initialize(store)
    market = Market()

    def watch():
        while True:
            try:
                quotes, _ = market.snapshot()
                active = store.tick(quotes, time.time())
                market.poll(active)
                tbtc_alert.tick_chain(store)
            except Exception as exc:
                print('watch:', type(exc).__name__, flush=True)
            time.sleep(.5)

    def watch_tbtc_prices():
        while True:
            try:
                tbtc_alert.tick_prices(store)
            except Exception as exc:
                print('tbtc price reader:', type(exc).__name__, flush=True)
            time.sleep(.5)

    def deliver():
        while True:
            try:
                event = store.claim()
                if event:
                    send_event(store, event, market)
                    continue
            except Exception as exc:
                print('delivery:', type(exc).__name__, flush=True)
            time.sleep(.5)

    threading.Thread(target=watch, daemon=True).start()
    threading.Thread(target=watch_tbtc_prices, daemon=True).start()
    # A slow or failed device must not hold other devices behind its HTTP timeout.
    for _ in range(8):
        threading.Thread(target=deliver, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('RADAR_ALARMS_PORT', 18886))), make_handler(store, market)).serve_forever()


if __name__ == '__main__':
    main()
