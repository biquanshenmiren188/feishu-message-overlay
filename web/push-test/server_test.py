import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from server import Trial, rows_for, validate_subscription, compact_rows


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        config = self.root / 'config.json'
        config.write_text(json.dumps({'pairCode': '12345678', 'expiresAt': time.time()+3600, 'publicKey':'test'}))
        self.sent = []
        self.app = Trial(self.root / 'state', config, lambda sub,payload:self.sent.append(payload) or 201)

    def test_internal_alarm_identity_is_small_and_authenticated(self):
        from server import handler
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import threading
        token=self.app.pair('12345678')
        cls=handler(self.app)
        http=ThreadingHTTPServer(('127.0.0.1',0),cls)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            url=f'http://127.0.0.1:{http.server_port}/internal/alarm-identity'
            with patch.object(self.app,'public_status',side_effect=AssertionError('heavy status must not run')):
                with urlopen(Request(url,headers={'Authorization':'Bearer '+token})) as r:
                    self.assertEqual(json.load(r),{'profileId':'legacy'})
                with self.assertRaises(HTTPError) as caught:urlopen(url)
                self.assertEqual(caught.exception.code,401)
            fake=object.__new__(cls);fake.path='/internal/alarm-identity';fake.client_address=('192.0.2.1',1000);result=[];fake.reply=lambda status,body:result.append(status)
            fake.do_GET();self.assertEqual(result,[404])
        finally:http.shutdown();http.server_close()

    def test_resend_one_four_entry_notification(self):
        self.app.state['subscription'] = {'test': True}
        self.app.state['seq'] = 7
        result = self.app.resend()
        self.assertEqual(result['http'], 201)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0]['seq'], 8)
        self.assertEqual(len(self.sent[0]['rows']), 4)
        self.assertEqual(self.sent[0]['title'], '')
        self.assertTrue(self.sent[0]['rows'][-1].endswith('ETH'))
        with self.assertRaises(ValueError):self.app.resend()
        self.assertEqual(len(self.sent), 1)

    def test_window_and_order(self):
        for step in range(1,8):
            rows=rows_for(step,0)
            self.assertEqual(len(rows),min(step,6))
        self.assertTrue(rows_for(1,0)[0].startswith('ARC '))
        final=rows_for(7,0)
        self.assertTrue(final[0].startswith('BLUR '))
        self.assertTrue(final[-1].startswith('ETH '))
        self.assertFalse(any(x.startswith('ARC ') for x in final))

    def test_pair_auth_and_redaction(self):
        with self.assertRaises(ValueError):self.app.pair('incorrect')
        token=self.app.pair('12345678')
        self.assertTrue(self.app.authenticate(token))
        self.assertFalse(self.app.authenticate('bad'))
        self.app.state['subscription']={'endpoint':'https://private.push.apple.com/secret'}
        public=json.dumps(self.app.public_status())
        self.assertNotIn(token,public)
        self.assertNotIn('/secret',public)

    def test_reject_untrusted_push_endpoints(self):
        for endpoint in ['http://127.0.0.1/','https://push.apple.com.evil.test/a','https://x.push.apple.com:443@127.0.0.1/a','https://x.push.apple.com:444/a',
                         'https://fcm.googleapis.com.evil.test/wp/a', 'https://evil.fcm.googleapis.com/wp/a',
                         'https://fcm.googleapis.com/v1/projects/a', 'https://fcm.googleapis.com:444/wp/a',
                         'https://fcm.googleapis.com@127.0.0.1/wp/a', 'https://fcm.googleapis.com/wp/a#secret',
                         'https://updates.push.services.mozilla.com.evil.test/wpush/v2/a',
                         'https://127.0.0.1/wp/a', 'https://fcm.googleapis.com\n/wp/a', None]:
            with self.assertRaises(ValueError):validate_subscription({'endpoint':endpoint})

    def test_accept_android_webpush_and_keep_apple_compatible(self):
        import base64
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')
        keys = dict(p256dh=encode(key), auth=encode(b'0'*16))
        for endpoint in ['https://fcm.googleapis.com/wp/fixture', 'https://fcm.googleapis.com/fcm/send/fixture',
                         'https://updates.push.services.mozilla.com/wpush/v2/fixture', 'https://fixture.push.apple.com/fixture']:
            sub = dict(endpoint=endpoint, keys=keys)
            self.assertEqual(validate_subscription(sub), sub)
            with self.assertRaises(ValueError): validate_subscription(dict(sub, keys=dict(keys, auth='bad')))

    def test_binding_requires_owner_token_and_is_not_cached(self):
        from http.server import ThreadingHTTPServer
        from http.client import HTTPConnection
        from threading import Thread
        from server import handler, BASE
        token = self.app.pair('12345678')
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.app))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for bearer, expected in [('', 401), ('wrong', 401), (token, 200)]:
                connection = HTTPConnection(*server.server_address)
                connection.request('GET', BASE+'api/binding', headers={'Authorization':'Bearer '+bearer})
                response = connection.getresponse()
                value = json.loads(response.read())
                self.assertEqual(response.status, expected)
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                if expected == 200:
                    self.assertEqual(value, {'pushCode':'12345678'})
                else:
                    self.assertNotIn('12345678', json.dumps(value))
                connection.close()
            self.assertNotIn('12345678', json.dumps(self.app.public_status()))
            self.assertFalse(self.sent)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_bounded_campaign_no_real_input(self):
        self.app.state['subscription']={'synthetic':True}
        with patch('threading.Thread'):
            self.app.start()
            with self.assertRaises(ValueError):self.app.start()
        c=self.app.state['campaign']
        # A timestamp in the past eliminates waits without altering production interval.
        self.app.run_campaign(c['run'],time.time()-300,self.app.stop_event)
        self.assertEqual(len(self.sent),7)
        self.assertEqual([len(p['rows']) for p in self.sent],[1,2,3,4,4,4,4])
        self.assertTrue(self.sent[-1]['rows'][0].endswith('ZEREBRO'))
        self.assertTrue(self.sent[-1]['rows'][-1].endswith('ETH'))
        self.assertEqual(self.app.state['campaign']['state'],'complete')
        self.assertEqual([p['seq'] for p in self.sent],list(range(1,8)))

    def test_stop_prevents_future_sends(self):
        self.app.state['subscription']={1:True}
        with patch('threading.Thread'):self.app.start()
        self.app.stop()
        c=self.app.state['campaign']
        self.app.run_campaign(c['run'],time.time()-300,self.app.stop_event)
        self.assertEqual(self.sent,[])

    def test_user_exchange_labels_and_large_rank_preserved(self):
        self.assertEqual(compact_rows(['BTC FF BYBIT→HYPERLIQUID R1000+ +0.10% 00:39:22']),
                         ['00:39 +0.10% R1000+ FF BY→HY BTC'])

    def test_failure_stops_and_does_not_log_secret(self):
        self.app.state['subscription']={1:True}
        def fail(*args):raise RuntimeError('secret-endpoint')
        self.app.sender=fail
        with patch('threading.Thread'):self.app.start()
        c=self.app.state['campaign']
        self.app.run_campaign(c['run'],time.time()-300,self.app.stop_event)
        self.assertEqual(len(self.app.state['sends']),1)
        self.assertEqual(c['state'],'failed')
        self.assertNotIn('secret-endpoint',json.dumps(self.app.public_status()))

    def test_restart_does_not_resume(self):
        self.app.state['subscription']={1:True}
        with patch('threading.Thread'):self.app.start()
        other=Trial(self.root/'state',self.root/'config.json')
        self.assertEqual(other.state['campaign']['state'],'interrupted')


if __name__=='__main__':unittest.main()
