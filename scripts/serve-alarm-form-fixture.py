"""Loopback-only browser fixture using the real isolated Store, with no delivery.

Usage: python scripts/serve-alarm-form-fixture.py STATIC_BASELINE AUDIT_JSON
Only synthetic save operations are accepted. No real credentials or network feeds.
"""
from pathlib import Path
from http.server import ThreadingHTTPServer
import json, mimetypes, sys, tempfile, time, uuid
from urllib.parse import urlsplit, parse_qs

repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo/'web/alarms'))
from store import Store
from market import Market
from server import make_handler
from denominations import REGISTRY
from decimal import Decimal

root=Path(sys.argv[1]).resolve();audit_path=Path(sys.argv[2]).resolve()
temp=tempfile.TemporaryDirectory();store=Store(temp.name);market=Market();audit=[]
venues=('binance','okx','bybit','bitget','gate','aster')
bases=('BTC','ETH','SOL','PEPE','1000PEPE','WBTC')
scaled='--denominations' in sys.argv
layout='--layout' in sys.argv

def scaled_book(at,failed=False):
    quotes={}
    for (venue,kind,symbol),(base,asset,units) in REGISTRY.items():
        stamp=at-30 if failed and kind=='future' else at
        value=Decimal('0.0000039' if failed and kind=='spot' else '0.0000041')*units
        quotes[venue,kind,symbol]=dict(exchange=venue,market=kind,symbol=symbol,base=base,quote='USDT',unit=base,
            instrumentVerified=True,last=str(value),lastAt=stamp,observedAt=stamp)
    return quotes

def refresh():
    now=time.time();quotes={}
    if scaled:
        market.quotes=scaled_book(now,True);store.tick(market.quotes,now);return
    for venue in venues:
        for base in bases:
            symbol=base+'-USDT-SWAP' if venue=='okx' else base+'_USDT' if venue=='gate' else base+'USDT'
            value=('68732.3' if venue=='okx' else '68735.8') if layout and base=='BTC' else '100'
            q=dict(exchange=venue,market='future',symbol=symbol,base=base,quote='USDT',unit=base,instrumentVerified=True,last=value,lastAt=now,observedAt=now)
            quotes[(venue,'future',symbol)]=q
    market.quotes=quotes
    store.tick(quotes,now)

if layout:
    refresh()
    for i,(venue,symbol,target) in enumerate((('okx','BTC-USDT-SWAP','65000'),('binance','BTCUSDT','66000'))):
        store.mutate('fixture',dict(action='save',requestId=uuid.uuid4().hex,revision=i,rule=dict(exchange=venue,market='future',symbol=symbol,priceType='last',condition='below',target=target,repeat=True,enabled=True,fallbackExchanges=['bybit'],hold=0,cooldown=30,hysteresis='0',level='critical',immediate=True)),market.quotes)
    refresh()

Base=make_handler(store,market,lambda token:'fixture' if token=='synthetic_fixture_only' else None)
class Handler(Base):
    def reply(self,status,data):
        # Optional deterministic display-only faults, confined to this isolated fixture.
        control=audit_path.with_suffix('.feed.json')
        if '--stable' in sys.argv and self.path.startswith('/radar/alarms-api/state') and control.exists():
            mode=json.loads(control.read_text()).get('mode','healthy')
            for r in data.get('rules',[]):
                s=r['state'];now=time.time()
                s.update(price=str(68000+int(now)%100),sampleAt=now-11,observedAt=now-2,status='watching')
                s['source']={'exchange':r['exchange'],'market':'future','fallback':False}
                if mode=='outage':s.update(status='stale',sampleAt=now-30)
                if mode=='backup':s['source']={'exchange':'bybit','market':'spot','fallback':True}
        return super().reply(status,data)

    def do_POST(self):
        if self.path!='/radar/alarms-api/change':return self.reply(405,{})
        try:
            assert self.headers.get('Authorization')=='Bearer synthetic_fixture_only'
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if data.get('action')!='save':return self.reply(405,dict(error='Fixture accepts only synthetic saves'))
            refresh();result=store.mutate('fixture',data,market.quotes)
            if scaled:
                now=time.time()
                for offset in (6,4,2):store.tick(scaled_book(now-offset),now-offset)
                refresh()
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
            import re
            raw=re.sub(rb'(<body\b[^>]*>)',rb'\1<script>localStorage.setItem("radar-settings-token","synthetic_fixture_only");</script>',raw,count=1)
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(chosen))[0] or 'application/octet-stream');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)

print('Isolated form fixture: http://127.0.0.1:18794/radar/robot-push/alarms/',flush=True)
try:ThreadingHTTPServer(('127.0.0.1',18794),Handler).serve_forever()
finally:market.pool.shutdown();store.db.close();temp.cleanup()
