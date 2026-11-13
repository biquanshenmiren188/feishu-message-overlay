"""Explicitly authorized three-notification acceptance; real time and real Bark.
Read production config/device only. All rule/feed changes live in a temporary DB.
Usage: sudo python accept-selected-backup-phone.py --send-three UNIQUE_RUN_ID
No automatic retry or extra test notifications. Does not modify UI/services/rules.
"""
import fcntl,hashlib,json,os,re,sqlite3,sys,tempfile,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from cryptography.fernet import Fernet

assert len(sys.argv)==3 and sys.argv[1]=='--send-three'
run_id=sys.argv[2];assert re.fullmatch('[a-z0-9-]{8,80}',run_id)
backend=Path('/opt/radar-alarms/current').resolve()
sys.path.insert(0,str(backend))
from engine import validate
from sources import backup_venues
from store import Store
from market import Market,VENUES
from server import send_event

root=Path('/var/lib/radar-alarms')
def read_original():
 with sqlite3.connect('file:'+str(root/'alarms.sqlite3')+'?mode=ro',uri=True) as db:
  rows=db.execute('SELECT id,profile,config FROM rules ORDER BY id').fetchall()
  devices=db.execute('SELECT profile,fingerprint,secret,label FROM devices ORDER BY profile').fetchall()
  profiles=db.execute('SELECT id,revision,enabled FROM profiles ORDER BY id').fetchall()
  digest=hashlib.sha256(json.dumps([rows,devices,profiles]).encode()).hexdigest()
  return rows,devices,digest

def emit(kind,**fields):
 print(json.dumps(dict(kind=kind,**fields),ensure_ascii=False),flush=True)

def china(stamp):return datetime.fromtimestamp(stamp,timezone(timedelta(hours=8))).isoformat(timespec='milliseconds')

lock=open('/tmp/radar-phone-acceptance.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# A failed/uncertain run is never blindly repeated.
marker=Path('/tmp/radar-phone-acceptance-'+run_id+'.started')
with marker.open('x') as f:f.write('authorized three notifications; '+china(time.time()))
rows,devices,before=read_original()
choices=[(p,json.loads(raw)) for _,p,raw in rows if json.loads(raw)['exchange']=='binance' and json.loads(raw)['symbol']=='BTCUSDT']
assert len(choices)==1,'Target rule is not unique'
profile,original=choices[0]
receivers=[d for d in devices if d[0]==profile];assert len(receivers)==1,'Device binding is not unique'
allowed=list(backup_venues(original));assert allowed,'No selected backup source'
assert original['condition']=='below' and original['repeat'] and original['enabled']
receiver=receivers[0]
base='BTC';target=Decimal(original['target']);clear=str(target+100);hit=str(target-1)
config=validate(dict(original,fallbackExchanges=allowed,enabled=True,repeat=True,immediate=True,expiresAt=None))
phase={'failed':False,'price':clear}
class SimulatedMarket(Market):
 def fetch(self,exchange,market):
  if phase['failed'] and (exchange,market)==(config['exchange'],config['market']):
   raise TimeoutError('authorized isolated main-feed outage')
  now=time.time()
  symbol=base+('-USDT-SWAP' if market=='future' else '-USDT') if exchange=='okx' else base+'_USDT' if exchange=='gate' else base+'USDT'
  q=dict(exchange=exchange,market=market,symbol=symbol,base=base,quote='USDT',unit=base,instrumentVerified=True,last=phase['price'],lastAt=now,observedAt=now)
  return {(exchange,market,symbol):q}

market=None;store=None;sent=[];started=time.monotonic();restored_at=None;warm_at=None;main_failed_at=None;last_route=None
import secrets
try:
 with tempfile.TemporaryDirectory(prefix='radar-phone-acceptance-') as temp:
  try:
   store=Store(temp);market=SimulatedMarket()
   store.cipher=Fernet((root/'bark-encryption.key').read_bytes())
   with store.db:
    store.ensure('acceptance')
    store.db.execute('INSERT INTO devices VALUES (?,?,?,?)',('acceptance',receiver[1],receiver[2],'authorized test recipient'))
   primary=market.fetch(config['exchange'],config['market'])
   store.mutate('acceptance',dict(action='save',rule=config,requestId=secrets.token_hex(16),revision=0),primary)
   active={(v,m) for v in VENUES for m in ('spot','future')}
   emit('started',backend=str(backend),main=config['exchange'],selected=allowed,notificationLimit=3)
   while True:
    assert time.monotonic()-started<180,'Acceptance deadline exceeded; no retry'
    market.poll(active)
    quotes,_=market.snapshot();now=time.time();store.tick(quotes,now)
    view=store.view('acceptance');state=view['rules'][0]['state']
    route=state.get('sourceStatus'),(state.get('source') or {}).get('exchange')
    if route!=last_route:
     emit('route',status=route[0],exchange=route[1],at=china(now));last_route=route
    if not phase['failed'] and restored_at is None:
     qualified=state.get('qualifiedSources',{})
     if any(q.get('count',0)>=3 for q in qualified.values()):
      phase.update(failed=True,price=hit);main_failed_at=time.monotonic()
      emit('main_outage_simulated',at=china(now),threshold=str(target),simulatedPrice=hit)
    if state.get('sourceStatus')=='fallback':
     assert state['source']['exchange'] in allowed
    event=store.claim()
    if event:
     assert len(sent)<3 and restored_at is None,'Unexpected fourth event'
     payload=json.loads(event['payload'])
     assert payload['source']['fallback'] and payload['source']['exchange'] in allowed
     assert payload['price']==hit
     payload['title']='【断流验收 '+str(len(sent)+1)+'/3】'+payload['title']
     payload['body']='测试通知：模拟行情，非实时价格。主源断流后使用已勾选的备用源。\n'+payload['body']
     payload['url']='https://leida.shenmiren.work/radar/robot-push/alarms/'
     with store.db:store.db.execute('UPDATE events SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),event['id']))
     event['payload']=json.dumps(payload,ensure_ascii=False)
     attempt=time.time();attempt_mono=time.monotonic()
     # Production send_event, real HTTPS request, no mock and no retry.
     send_event(store,event,market)
     row=store.db.execute('SELECT status,attempts,error FROM events WHERE id=?',(event['id'],)).fetchone()
     dispatch=json.loads(store.db.execute('SELECT state FROM rules').fetchone()[0]).get('lastDispatch')
     item=dict(number=len(sent)+1,at=china(dispatch or attempt),dispatch=dispatch,source=payload['source']['exchange'],status=row['status'],attempts=row['attempts'])
     if sent:item['intervalSeconds']=round(dispatch-sent[-1]['dispatch'],3) if dispatch else None
     sent.append(item);emit('sent',**item)
     assert row['status']=='accepted' and row['attempts']==1,'Bark did not confirm acceptance; stopping without retry'
     if len(sent)>1:assert 30<=item['intervalSeconds']<=32,'Dispatch interval outside acceptance range'
     if len(sent)==3:
      phase.update(failed=False,price=clear);restored_at=time.monotonic()
      emit('test_feed_restored',at=china(time.time()),watchSeconds=32)
    if restored_at is not None and time.monotonic()-restored_at>=32:
     assert state.get('sourceStatus')=='primary' and state.get('status')=='watching'
     assert len(view['events'])==3 and all(e['status']=='accepted' for e in view['events'])
     break
    time.sleep(.1)
  finally:
   if market is not None:market.pool.shutdown(wait=True)
   if store is not None:store.db.close()
finally:
 _,_,after=read_original()
 emit('finished',notifications=len(sent),originalConfigAndBindingUnchanged=(before==after),temporaryStateRemoved=True)
 assert before==after,'Production config changed during test; inspect without overwriting'
