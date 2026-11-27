"""Multi-device acceptance against real Store/engine/sender with a fake HTTP boundary."""
import json
import secrets
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import threading
from store import Store, Conflict
from server import send_event, make_handler
from market import Market
from test_alarms import rule, quote


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.s=Store(self.temp.name);self.now=time.time()
        self.quotes={('binance','future','BTCUSDT'):quote(101,self.now)}
    def tearDown(self):
        self.s.db.close();self.temp.cleanup()
    def change(self,profile='a',**kw):
        return self.s.mutate(profile,dict(requestId=secrets.token_hex(16),revision=self.s.view(profile)['revision'],**kw),self.quotes)
    def bind(self,n):
        return self.change(action='bind',key='synthetic_device_'+str(n),label='设备 '+str(n))['id']
    def test_legacy_migration_preserves_cipher_rules_and_restarts(self):
        self.bind(1);self.change(action='save',rule=rule(repeat=True))
        raw=tuple(self.s.db.execute('SELECT profile,fingerprint,secret,label FROM devices').fetchone())
        configs=self.s.db.execute('SELECT id,profile,config FROM rules').fetchall()
        with self.s.db:
            self.s.db.execute('ALTER TABLE devices RENAME TO devices_new')
            self.s.db.execute('CREATE TABLE devices(profile TEXT PRIMARY KEY,fingerprint TEXT UNIQUE NOT NULL,secret TEXT NOT NULL,label TEXT NOT NULL)')
            self.s.db.execute('INSERT INTO devices VALUES (?,?,?,?)',raw);self.s.db.execute('DROP TABLE devices_new')
        self.s.db.close();self.s=Store(self.temp.name)
        self.assertEqual(tuple(self.s.db.execute('SELECT profile,fingerprint,secret,label FROM devices').fetchone()),raw)
        self.assertEqual([tuple(r) for r in self.s.db.execute('SELECT id,profile,config FROM rules')],[tuple(r) for r in configs])
        identity=self.s.device_list('a',True)[0]['id']
        self.s.db.close();self.s=Store(self.temp.name)
        self.assertEqual(self.s.device_list('a',True)[0]['id'],identity)
        self.assertEqual(self.s.device_list('a',True)[0]['key'],'synthetic_device_1')
    def test_add_duplicate_edit_unbind_isolated_and_no_secrets_in_state(self):
        a,b=self.bind(1),self.bind(2)
        self.change(action='save',rule=rule(repeat=True));self.s.tick(self.quotes,self.now)
        with self.assertRaisesRegex(ValueError,'已绑定'):self.bind(2)
        with self.assertRaises(Conflict):self.change('b',action='bind',key='synthetic_device_2',label='other')
        with self.assertRaises(ValueError):self.change('b',action='unbind',deviceId=a)
        with self.assertRaisesRegex(ValueError,'请选择'):self.change(action='unbind')
        before=self.s.device_list('a',True)
        self.change(action='bind',deviceId=a,key='synthetic_device_3',label='改名')
        self.assertEqual(self.s.device_list('a',True)[1],before[1])
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM events WHERE status='queued'").fetchone()[0],1)
        self.change(action='unbind',deviceId=a)
        self.assertEqual([d['id'] for d in self.s.device_list('a')],[b])
        self.assertEqual(len(self.s.view('a')['rules']),1)
        self.assertNotIn('synthetic_device',json.dumps(self.s.view('a')))
    def test_rename_same_key_does_not_cancel_pending(self):
        a=self.bind(1);self.change(action='test',deviceId=a)
        self.change(action='bind',deviceId=a,key='synthetic_device_1',label='重命名')
        self.assertIsNotNone(self.s.claim())
    def test_test_single_all_and_per_device_rate_limit(self):
        a,b=self.bind(1),self.bind(2)
        self.change(action='test',deviceId=a);self.change(action='test',deviceId=b)
        with self.assertRaises(ValueError):self.change(action='test')
        with patch('store.time.time',return_value=self.now+61):self.change(action='test')
        self.assertEqual(len(self.s.view('a',compact=True)['events']),2)
        self.assertEqual(len(self.s.view('a')['events']),4)
    def test_three_devices_three_rounds_one_failed_no_duplicate(self):
        for n in range(3):self.bind(n)
        self.change(action='save',rule=rule(repeat=True))
        sent=[]
        class MarketView:
            def snapshot(inner):return self.quotes,{}
        def transport(req,**kw):
            body=json.loads(req.data);sent.append((clock,body))
            if body['device_key']=='synthetic_device_1':raise TimeoutError()
            class Response:
                def __enter__(self):return self
                def __exit__(self,*_):pass
                def read(self,*_):return b'{"code":200}'
            return Response()
        for seconds in (0,29,30,59,60):
            clock=self.now+seconds;self.quotes={('binance','future','BTCUSDT'):quote(101,clock)}
            with patch('store.time.time',return_value=clock),patch('server.build_opener') as opener:
                opener.return_value.open.side_effect=transport
                self.s.tick(self.quotes,clock)
                while (event:=self.s.claim()) is not None:send_event(self.s,event,MarketView())
        self.assertEqual(len(sent),9)
        for n in range(3):
            rows=[(at,p) for at,p in sent if p['device_key']=='synthetic_device_'+str(n)]
            self.assertEqual([at-self.now for at,p in rows],[0,30,60])
            self.assertEqual(len({p['id'] for at,p in rows}),3)
            self.assertTrue(all((p['level'],p['call'],p['volume'])==('critical','1',5) for at,p in rows))
        self.assertEqual([e['status'] for e in self.s.view('a')['events']].count('accepted'),6)
        self.assertEqual([e['status'] for e in self.s.view('a')['events']].count('unknown'),3)
    def test_concurrent_claims_once_per_device(self):
        for n in range(3):self.bind(n)
        self.change(action='save',rule=rule(repeat=True));self.s.tick(self.quotes,self.now)
        with ThreadPoolExecutor(max_workers=8) as pool:
            events=[e for e in pool.map(lambda _:self.s.claim(),range(12)) if e]
            results=list(pool.map(lambda e:self.s.begin_send(e,self.quotes,self.now),events))
        self.assertEqual(len(events),3);self.assertEqual(results,[True]*3)
        self.assertFalse(self.s.begin_send(events[0],self.quotes,self.now))
    def test_late_device_does_not_delay_healthy_next_round_or_send_early(self):
        self.bind(1);self.bind(2);self.change(action='save',rule=rule(repeat=True));self.s.tick(self.quotes,self.now)
        first=self.s.claim();second=self.s.claim()
        self.assertTrue(self.s.begin_send(first,self.quotes,self.now))
        self.assertTrue(self.s.begin_send(second,self.quotes,self.now+5))
        self.s.finish(first,'accepted');self.s.finish(second,'accepted')
        at=self.now+30;self.quotes={('binance','future','BTCUSDT'):quote(101,at)}
        with patch('store.time.time',return_value=at):
            self.s.tick(self.quotes,at);a,b=self.s.claim(),self.s.claim()
            results=[self.s.begin_send(e,self.quotes,at) for e in (a,b)]
            self.assertEqual(sum(results),1);self.assertIsNone(self.s.claim())
        with patch('store.time.time',return_value=at+5):
            e=self.s.claim();self.assertTrue(self.s.begin_send(e,self.quotes,at+5))
    def test_new_device_next_round_only_and_remove_does_not_cancel_other(self):
        a=self.bind(1);self.change(action='save',rule=rule(repeat=True));self.s.tick(self.quotes,self.now)
        self.bind(2);self.assertEqual(len(self.s.view('a')['events']),1)
        self.change(action='unbind',deviceId=a)
        self.assertIsNone(self.s.claim())
        self.s.tick({('binance','future','BTCUSDT'):quote(101,self.now+30)},self.now+30)
        self.assertEqual([e['status'] for e in self.s.view('a')['events']].count('queued'),1)
    def test_one_shot_partial_delivery_does_not_rearm_for_sent_device(self):
        self.bind(1);self.bind(2);self.change(action='save',rule=rule(immediate=True));self.s.tick(self.quotes,self.now)
        a,b=self.s.claim(),self.s.claim();self.assertTrue(self.s.begin_send(a,self.quotes,self.now));self.s.finish(a,'accepted')
        self.assertFalse(self.s.begin_send(b,{},self.now+13))
        self.assertTrue(self.s.view('a')['rules'][0]['state']['fired'])
        self.s.tick({('binance','future','BTCUSDT'):quote(101,self.now+14)},self.now+14)
        self.assertEqual(len(self.s.view('a')['events']),2)
    def test_single_device_mode_is_scoped_and_cannot_become_broadcast(self):
        self.bind(0)
        foreign = self.change('b',action='bind',key='foreign_device_b',label='另外的方案')['id']
        for invalid in (None,'',foreign):
            with self.assertRaises(ValueError):
                self.change(action='test',deviceId=invalid,testMode='critical-once')
        with self.assertRaises(ValueError):
            self.change(action='test',testMode='critical')
        for i,mode in enumerate(('active','critical-once','critical'),1):
            selected = self.bind(i)
            self.change(action='test', deviceId=selected, testMode=mode)
            event = self.s.claim()
            with patch('server.build_opener') as make:
                make.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"code":200}'
                send_event(self.s,event)
                body = json.loads(make.return_value.open.call_args.args[0].data)
                self.assertEqual(body['device_key'],'synthetic_device_'+str(i))
                self.assertEqual(body['level'],'active' if mode=='active' else 'critical')
                self.assertEqual(body.get('call'), '1' if mode=='critical' else None)
                self.assertEqual(body.get('volume'), None if mode=='active' else 5)
            self.assertIsNone(self.s.claim())

    def test_reveal_endpoint_auth_scope_no_store(self):
        self.bind(1);market=Market()
        http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.s,market,lambda token:token if token in ('a','b') else None))
        threading.Thread(target=http.serve_forever,daemon=True).start()
        url=f'http://127.0.0.1:{http.server_port}/radar/alarms-api/devices'
        try:
            with self.assertRaises(HTTPError):urlopen(url)
            with urlopen(Request(url,headers={'Authorization':'Bearer a'})) as response:
                self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertEqual(json.load(response)['devices'][0]['key'],'synthetic_device_1')
            with urlopen(Request(url+'?view=test',headers={'Authorization':'Bearer a'})) as response:
                self.assertNotIn('key',json.load(response)['devices'][0])
            with urlopen(Request(url,headers={'Authorization':'Bearer b'})) as response:self.assertEqual(json.load(response)['devices'],[])
        finally:http.shutdown();http.server_close();market.pool.shutdown()


if __name__=='__main__':unittest.main()
