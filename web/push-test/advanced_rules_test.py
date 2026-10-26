import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from advanced_rules import DEFAULT,validate,reasons,OISnapshot
from oi_source_cache import OISourceCache
from preferences import DEFAULTS,matches
from live import Live
from live_test import message
from datetime import datetime,timezone

class AdvancedTests(unittest.TestCase):
 def setUp(self):
  self.a=copy.deepcopy(DEFAULT);self.now=time.time()
  self.row=dict(coin='BTC',buy='GATE',sell='BINANCE',mode='SF',rank='R5+',value='+0.50%',oiCheckedAt=self.now)
 def test_side_and_market_are_and_other_rules_are_or(self):
  self.a['legRules']=[dict(exchange='gate',side='left',market='perp',enabled=True)]
  self.assertFalse(reasons(self.row,self.a))
  self.row['mode']='FF';self.assertTrue(reasons(self.row,self.a))
  self.row.update(buy='BINANCE',sell='GATE');self.assertFalse(reasons(self.row,self.a))
  self.a['legRules'].append(dict(exchange='gate',side='right',market='all',enabled=True));self.assertTrue(reasons(self.row,self.a))
 def test_coin_scoped_and_paused(self):
  self.a['coins']=[dict(coin='BTC',exchange='okx',enabled=True)]
  self.assertFalse(reasons(self.row,self.a));self.a['coins'][0]['exchange']='gate';self.assertTrue(reasons(self.row,self.a))
  self.a['coins'][0]['enabled']=False;self.assertFalse(reasons(self.row,self.a))
 def test_oi_each_perp_and_equal_passes(self):
  self.a['globalOI']=100
  self.row['oi']={'right':dict(value=1000000,time=self.now*1000,basis='double-v1')}
  self.assertFalse(reasons(self.row,self.a)) # Spot is ignored.
  self.row['mode']='FF';self.assertTrue(reasons(self.row,self.a))
  self.row['oi']['left']=dict(value=999999,time=self.now*1000,basis='double-v1');self.assertTrue(reasons(self.row,self.a))
  self.row['oi']['left']['value']=1000000;self.assertFalse(reasons(self.row,self.a))
 def test_override_priority_and_explicit_no_limit(self):
  self.a['globalOI']=500;self.a['exchangeOI']['binance']=dict(mode='none',value=None)
  self.assertFalse(reasons(self.row,self.a))
  self.a['coinOI']=[dict(coin='BTC',exchange='binance',value=100,enabled=True)]
  self.assertTrue(reasons(self.row,self.a));self.a['coinOI'][0]['value']=None;self.assertFalse(reasons(self.row,self.a))
 def test_stale_future_wrong_basis_and_missing_policy(self):
  self.a['globalOI']=100
  for ts,basis in [(self.now*1000-300001,'double-v1'),(self.now*1000+30001,'double-v1'),(self.now*1000,'raw')]:
   self.row['oi']={'right':dict(value=1e9,time=ts,basis=basis)};self.assertTrue(reasons(self.row,self.a))
  self.a['missing']='allow';self.assertFalse(reasons(self.row,self.a))
 def test_bad_payloads_rejected(self):
  for value in (-1,float('nan'),True):
   self.a['globalOI']=value
   with self.assertRaises(ValueError):validate(self.a)
  self.a=copy.deepcopy(DEFAULT);self.a['exchangeOI']['binance']=dict(mode='custom',value=None)
  with self.assertRaises(ValueError):validate(self.a)
 def test_cache_exact_symbol_and_no_unconfigured_fetch(self):
  sources=OISourceCache();self.addCleanup(sources.close);snap=OISnapshot(source_cache=sources)
  with patch.object(snap,'_read') as read:
   snap.enrich([self.row],self.a,self.now);read.assert_not_called()
  self.a['globalOI']=100
  data={'binance:BTCUSDT':dict(value=1e6,time=self.now*1000,basis='double-v1')}
  with patch.object(snap,'_read',return_value=('binance',data)) as read:
   snap.enrich([self.row],self.a,self.now);snap.enrich([self.row],self.a,self.now+3);self.assertEqual(read.call_count,1)
  self.assertFalse(reasons(self.row,self.a));self.row['coin']='1000BTC';snap.enrich([self.row],self.a,self.now+4);self.assertTrue(reasons(self.row,self.a))
 def test_legacy_matches_unchanged_empty_advanced(self):
  for blocked in ([],['BTC']):
   s=dict(copy.deepcopy(DEFAULTS),excluded_coins=blocked)
   self.assertEqual(matches(self.row,s),matches(self.row,dict(s,advanced=copy.deepcopy(DEFAULT))))
 def test_migration_legacy_save_preserves_advanced_and_logs_no_replay(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);config=root/'config.json';config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='public')))
   sent=[];app=Live(root/'state',config,lambda *args:sent.append(args) or 201)
   app.state['subscription']={'endpoint':'https://test.push.apple.com/test','keys':{'p256dh':'test','auth':'test'}}
   before=copy.deepcopy(app.state);again=Live(root/'state',config,lambda *args:None)
   self.assertEqual(again.state,{k:v for k,v in before.items() if k!='subscription'})
   self.a['legRules']=[dict(exchange='okx',side='left',market='perp',enabled=True)]
   app.configure(dict(revision=0,settings=dict(copy.deepcopy(DEFAULTS),advanced=self.a)))
   app.configure(dict(revision=1,settings=copy.deepcopy(DEFAULTS)))
   self.assertEqual(app.state['live']['settings']['advanced'],self.a)
   feed=dict(sourceConnected=True,updatedAt=datetime.fromtimestamp(self.now,timezone.utc).isoformat(),messages=[message(1,self.now)])
   app.tick(feed,self.now);app.tick(feed,self.now+1)
   self.assertFalse(sent);self.assertEqual(len(app.public_status()['blockedHistory']),1)
   self.assertEqual(app.public_status()['blockedHistory'][0]['revision'],2)
   app.configure(dict(revision=2,settings=dict(copy.deepcopy(DEFAULTS),advanced=copy.deepcopy(DEFAULT))))
   app.tick(feed,self.now+2);self.assertFalse(sent)

if __name__=='__main__':unittest.main()
