"""Read-only official feeds; simulate primary outage only in private dictionaries.

No Store, production config, device key or notification transport is opened.
Usage: python verify-alarm-denominations.py BACKEND_DIR
"""
import concurrent.futures
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from denominations import REGISTRY, FUTURES, native
from market import Market, VENUES
from sources import identity, candidate, select
from engine import validate, number

market=Market();states={};rounds=[];errors=[]
try:
    for iteration in range(3):
        quotes={}
        def fetch(group):
            try:return group,market.fetch(*group),None
            except Exception as exc:return group,{},type(exc).__name__
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for group,rows,error in pool.map(fetch,[(v,m) for v in VENUES for m in ('future','spot')]):
                quotes.update(rows)
                if error:errors.append(dict(round=iteration,group=group,error=error))
        now=time.time();checks=[]
        for main, aliases in FUTURES.items():
            for base in aliases:
                symbol=native(main,'future',base);p=quotes.get((main,'future',symbol))
                if not p:continue
                a=identity(p)
                for (venue,kind,spot),q in quotes.items():
                    if venue==main or kind!='spot':continue
                    c=candidate(q,a)
                    if c is None:continue
                    key=main+':'+symbol+'>'+venue+':'+spot
                    r=validate(dict(exchange=main,market='future',symbol=symbol,priceType='last',condition='below',
                                    target=p['last'],repeat=True,fallbackExchanges=[venue]))
                    _,_,s=select(r,states.get(key,{}),quotes,now);states[key]=s
                    failed={k:v for k,v in quotes.items() if k!=(main,'future',symbol)}
                    chosen,_,out=select(r,s,failed,now)
                    checks.append(dict(key=key,raw=q['last'],converted=c['last'],primary=p['last'],
                        factor=c.get('conversionFactor','1'),ratio=str(number(c['last'])/number(p['last'])),
                        routed=bool(chosen and out['source'].get('fallback') and out['source']['exchange']==venue),
                        reason=out['routingReason']))
        rounds.append(checks)
        if iteration<2:time.sleep(2)
    print(json.dumps(dict(rounds=rounds,errors=errors,finalRoutes=sum(x['routed'] for x in rounds[-1]),
        finalCandidates=len(rounds[-1]),externalNotifications=0,productionMutations=0),ensure_ascii=False,indent=2))
finally:market.pool.shutdown()
