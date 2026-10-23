import copy,json,tempfile,threading,time,unittest
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from desktop_rules import DesktopRules
from live import Live
from profiles import Profiles
from server import handler,BASE,ORIGIN

class CoinBlocksTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.config=self.root/'config.json';self.config.write_text(json.dumps(dict(pairCode='12345678',expiresAt=0,publicKey='fixture')))
  self.sent=[];self.phone=Live(self.root/'state',self.config,lambda *args:self.sent.append(args))
  self.app=DesktopRules(self.root/'state');self.request=dict(requestId='test-request-001',coins=['ptb','PTB'],exchange='gate')
 def test_all_channels_preserve_settings_mute_and_subscription(self):
  self.phone.state['subscription']={'endpoint':'https://fixture.push.apple.com/fixture','keys':{'p256dh':'fixture','auth':'fixture'}};before=copy.deepcopy(self.phone.state)
  self.app.data['desktop']['action']='mute';self.app.data['desktop']['settings']=copy.deepcopy(self.app.data['desktop']['rules']['mute'])
  self.app.data['desktop']['rules']['mute']['excluded_coins']=['MITO']
  self.app.data['desktop']['rules']['hide']['advanced']['globalOI']=123
  mute=copy.deepcopy(self.app.data['desktop']['rules']['mute'])
  result=self.app.block_coins(self.request,self.phone)
  self.assertTrue(all(x['state']=='saved' for x in result['operation']['results'].values()))
  for s in (result['desktop']['desktop']['rules']['hide'],result['desktop']['cards']['settings'],result['mobile']['settings']):self.assertIn(dict(coin='PTB',exchange='gate',enabled=True),s['advanced']['coins'])
  self.assertEqual(self.app.data['desktop']['rules']['mute'],mute);self.assertEqual(self.app.data['desktop']['action'],'mute')
  self.assertEqual(self.app.data['desktop']['rules']['hide']['advanced']['globalOI'],123)
  self.assertEqual(self.phone.state['subscription'],before['subscription']);self.assertEqual(self.phone.state['seq'],before['seq']);self.assertEqual(self.sent,[])
 def test_retry_is_idempotent_and_journal_survives_restart(self):
  first=self.app.block_coins(self.request,self.phone);version=self.phone.state['live']['revision']
  restored=DesktopRules(self.root/'state');second=restored.block_coins(self.request,self.phone)
  self.assertEqual(first['operation'],second['operation']);self.assertEqual(self.phone.state['live']['revision'],version);self.assertEqual(first['desktop']['revision'],second['desktop']['revision'])
  self.assertEqual(len(second['operations']),1)
  with self.assertRaises(ValueError):restored.block_coins(dict(self.request,coins=['OTHER']),self.phone)
 def test_partial_failure_then_only_failed_channel_retried(self):
  with patch.object(self.phone,'configure',side_effect=OSError('private path')):result=self.app.block_coins(self.request,self.phone)
  self.assertEqual(result['operation']['results']['mobile']['state'],'failed');self.assertNotIn('private path',json.dumps(result))
  desktop_revision=result['desktop']['revision'];result=self.app.block_coins(self.request,self.phone)
  self.assertEqual(result['desktop']['revision'],desktop_revision);self.assertTrue(all(x['state']=='saved' for x in result['operation']['results'].values()))
 def test_broader_and_disabled_rules_do_not_duplicate(self):
  for channel in ['desktop','cards']:
   settings=self.app.data['desktop']['rules']['hide'] if channel=='desktop' else self.app.data[channel]['settings']
   settings['advanced']['coins']=[dict(coin='PTB',exchange='all' if channel=='desktop' else 'gate',enabled=channel=='desktop')]
  self.phone.state['live']['settings']['excluded_coins']=['PTB']
  result=self.app.block_coins(self.request,self.phone)
  self.assertEqual(len(result['desktop']['desktop']['rules']['hide']['advanced']['coins']),1)
  self.assertTrue(result['desktop']['cards']['settings']['advanced']['coins'][0]['enabled'])
  self.assertEqual(result['mobile']['settings']['advanced']['coins'],[])
 def test_capacity_failure_is_reported_without_overwriting_rules(self):
  rules=[dict(coin='C'+str(i),exchange='all',enabled=True) for i in range(100)]
  self.app.data['cards']['settings']['advanced']['coins']=copy.deepcopy(rules)
  result=self.app.block_coins(self.request,self.phone)
  self.assertEqual(result['operation']['results']['cards']['state'],'failed');self.assertEqual(self.app.data['cards']['settings']['advanced']['coins'],rules)
  self.assertEqual(result['operation']['results']['desktop']['state'],'saved')
 def test_invalid_request_and_failed_intent_do_not_mutate_rules(self):
  for data in (dict(self.request,coins=['<script>']),dict(self.request,exchange='invalid'),dict(self.request,requestId='x'),dict(self.request,coins=[])):
   with self.assertRaises(ValueError):self.app.block_coins(data,self.phone)
  with patch.object(self.app,'save',side_effect=OSError('disk')):
   with self.assertRaises(OSError):self.app.block_coins(self.request,self.phone)
  self.assertEqual(self.app.status()['revision'],0);self.assertEqual(self.phone.state['live']['revision'],0);self.assertEqual(self.app.data.get('coinOperations'),[])
 def test_failed_desktop_write_restores_memory_and_records_failure(self):
  save=self.app.save;calls=0
  def flaky():
   nonlocal calls
   calls+=1
   if calls==3:raise OSError('disk')
   save()
  with patch.object(self.app,'save',side_effect=flaky):result=self.app.block_coins(self.request,self.phone)
  self.assertEqual(result['operation']['results']['cards']['state'],'failed');self.assertEqual(result['desktop']['cards']['settings']['advanced']['coins'],[])
  restored=DesktopRules(self.root/'state');self.assertEqual(restored.status(),self.app.status())
  result=restored.block_coins(self.request,self.phone);self.assertTrue(all(x['state']=='saved' for x in result['operation']['results'].values()))
 def test_owner_only_routes_and_origin(self):
  token=self.phone.pair('12345678');profiles=Profiles(self.root/'state',self.config,lambda *a:None)
  other=profiles.create_code('a'*32)['token'];server=ThreadingHTTPServer(('127.0.0.1',0),handler(profiles));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  def request(route,auth,data=None,origin=ORIGIN):
   conn=HTTPConnection(*server.server_address);conn.request('GET' if data is None else 'POST',BASE+'api/'+route,body=None if data is None else json.dumps(data),headers={'Authorization':'Bearer '+auth,'Origin':origin,'Content-Type':'application/json'});r=conn.getresponse();body=json.loads(r.read());conn.close();return r.status,body
  try:
   self.assertEqual(request('coin-blocks','wrong')[0],401);self.assertEqual(request('coin-blocks',other)[0],403)
   self.assertEqual(request('card-decisions','wrong')[0],401);self.assertEqual(request('card-decisions',other)[0],403)
   with patch.object(DesktopRules,'web_cards',return_value={'decisions':{},'cardsEnabled':True,'revision':0}):self.assertEqual(request('card-decisions',token)[0],200)
   self.assertEqual(request('block-coins',other,self.request)[0],403);self.assertEqual(request('block-coins',token,self.request,'https://evil.invalid')[0],403)
   self.assertEqual(request('block-coins',token,self.request)[0],200);self.assertEqual(request('coin-blocks',token)[0],200)
   edit=dict(requestId='owner-edit-001',changes=[dict(channel='mute',coin='TEST',exchange='gate',before=None,after=True)])
   self.assertEqual(request('edit-coins','wrong',edit)[0],401);self.assertEqual(request('edit-coins',other,edit)[0],403);self.assertEqual(request('edit-coins',token,edit,'https://evil.invalid')[0],403);self.assertEqual(request('edit-coins',token,edit)[0],200)
   self.assertEqual(profiles.resolve(other).state['live']['revision'],0)
  finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
