import unittest, tempfile, json
from pathlib import Path
from unittest.mock import patch
from delivery import fingerprint, with_fallback, vapid_headers, TTL, TOPIC
from server import Trial
import live_test as fixture
from live_test import message

class DeliveryTests(unittest.TestCase):
 def test_jwt_reused_for_hour_and_across_restart(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);key=root/'key';key.write_text('test-key')
   calls=[]
   def sign(claims):calls.append(claims);return {'Authorization':'token-'+str(len(calls))}
   first=vapid_headers(root,str(key),'https://a.push.apple.com/one','https://radar.test',signer=sign,now=10000)
   second=vapid_headers(root,str(key),'https://a.push.apple.com/two','https://radar.test',signer=sign,now=13599)
   self.assertEqual(first,second);self.assertEqual(len(calls),1)
   third=vapid_headers(root,str(key),'https://a.push.apple.com/two','https://radar.test',signer=sign,now=13600)
   self.assertNotEqual(first,third);self.assertEqual(len(calls),2)
   self.assertEqual(calls[0]['aud'],'https://a.push.apple.com')
 def test_fallback_is_complete_and_preserves_old_worker_payload(self):
  p={'kind':'radar-six-test','seq':123,'run':'live','title':'','rows':['10:01 +0.2% R0 SF GT→OK BTC','10:02 +0.3% R1000+ FF BY→HY ETH']}
  result=with_fallback(p,'https://radar.test')
  self.assertEqual(result['rows'],p['rows']);self.assertEqual(result['title'],'')
  self.assertEqual(result['web_push'],8030);self.assertTrue(result['mutable'])
  self.assertTrue(result['notification']['mutable']);self.assertTrue(result['notification']['title'])
  self.assertEqual(result['notification']['body'],'\n'.join(p['rows']))
  self.assertEqual(result['notification']['navigate'],'https://radar.test/radar/push-test/')
  self.assertLess(len(json.dumps(result).encode()),3000)
 def test_transport_uses_cached_authorization_and_coalesces_offline_messages(self):
  import types,sys
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);config=root/'config.json';config.write_text(json.dumps({'privateKeyPath':'test'}))
   app=Trial(root/'state',config)
   sent=[]
   def send(**kwargs):sent.append(kwargs);return types.SimpleNamespace(status_code=201)
   with patch.dict(sys.modules,pywebpush=types.SimpleNamespace(webpush=send)),patch('delivery.vapid_headers',return_value={'Authorization':'cached'}):
    app.send_webpush({'endpoint':'https://a.push.apple.com/x'},{'rows':['a']})
   self.assertEqual(sent[0]['ttl'],300);self.assertEqual(sent[0]['headers']['Topic'],TOPIC)
   self.assertEqual(sent[0]['headers']['Authorization'],'cached')
   self.assertNotIn('vapid_claims',sent[0])

class RecoveryTests(unittest.TestCase):
 setUp=fixture.LiveTests.setUp
 tick=fixture.LiveTests.tick
 settings=fixture.LiveTests.settings
 def test_saving_unchanged_settings_preserves_waiting_message(self):
  self.tick([message(1,self.now)])
  self.tick([message(2,self.now+10)],self.now+10)
  self.settings()
  self.tick([],self.now+60)
  self.assertEqual(len(self.sent),2)
  self.assertTrue(self.sent[-1]['rows'][-1].endswith('COIN2'))
 def test_phone_actual_subscription_mismatch_is_reported(self):
  self.app.device_status({'permission':'granted','subscriptionFingerprint':'a'*64,'version':'radar-delivery-v4'})
  self.assertFalse(self.app.public_status()['device']['matches'])
  fp=fingerprint(self.app.state['subscription'])
  self.app.device_status({'permission':'granted','subscriptionFingerprint':fp,'version':'radar-delivery-v4'})
  self.assertTrue(self.app.public_status()['device']['matches'])
  self.assertNotIn('test.push.apple.com',json.dumps(self.app.public_status()))
 def test_repair_compare_and_swap_cannot_overwrite_a_new_subscription(self):
  old=fingerprint(self.app.state['subscription']);new={'endpoint':'https://a.push.apple.com/new','keys':{'auth':'a','p256dh':'p'}}
  with patch('live.validate_subscription',return_value=new):
   with self.assertRaises(ValueError):self.app.repair_subscription(new,'wrong')
   self.app.repair_subscription(new,old)
   self.app.repair_subscription(new,old) # Idempotent retry.
  self.assertEqual(self.app.state['subscription'],new)
 def test_failed_receipt_does_not_expose_exception_text_or_keys(self):
  self.app.receipt({'seq':3,'stage':'worker-error','error':'NotAllowedError','endpoint':'secret','token':'secret','message':'secret'})
  item=self.app.state['receipts'][-1]
  self.assertEqual(item['error'],'NotAllowedError');self.assertNotIn('secret',json.dumps(item))
 def test_recovery_verification_is_one_notification_not_a_campaign(self):
  self.app.device_status({'permission':'granted','subscriptionFingerprint':fingerprint(self.app.state['subscription']),'version':'radar-delivery-v4'})
  result=self.app.verify_delivery()
  self.assertEqual(result['state'],'accepted');self.assertEqual(len(self.sent),1)
  self.assertEqual(len(self.sent[0]['rows']),4);self.assertEqual(self.sent[0]['run'],'verify')
  with self.assertRaises(ValueError):self.app.verify_delivery()
  self.assertEqual(len(self.sent),1)
 def test_known_missing_phone_subscription_does_not_send_to_stale_address(self):
  self.app.device_status({'permission':'default','subscriptionFingerprint':None,'version':'radar-delivery-v4'})
  self.tick([message(1,self.now)])
  self.assertFalse(self.sent)
  self.assertEqual(len(self.app.state['live']['pending']),1)
 def test_only_capable_phone_gets_declarative_event(self):
  payload={'kind':'radar-six-test','seq':1,'run':'live','title':'','rows':['row']}
  self.assertNotIn('web_push',self.app.notification_payload(payload))
  self.app.state['device']={'version':'radar-delivery-v4'}
  self.assertNotIn('web_push',self.app.notification_payload(payload))
  self.app.state['device']={'version':'radar-delivery-v5'}
  self.assertEqual(self.app.notification_payload(payload)['web_push'],8030)
