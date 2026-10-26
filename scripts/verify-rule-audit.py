"""Read-only production-source checks; no app constructors, sends or state writes."""
import json,time,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from advanced_rules import OISnapshot,DEFAULT,reasons
from signals import desktop_rows,parse_messages

now=time.time();reader=OISnapshot();report={'sources':{},'hlChecks':{}}
for ex in ('binance','bybit','bitget','okx','gate','aster','hyperliquid'):
    name,data=reader._read(ex,now)
    assert name==ex and data,ex+' missing source'
    report['sources'][ex]=len(data)
    if ex=='hyperliquid':
        for coin in ('BTC','HYPE'):
            value=data[ex+':'+coin+'USDT']
            row=dict(coin=coin,buy='HL',sell='BINANCE',mode='FS',oiCheckedAt=now,oi={'left':value})
            rule=dict(copy.deepcopy(DEFAULT),globalOI=50)
            assert not reasons(row,rule),(coin,reasons(row,rule))
            row['oiCheckedAt']=value['expiresAt']/1000+.001
            assert reasons(row,rule),coin+' deadline not enforced'
            report['hlChecks'][coin]={'value':value['value'],'nativeQuote':value['nativeQuote'],'expiryEnforced':True}
feed=json.loads(Path('/var/lib/robot-push/feed.json').read_text())
messages=list(feed.get('messages',[]))
if feed.get('pinned'):messages.append(feed['pinned'])
report['retainedMessages']={'total':len(messages),'desktopRecognized':sum(bool(desktop_rows(m,now)) for m in messages),
                            'mobileFreshRecognized':sum(bool(parse_messages(m,now)) for m in messages)}
print(json.dumps(report))
