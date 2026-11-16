"""Loopback-only outage fixture, real router/store/API/UI, no live feeds or delivery.

Usage: python scripts/serve-alarm-outage-fixture.py STATIC_BASELINE SCENARIO_JSON
Scenario file: {"phase":"primary|primary_down|backup_down|all_down|recovery1|recovery2|recovery3|web_delay|api_down"}
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
import json, mimetypes, secrets, sys, tempfile, threading, time
from urllib.parse import urlsplit

repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'web/alarms'))
from market import Market
from store import Store
from server import make_handler

root=Path(sys.argv[1]).resolve();scenario=Path(sys.argv[2]).resolve()
temp=tempfile.TemporaryDirectory();store=Store(temp.name);market=Market()
phase=None;phase_at=0;guard=threading.RLock()

def quotes(now,mode):
    rows={}
    for venue,kind in [('binance','future'),('okx','spot'),('bybit','spot'),('bitget','spot'),('gate','spot')]:
        stamp=now
        if mode in ('primary_down','backup_down','all_down') and venue=='binance':stamp=now-60
        if mode in ('backup_down','all_down') and venue=='okx':stamp=now-60
        if mode=='all_down':stamp=now-60
        if mode.startswith('recovery') and venue=='binance':stamp=phase_at
        if mode=='web_delay' and venue=='binance':stamp=now-10
        symbol='BTC-USDT' if venue=='okx' else 'BTC_USDT' if venue=='gate' else 'BTCUSDT'
        rows[venue,kind,symbol]=dict(exchange=venue,market=kind,symbol=symbol,base='BTC',quote='USDT',unit='BTC',instrumentVerified=True,observedAt=stamp,lastAt=stamp,last='70000')
    return rows

now=time.time();initial=quotes(now,'primary')
store.mutate('fixture',dict(action='save',requestId=secrets.token_hex(16),revision=0,rule=dict(exchange='binance',market='future',symbol='BTCUSDT',priceType='last',condition='below',target='66000',repeat=True,fallbackExchange='auto')),initial)
for at in (now-6,now-3,now):store.tick(quotes(at,'primary'),at)

Base=make_handler(store,market,lambda token:'fixture' if token=='outage_fixture_only' else None)
class Handler(Base):
    def do_POST(self):return self.reply(405,dict(error='Isolated outage fixture is read-only'))
    def reply(self,status,value):
        if getattr(self,'delay',False) and status==200:time.sleep(4)
        super().reply(status,value)
    def do_GET(self):
        global phase,phase_at
        path=urlsplit(self.path).path
        if path.startswith('/radar/alarms-api/'):
            with guard:
                mode=json.loads(scenario.read_text())['phase']
                now=time.time()
                if mode!=phase:phase,phase_at=mode,now
                market.quotes=quotes(now,mode);store.tick(market.quotes,now)
            if mode=='api_down':return self.reply(503,dict(error='Isolated page API outage'))
            self.delay=mode=='web_delay'
            return super().do_GET()
        rel=path.removeprefix('/radar/')
        if path.endswith('/'):rel+='index.html'
        chosen=(repo/'web'/rel if rel.startswith('robot-push/alarms/') else root/rel).resolve()
        if not (chosen.is_relative_to(repo/'web/robot-push/alarms') or chosen.is_relative_to(root)) or not chosen.is_file():return self.reply(404,{})
        raw=chosen.read_bytes()
        if chosen.name=='index.html':raw=raw.replace(b'<body>',b'<body><script>localStorage.setItem("radar-settings-token","outage_fixture_only");</script>')
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(chosen))[0] or 'application/octet-stream');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)

print('Isolated outage fixture: http://127.0.0.1:18795/radar/robot-push/alarms/',flush=True)
try:ThreadingHTTPServer(('127.0.0.1',18795),Handler).serve_forever()
finally:market.pool.shutdown();store.db.close();temp.cleanup()
