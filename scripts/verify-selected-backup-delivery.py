"""Read deployed modules; simulate feeds and Bark HTTP using an isolated temporary DB.

Usage: python verify-selected-backup-delivery.py /opt/radar-alarms/current
Never loads production rules/devices, sends notifications, or changes services.
"""
import json
from pathlib import Path
import secrets
import sys
from unittest.mock import patch

backend=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(backend))
from test_sources import OutageSimulationTests
from server import send_event

results=[]
venues=('binance','okx','bybit','bitget','gate','aster')
for main in venues:
 others=[v for v in venues if v!=main]
 selected=[others[1],others[-1]]
 first,second=selected
 for coin in ('BTC','ETH','SOL','DOGE','XRP','PEPE','JCT'):
  for condition in ('below','above'):
   case=OutageSimulationTests()
   try:
    store,market,failed,prices,step,start=case.run_scenario(main,coin,selected=selected)
    store.mutate('simulation',dict(action='bind',key='synthetic_selected_delivery_only',label='isolated',requestId=secrets.token_hex(16),revision=store.view('simulation')['revision']),market.snapshot()[0])
    with store.db:
     row=store.db.execute('SELECT id,config FROM rules').fetchone()
     config=json.loads(row['config']);config['condition']=condition
     store.db.execute('UPDATE rules SET config=? WHERE id=?',(json.dumps(config),row['id']))
    failed.add((main,'future'))
    hit='99' if condition=='below' else '101'
    clear='101' if condition=='below' else '99'
    prices['value']=hit;sent=[]
    with patch('server.build_opener') as transport:
     transport.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"code":200}'
     for seconds,expected_source,expected_count in [(19,first,1),(33,second,1),(48,second,1),(49,second,2),(78,second,2),(79,second,3)]:
      if seconds==33:failed.add((first,'spot'))
      state=step(seconds)
      assert state['source']['exchange']==expected_source and state['source']['fallback']
      event=store.claim()
      if event:
       send_event(store,event,market)
       request=transport.return_value.open.call_args.args[0];body=json.loads(request.data)
       assert request.full_url=='https://api.day.app/push' and request.get_method()=='POST'
       assert body['device_key']=='synthetic_selected_delivery_only'
       assert (body['level'],body['volume'],body['call'])==('critical',5,'1')
       assert expected_source.upper()+' · 现货' in body['body']
       assert '触发价格：'+hit+' USDT' in body['body']
       assert coin+'/USDT' in body['title']
       sent.append(dict(seconds=seconds-19,source=expected_source))
      assert transport.return_value.open.call_count==expected_count
     assert {e['status'] for e in store.view('simulation')['events']}=={'accepted'}
     prices['value']=clear;assert step(109)['status']=='watching';assert store.claim() is None
     prices['value']=hit;step(139);event=store.claim();assert event is not None
     market.quotes={};send_event(store,event,market)
     assert store.view('simulation')['events'][0]['status']=='cancelled'
     failed.add((second,'spot'));assert step(170)['status']=='stale';assert store.claim() is None
     assert transport.return_value.open.call_count==3
    results.append(dict(main=main,coin=coin,condition=condition,selected=selected,sent=sent,clearStops=True,staleQueueCancelled=True,uncheckedNeverUsed=True))
   finally:case.doCleanups()
print(json.dumps(dict(backend=str(backend),scenarios=results,passed=len(results),barkTransport='mocked; no external notifications'),ensure_ascii=False,indent=2))
