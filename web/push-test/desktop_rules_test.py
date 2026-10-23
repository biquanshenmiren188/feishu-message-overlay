import copy,json,tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from desktop_rules import DesktopRules

class DesktopRulesTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.feed=self.root/'feed.json';self.cards=self.root/'cards.json'
  self.message=dict(id='a'*64,senderType='bot',title='BTC | FF | R2 +1.13%',body='买 BINANCE 永续 → 卖 GATE 永续',sentAt=datetime.now(timezone.utc).isoformat())
  self.feed.write_text(json.dumps(dict(messages=[self.message])))
  self.cards.write_text(json.dumps(dict(snapshot=dict(complete=True,active=[dict(id='one',pair='pair-one',asset='BTC',strategy='FF',validUntil=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat(),v2Residual=dict(level=2,bps=113),details=dict(legs=[dict(exchange='binance'),dict(exchange='gate')]))]))))
  self.app=DesktopRules(self.root,self.feed,self.cards)
 def tearDown(self):self.tmp.cleanup()
 def configure(self,channel='desktop',action='hide',change=None):
  state=self.app.status();s=state[channel]['rules'][action] if channel=='desktop' else state[channel]['settings'];change(s)
  return self.app.configure(dict(revision=state['revision'],channel=channel,settings=s,action=action))
 def test_defaults_do_not_change_delivery_or_write_settings(self):
  d=self.app.evaluate();self.assertEqual(d['messages'],{});self.assertEqual(d['cards'],{});self.assertFalse(self.app.path.exists())
 def test_mute_hide_independent_history_and_restart(self):
  self.configure(action='mute',change=lambda s:s['excluded_coins'].append('BTC'))
  d=self.app.evaluate();self.assertEqual(d['messages'],{'a'*64:'mute'});self.assertEqual(d['cards'],{})
  self.app.evaluate();self.assertEqual(len(self.app.status()['history']),1)
  self.configure('cards',change=lambda s:s['excluded_exchanges'].append('GATE'))
  d=self.app.evaluate();self.assertEqual(d['cards'],{'pair-one':'hide'});self.assertEqual(d['messages']['a'*64],'mute')
  restored=DesktopRules(self.root,self.feed,self.cards);self.assertEqual(restored.status()['history'],self.app.status()['history'])
 def test_side_market_conjunction_and_rank(self):
  self.configure(change=lambda s:s['advanced']['legRules'].append(dict(exchange='gate',side='left',market='perp',enabled=True)))
  self.assertEqual(self.app.evaluate()['messages'],{})
  self.configure(change=lambda s:s['advanced']['legRules'][0].update(side='right',market='spot'))
  self.assertEqual(self.app.evaluate()['messages'],{})
  self.configure(change=lambda s:s['advanced']['legRules'][0].update(market='perp'))
  self.assertEqual(self.app.evaluate()['messages']['a'*64],'hide')
 def test_disabled_hides_even_under_mute_and_rejects_stale_edit(self):
  self.configure(action='mute',change=lambda s:s.update(notify_enabled=False))
  self.assertEqual(self.app.evaluate()['messages']['a'*64],'hide')
  with self.assertRaises(ValueError):self.app.configure(dict(revision=0,channel='desktop',settings=self.app.status()['desktop']['settings'],action='hide'))
 def test_oi_missing_and_equal_boundary(self):
  self.configure(change=lambda s:s['advanced'].update(globalOI=100))
  now=time.time();self.app.oi._read=lambda ex,n:(ex,{ex+':BTCUSDT':dict(value=1e6,time=n*1000,basis='double-v1')})
  self.assertEqual(self.app.evaluate()['messages'],{})
  self.app.oi.cache['gate']['gate:BTCUSDT']['value']=999999
  self.assertEqual(self.app.evaluate()['messages']['a'*64],'hide')
 def test_unranked_topic_keeps_coin_and_direction_checks(self):
  m=dict(self.message,title='专题｜BTC｜FF｜BN → GT')
  rows=self.app.rows(m,time.time());self.assertEqual(rows[0]['coin'],'BTC');self.assertTrue(rows[0]['unranked'])

 def test_removed_cards_stay_blocked_through_expiry_and_restart(self):
  self.configure('cards',change=lambda s:s['advanced']['coins'].append(dict(coin='BTC',exchange='all',enabled=True)))
  now=time.time()
  with patch('desktop_rules.time.time',return_value=now):self.assertEqual(self.app.evaluate()['cards'],{'pair-one':'hide'})
  self.cards.write_text(json.dumps(dict(snapshot=dict(complete=True,active=[]))))
  with patch('desktop_rules.time.time',return_value=now+1):self.assertEqual(self.app.evaluate()['cards'],{'pair-one':'hide'})
  restored=DesktopRules(self.root,self.feed,self.cards)
  with patch('desktop_rules.time.time',return_value=now+29):self.assertEqual(restored.evaluate()['cards'],{'pair-one':'hide'})
  self.assertEqual(len([h for h in restored.status()['history'] if h['channel']=='cards']),1)
  with patch('desktop_rules.time.time',return_value=now+32):self.assertEqual(restored.evaluate()['cards'],{'pair-one':'hide'})
  with patch('desktop_rules.time.time',return_value=now+62):self.assertEqual(restored.evaluate()['cards'],{})

 def test_edit_applies_to_retained_cards_and_unblock_restores(self):
  now=time.time()
  with patch('desktop_rules.time.time',return_value=now):self.app.evaluate()
  self.cards.write_text(json.dumps(dict(snapshot=dict(complete=True,active=[]))))
  self.configure('cards',change=lambda s:s['excluded_coins'].append('BTC'))
  with patch('desktop_rules.time.time',return_value=now+2):self.assertEqual(self.app.evaluate()['cards'],{'pair-one':'hide'})
  self.configure('cards',change=lambda s:s.update(excluded_coins=[]))
  with patch('desktop_rules.time.time',return_value=now+3):self.assertEqual(self.app.evaluate()['cards'],{})

 def test_desktop_rule_sets_coexist_hide_wins_and_do_not_change_cards(self):
  self.configure(action='mute',change=lambda s:s['excluded_coins'].append('BTC'))
  self.configure(action='hide',change=lambda s:s['advanced']['legRules'].append(dict(exchange='gate',side='right',market='perp',enabled=True)))
  state=self.app.status();self.assertEqual(state['desktop']['rules']['mute']['excluded_coins'],['BTC'])
  self.assertEqual(state['desktop']['rules']['hide']['excluded_coins'],[])
  d=self.app.evaluate();self.assertEqual(d['messages']['a'*64],'hide');self.assertEqual(d['cards'],{})
  self.configure(action='hide',change=lambda s:s.update(advanced=copy.deepcopy(__import__('advanced_rules').DEFAULT)))
  self.assertEqual(self.app.evaluate()['messages']['a'*64],'mute')
  restored=DesktopRules(self.root,self.feed,self.cards)
  self.assertEqual(restored.evaluate()['messages']['a'*64],'mute')
  self.assertEqual([h['action'] for h in self.app.status()['history'] if h['channel']=='desktop'],['mute','hide'])

 def test_migrates_legacy_action_without_copying_rules_to_other_action(self):
  self.configure(action='mute',change=lambda s:s['excluded_coins'].append('BTC'))
  legacy=json.loads(self.app.path.read_text());del legacy['desktop']['rules'];self.app.path.write_text(json.dumps(legacy))
  migrated=DesktopRules(self.root,self.feed,self.cards);state=migrated.status()
  self.assertEqual(state['revision'],legacy['revision']);self.assertEqual(state['desktop']['rules']['mute']['excluded_coins'],['BTC'])
  self.assertEqual(state['desktop']['rules']['hide']['excluded_coins'],[])
  self.assertEqual(migrated.evaluate()['messages']['a'*64],'mute')

if __name__=='__main__':unittest.main()
