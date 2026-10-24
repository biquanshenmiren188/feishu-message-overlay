import copy, json, tempfile, threading, time, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from profiles import Profiles
from desktop_rules import DesktopRules
from desktop_binding import DesktopProfiles
from server import handler, BASE


class DesktopBindingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        config = self.root/'config.json'
        config.write_text(json.dumps(dict(pairCode='12345678', expiresAt=0, publicKey='fixture')))
        self.sent = []
        self.profiles = Profiles(self.root/'state', config, lambda *a:self.sent.append(a))
        self.codes = [self.profiles.create_code(str(n)*32) for n in (1, 2)]
        self.accounts = [self.profiles.resolve(c['token']) for c in self.codes]
        self.feed = self.root/'feed.json'; self.cards = self.root/'cards.json'
        self.feed.write_text(json.dumps(dict(messages=[dict(id='a'*64, senderType='bot', title='BTC | FF | R2 +1.13%', body='买 BINANCE 永续 → 卖 GATE 永续', sentAt=datetime.now(timezone.utc).isoformat())])))
        self.cards.write_text(json.dumps(dict(snapshot=dict(complete=True, active=[dict(id='one',pair='pair-one',asset='BTC',strategy='FF',validUntil=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat(),v2Residual=dict(level=2,bps=113),details=dict(legs=[dict(exchange='binance'),dict(exchange='gate')]))]))))
        self.legacy = DesktopRules(self.profiles.directory, self.feed, self.cards)
        self.bindings = DesktopProfiles(self.profiles, self.legacy)

    def data(self, n=0):
        return dict(pushCode=self.codes[n]['pushCode'], client='a'*16)

    def test_unbound_allows_everything_without_reading_or_writing_any_profile(self):
        self.legacy.data['desktop']['settings']['notify_enabled'] = False
        self.legacy.data['cards']['settings']['notify_enabled'] = False
        before = {p:p.read_bytes() for p in self.profiles.directory.rglob('*') if p.is_file()}
        with patch.object(self.legacy, 'evaluate', side_effect=AssertionError('unbound consulted owner')):
            result = self.bindings.state(dict(pushCode='', client='a'*16))
        self.assertEqual(result['pushBinding'], dict(protocol=1,bound=False,canManage=False))
        self.assertEqual(result['desktopRules'], dict(revision=0,messages={},cards={},desktopEnabled=True,cardsEnabled=True))
        self.assertEqual(before, {p:p.read_bytes() for p in self.profiles.directory.rglob('*') if p.is_file()})

    def test_valid_polling_is_read_only_for_phone_and_does_not_consume_pair_budget(self):
        before = {a.profile_id:a.path.read_bytes() for a in self.profiles.accounts.values()}
        with patch.object(self.profiles, 'pair', side_effect=AssertionError('must not pair phone')):
            for _ in range(20):
                result = self.bindings.state(self.data())
                self.assertEqual(result['pushBinding'], dict(protocol=1,bound=True,canManage=True))
        self.assertEqual(before, {a.profile_id:a.path.read_bytes() for a in self.profiles.accounts.values()})
        self.assertEqual(self.profiles.desktop_code_attempts, {})
        self.assertEqual(self.legacy.last_seen, 0)
        self.assertEqual(self.bindings.policy(self.accounts[1]).last_seen, 0)
        self.assertGreater(self.bindings.policy(self.accounts[0]).last_seen, 0)
        self.assertEqual(self.sent, [])

    def test_profile_isolation_edit_and_restart_keep_owner_and_other_phone_untouched(self):
        before = {a.profile_id:copy.deepcopy(a.state) for a in self.profiles.accounts.values()}
        operation = dict(op='block',request=dict(requestId='profile-test-001',coins=['BTC'],exchange='all'))
        self.bindings.coins(dict(self.data(),request=operation))
        blocked = self.bindings.state(self.data())['desktopRules']
        self.assertEqual(blocked['messages'], {'a'*64:'hide'})
        self.assertEqual(blocked['cards'], {'pair-one':'hide'})
        self.assertEqual(self.bindings.state(self.data(1))['desktopRules']['messages'], {})
        self.assertEqual(self.legacy.evaluate()['messages'], {})
        for a in [self.profiles.accounts['legacy'], self.accounts[1]]:
            self.assertEqual(a.state, before[a.profile_id])
        restarted = DesktopProfiles(self.profiles, self.legacy)
        self.assertEqual(restarted.state(self.data())['desktopRules']['messages'], {'a'*64:'hide'})
        self.assertNotIn('pushCode', json.dumps(blocked))
        self.assertEqual(self.sent, [])

    def test_wrong_revoked_or_unbound_code_cannot_edit_and_never_falls_back(self):
        wrong = dict(pushCode='00000000', client='b'*16)
        with self.assertRaises(ValueError):self.bindings.state(wrong)
        with self.assertRaises(ValueError):self.bindings.coins(dict(pushCode='',client='a'*16,request={'op':'state'}))
        account = self.accounts[0]
        del self.profiles.accounts[account.profile_id]
        with self.assertRaises(ValueError):self.bindings.state(self.data())
        with self.assertRaises(ValueError):self.bindings.policy(account)
        with self.assertRaises(ValueError):self.bindings.state(dict(self.data(1),profileId='legacy'))
        self.assertEqual(self.legacy.status()['revision'],0)

    def test_invalid_attempts_rate_limited_per_signed_client(self):
        for _ in range(10):
            with self.assertRaisesRegex(ValueError,'无效'):self.profiles.desktop_account('00000000','a'*16)
        with self.assertRaisesRegex(ValueError,'频繁'):self.profiles.desktop_account(self.codes[0]['pushCode'],'a'*16)
        self.assertIs(self.profiles.desktop_account(self.codes[0]['pushCode'],'b'*16),self.accounts[0])

    def test_http_scoped_reads_edits_binding_and_origin_guard(self):
        # Use realistic isolated feed files while exercising the real HTTP router.
        constructor = DesktopRules
        with patch('desktop_rules.DesktopRules',side_effect=lambda directory,*a:constructor(directory,self.feed,self.cards)):
            http = ThreadingHTTPServer(('127.0.0.1',0),handler(self.profiles))
        thread = threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        def request(path,data=None,token='',origin=None):
            conn = HTTPConnection(*http.server_address)
            headers={'Content-Type':'application/json','Authorization':'Bearer '+token}
            if origin:headers['Origin']=origin
            conn.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),headers)
            response=conn.getresponse();status=response.status;body=json.loads(response.read());conn.close();return status,body
        try:
            code = self.codes[0]
            self.assertEqual(request('/internal/desktop-binding',self.data())[0],200)
            self.assertEqual(request('/internal/desktop-binding',dict(self.data(),pushCode='00000000'))[0],400)
            self.assertEqual(request('/internal/desktop-binding',self.data(),origin='https://evil.invalid')[0],403)
            self.assertEqual(request(BASE+'api/coin-blocks',token='wrong')[0],401)
            state=request(BASE+'api/coin-blocks',token=code['token'])[1]
            self.assertEqual(state['desktop']['revision'],0)
            edit=dict(requestId='http-test-001',changes=[dict(channel='cards',coin='BTC',exchange='all',before=None,after=True)])
            self.assertEqual(request(BASE+'api/edit-coins',edit,code['token'])[0],200)
            result=request('/internal/desktop-binding',self.data())[1]
            self.assertEqual(result['desktopRules']['cards'],{'pair-one':'hide'})
            self.assertEqual(request('/internal/desktop-binding',self.data(1))[1]['desktopRules']['cards'],{})
            self.assertEqual(request(BASE+'api/card-decisions',token=code['token'])[1]['decisions'],{'pair-one':'hide'})
            self.assertEqual(request(BASE+'api/coin-blocks',token=self.codes[1]['token'])[1]['desktop']['revision'],0)
        finally:http.shutdown();http.server_close();thread.join()


if __name__ == '__main__':unittest.main()
