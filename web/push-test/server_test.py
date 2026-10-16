import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from server import Trial, rows_for, validate_subscription


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        config = self.root / 'config.json'
        config.write_text(json.dumps({'pairCode': '12345678', 'expiresAt': time.time()+3600, 'publicKey':'test'}))
        self.sent = []
        self.app = Trial(self.root / 'state', config, lambda sub,payload:self.sent.append(payload) or 201)

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

    def test_reject_non_apple_endpoints(self):
        for endpoint in ['http://127.0.0.1/','https://push.apple.com.evil.test/a','https://x.push.apple.com:443@127.0.0.1/a','https://x.push.apple.com:444/a']:
            with self.assertRaises(ValueError):validate_subscription({'endpoint':endpoint})

    def test_bounded_campaign_no_real_input(self):
        self.app.state['subscription']={'synthetic':True}
        with patch('threading.Thread'):
            self.app.start()
            with self.assertRaises(ValueError):self.app.start()
        c=self.app.state['campaign']
        # A timestamp in the past eliminates waits without altering production interval.
        self.app.run_campaign(c['run'],time.time()-300,self.app.stop_event)
        self.assertEqual(len(self.sent),7)
        self.assertEqual([len(p['rows']) for p in self.sent],[1,2,3,4,5,6,6])
        self.assertEqual(self.app.state['campaign']['state'],'complete')
        self.assertEqual([p['seq'] for p in self.sent],list(range(1,8)))

    def test_stop_prevents_future_sends(self):
        self.app.state['subscription']={1:True}
        with patch('threading.Thread'):self.app.start()
        self.app.stop()
        c=self.app.state['campaign']
        self.app.run_campaign(c['run'],time.time()-300,self.app.stop_event)
        self.assertEqual(self.sent,[])

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
