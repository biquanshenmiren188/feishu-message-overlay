import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from server import Store, Failure, make_handler, BASE

TOKEN = 'synthetic_token_1234567890'


class CenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.calls = []
        self.fail_alarm = False
        def upstream(service, route, token='', data=None, client='127.0.0.1'):
            self.calls.append((service, route, token, data, client))
            if route == 'pair': return dict(token=TOKEN)
            if route == 'create-code': return dict(token=TOKEN, pushCode='12345678')
            if token != TOKEN: raise Failure(401, '未连接')
            if route == 'status': return dict(profileId='legacy', subscribed=True, settings={'notify_enabled':True}, device={'permission':'granted'}, subscriptionFingerprint='not-exported')
            if route == 'binding': return dict(pushCode='12345678')
            if route == 'desktop-settings': return dict(connected=True, desktop={'private':'not-exported'})
            if route == 'state':
                if self.fail_alarm: raise Failure(503, '报警服务暂不可用')
                return dict(revision=2, device={'label':'Phone'}, enabled=True, rules=['not-exported'])
            if route == 'change': return dict(ok=True, revision=3)
            if route == 'verify': return dict(ok=True)
            raise AssertionError(route)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,upstream))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.store.db.close();self.tmp.cleanup()

    def request(self, route, data=None, token=TOKEN, origin=None):
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','CF-Connecting-IP':'192.0.2.5'}
        if origin: headers['Origin']=origin
        req=Request(f'http://127.0.0.1:{self.server.server_port}{BASE}{route}',headers=headers,data=None if data is None else json.dumps(data).encode())
        try:
            with urlopen(req) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def test_old_identity_full_code_and_minimal_state(self):
        status,v=self.request('state');self.assertEqual(status,200)
        self.assertEqual(v['pushCode'],'12345678');self.assertEqual(v['profileId'],'legacy')
        self.assertTrue(v['desktop']['connected']);self.assertNotIn('not-exported',json.dumps(v))
        self.assertEqual(len(list(Path(self.tmp.name).glob('*.sqlite3'))),1)

    def test_unauthorized_no_partial_read(self):
        self.assertEqual(self.request('state',token='wrong')[0],401);self.assertEqual(self.calls,[])
        self.assertEqual(self.request('state',token='unknown_token_1234567890')[0],401)

    def test_external_origin_denied(self):
        self.assertEqual(self.request('pair',{'code':'12345678'},origin='https://elsewhere.test')[0],403)
        self.assertEqual(self.calls,[])

    def test_pair_preserves_client_rate_limit_identity(self):
        self.assertEqual(self.request('pair',{'code':'12345678'},token='')[0],200)
        self.assertEqual(self.calls[0][-1],'192.0.2.5')

    def test_create_keeps_original_request_id(self):
        request={'requestId':'a'*32}
        self.request('create-code',request,token='')
        self.assertEqual(self.calls[0][3],request)

    def test_names_isolation_restart_and_idempotency(self):
        data=dict(requestId='a'*32,revision=0,name='主方案')
        self.assertEqual(self.store.rename('legacy',data)['revision'],1)
        self.assertEqual(self.store.rename('legacy',data)['revision'],1)
        self.assertEqual(self.store.view('other')['name'],'我的推送码')
        again=Store(self.tmp.name)
        self.assertEqual(again.view('legacy')['name'],'主方案');again.db.close()
        with self.assertRaises(Failure):self.store.rename('legacy',dict(data,name='其他名'))
        with self.assertRaises(Failure):self.store.rename('legacy',dict(data,requestId='b'*32))

    def test_rename_rejects_bad_input(self):
        for name in ['', 'a'*31, 'x\ny', 3]:
            self.assertEqual(self.request('rename',dict(requestId='a'*32,revision=0,name=name))[0],400)

    def test_service_failure_not_unbound(self):
        self.fail_alarm=True
        status,v=self.request('state');self.assertEqual(status,200)
        self.assertFalse(v['bark']['available']);self.assertNotIn('device',v['bark'])

    def test_bark_allowlist_and_revision_forwarding(self):
        self.assertEqual(self.request('bark',dict(requestId='b'*32,action='delete',revision=2))[0],400)
        body=dict(requestId='b'*32,action='bind',revision=2,key='synthetic_key',label='Phone')
        self.assertEqual(self.request('bark',body)[0],200)
        self.assertEqual(self.calls[-1][3],body)
        self.request('bark',body)
        self.assertEqual(len(self.store.view('legacy')['history']),1)
        dump='\n'.join(self.store.db.iterdump())
        self.assertNotIn('synthetic_key',dump);self.assertNotIn(TOKEN,dump)

    def test_no_arbitrary_proxy_or_query(self):
        for route in ['../status','state?profile=other','internal/desktop-state','binding']:
            self.assertEqual(self.request(route)[0],404)
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
