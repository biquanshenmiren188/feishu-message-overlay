"""Loopback-only browser fixture using the real isolated Store, with no delivery.

Usage: python scripts/serve-alarm-form-fixture.py STATIC_BASELINE AUDIT_JSON
Only synthetic save operations are accepted. No real credentials or network feeds.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
import json, mimetypes, sys, tempfile, time
from urllib.parse import urlsplit, parse_qs

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'web/alarms'))
from store import Store
from market import Market
from server import make_handler

root=Path(sys.argv[1]).resolve();audit_path=Path(sys.argv[2]).resolve()
temp=tempfile.TemporaryDirectory();store=Store(temp.name);market=Market();audit=[]
venues=('binance','okx','bybit','bitget','gate','aster')
bases=('BTC','ETH','SOL','PEPE','1000PEPE','WBTC')

def refresh():
    now=time.time();quotes={}
    for venue in venues:
        for base in bases:
            symbol=base+'-USDT-SWAP' if venue=='okx' else base+'_USDT' if venue=='gate' else base+'USDT'
            q=dict(exchange=venue,market='future',symbol=symbol,base=base,quote='USDT',unit=base,instrumentVerified=True,last='100',lastAt=now,observedAt=now)
            quotes[(venue,'future',symbol)]=q
    market.quotes=quotes
    store.tick(quotes,now)

Base=make_handler(store,market,lambda token:'fixture' if token=='synthetic_fixture_only' else None)
class Handler(Base):
    def do_POST(self):
        if self.path!='/radar/alarms-api/change':return self.reply(405,{})
        try:
            assert self.headers.get('Authorization')=='Bearer synthetic_fixture_only'
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if data.get('action')!='save':return self.reply(405,dict(error='Fixture accepts only synthetic saves'))
            refresh();result=store.mutate('fixture',data,market.quotes)
            audit.append(dict(request=data,response=result));audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
            return self.reply(200,result)
        except Exception as exc:return self.reply(400,dict(error=str(exc)))

    def do_GET(self):
        path=urlsplit(self.path).path
        if path.startswith('/radar/alarms-api/'):
            refresh();return super().do_GET()
        rel=path.removeprefix('/radar/')
        if path.endswith('/'):rel+='index.html'
        chosen=repo/'web'/rel if rel.startswith('robot-push/alarms/') else root/rel
        chosen=chosen.resolve()
        if not (chosen.is_relative_to(repo/'web/robot-push/alarms') or chosen.is_relative_to(root)) or not chosen.is_file():return self.reply(404,{})
        raw=chosen.read_bytes()
        if chosen.name=='index.html':
            raw=raw.replace(b'<body>',b'<body><script>localStorage.setItem("radar-settings-token","synthetic_fixture_only");</script>')
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(chosen))[0] or 'application/octet-stream');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)

print('Isolated form fixture: http://127.0.0.1:18794/radar/robot-push/alarms/',flush=True)
try:ThreadingHTTPServer(('127.0.0.1',18794),Handler).serve_forever()
finally:market.pool.shutdown();store.db.close();temp.cleanup()
