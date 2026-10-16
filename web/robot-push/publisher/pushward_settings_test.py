import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from pushward_settings import DEFAULTS, PREFIX, Conflict, SettingsServer, Store, validate
import pushward_radar_test as bridge_tests
from pushward_radar_test import NOW, feed, message


class PreferenceBridgeTests(unittest.TestCase):
    setUp = bridge_tests.BridgeTests.setUp
    tearDown = bridge_tests.BridgeTests.tearDown
    notifications = bridge_tests.BridgeTests.notifications
    def config(self, revision=1, **changes):
        self.bridge.configure(dict(copy.deepcopy(DEFAULTS), **changes), revision)

    def test_filter_percentage_is_rank_value_and_signed(self):
        self.config(min_percent=0.39, exchanges=['OKX'], coins=['BTC'])
        self.bridge.tick(feed([message(title='BTC | FF | R0 +0.39%'), message(2,title='BTC | FF | R1 -0.9%')]), NOW)
        self.assertEqual([r['value'] for r in self.bridge.s['rows']], ['+0.39%'])
        self.assertEqual(self.notifications()[0][2]['title'], '雷达 · 1条新消息')

    def test_filter_modes_ranks_exchanges(self):
        self.config(ranks=['R1'], modes=['SF'], exchanges=['ASTER'])
        self.bridge.tick(feed([message(), message(2,title='ARC | SF | R1 +0.4%',body='买 GATE 现货 → 卖 ASTER 永续')]), NOW)
        self.assertEqual([r['coin'] for r in self.bridge.s['rows']], ['ARC'])

    def test_change_rows_and_filters_restores_history_without_realert(self):
        msgs=[message(i, title=f'COIN{i} | FF | R0 +0.39%') for i in range(1,9)]
        self.bridge.tick(feed(msgs),NOW)
        self.config(rows=1, coins=['COIN2'])
        self.bridge.tick(feed(msgs,NOW+31),NOW+31)
        self.assertEqual([r['coin'] for r in self.bridge.s['rows']],['COIN2'])
        self.config(revision=2,rows=6)
        self.bridge.tick(feed(msgs,NOW+62),NOW+62)
        self.assertEqual(len(self.bridge.s['rows']),6)
        self.assertEqual(len(self.notifications()),1)

    def test_off_then_on_does_not_replay_muted_messages(self):
        self.config(notify_enabled=False)
        self.bridge.tick(feed([message()]),NOW)
        self.assertEqual(len(self.bridge.s['rows']),1)
        self.assertEqual(self.notifications(),[])
        self.config(revision=2)
        self.bridge.tick(feed([message()],NOW+60),NOW+60)
        self.assertEqual(self.notifications(),[])
        self.bridge.tick(feed([message(2,at=NOW+61,title='ETH | FF | R0 +0.5%')],NOW+61),NOW+61)
        self.assertEqual(len(self.notifications()),1)

    def test_ten_minute_interval_retains_batch_across_restart(self):
        self.config(notify_interval_seconds=600)
        self.bridge.tick(feed([message()]),NOW)
        msg=message(2,at=NOW+10,title='ETH | FF | R1 +0.6%')
        self.bridge.tick(feed([msg],NOW+10),NOW+10)
        from pushward_radar import Bridge
        self.bridge=Bridge(self.client,self.temp.name,'unit-test',NOW+300)
        self.config(notify_interval_seconds=600)
        self.bridge.tick(feed([msg],NOW+599),NOW+599)
        self.assertEqual(len(self.notifications()),1)
        self.bridge.tick(feed([msg],NOW+600),NOW+600)
        self.assertEqual(len(self.notifications()),2)
        self.assertIn('ETH',self.notifications()[-1][2]['body'])

    def test_changed_filter_drops_pending_alert(self):
        self.bridge.tick(feed([message()]),NOW)
        self.bridge.tick(feed([message(2,at=NOW+1,title='ETH | FF | R1 +0.6%')],NOW+1),NOW+1)
        self.config(coins=['BTC'])
        self.bridge.tick(feed([],NOW+31),NOW+31)
        self.assertEqual(len(self.notifications()),1)


class SettingsTests(unittest.TestCase):
    def test_strict_validation(self):
        for change in [dict(rows=7),dict(rows=True),dict(rows=0),dict(ranks=[]),dict(modes=['XX']),dict(exchanges=['UNKNOWN']),dict(coins=['BTC<script>']),dict(min_percent=float('nan')),dict(min_percent=float('inf')),dict(notify_interval_seconds=1),dict(notify_enabled='false')]:
            with self.subTest(change=change), self.assertRaises(ValueError): validate(dict(DEFAULTS,**change))
        self.assertEqual(validate(dict(DEFAULTS,coins=['btc','BTC']))['coins'],['BTC'])

    def test_atomic_persistence_and_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'preferences.json';store=Store(path)
            store.save(dict(DEFAULTS,rows=4),0)
            self.assertEqual(Store(path).get()['settings']['rows'],4)
            with self.assertRaises(Conflict):store.save(DEFAULTS,0)
            self.assertEqual(Store(path).get()['settings']['rows'],4)

    def test_corrupt_settings_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'preferences.json';path.write_text('{broken')
            with self.assertRaises(ValueError):Store(path)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.secret='test-admin-secret-not-a-real-key-123'
        cls.server=SettingsServer(('127.0.0.1',0),Store(Path(cls.temp.name)/'preferences.json'),cls.secret,cls.temp.name,'https://radar.test')
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()

    def request(self,path='/settings',method='GET',data=None,cookie=None,origin='https://radar.test'):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=3)
        headers={'Origin':origin,'Content-Type':'application/json'}
        if cookie:headers['Cookie']=cookie
        connection.request(method,PREFIX+path,None if data is None else json.dumps(data),headers)
        response=connection.getresponse();status=response.status;set_cookie=response.getheader('Set-Cookie');body=json.loads(response.read());connection.close()
        return status,body,set_cookie

    def login(self):
        status,_,cookie=self.request('/login','POST',dict(password=self.secret))
        self.assertEqual(status,200)
        self.assertIn('HttpOnly; Secure; SameSite=Strict',cookie)
        return cookie.split(';')[0]

    def test_unauthorized_and_cross_origin_denied(self):
        self.assertEqual(self.request()[0],401)
        self.assertEqual(self.request(method='POST',data=dict(revision=0,settings=DEFAULTS))[0],401)
        self.assertEqual(self.request('/login','POST',dict(password=self.secret),origin='https://evil.test')[0],403)
        self.assertEqual(self.request('/login','POST',dict(password='wrong'))[0],401)
        cookie=self.login()
        self.assertEqual(self.request(method='POST',data={},cookie=cookie,origin='https://evil.test')[0],403)
        self.assertEqual(self.request(cookie=cookie+'bad')[0],401)

    def test_save_reload_conflict_and_no_secret_in_response(self):
        cookie=self.login();status,data,_=self.request(cookie=cookie);self.assertEqual(status,200)
        settings=dict(DEFAULTS,rows=5,notify_interval_seconds=300)
        change=dict(revision=data['revision'],settings=settings)
        self.assertEqual(self.request(method='POST',data=change,cookie=cookie)[0],200)
        self.assertEqual(self.request(method='POST',data=change,cookie=cookie)[0],409)
        status,data,_=self.request(cookie=cookie);self.assertEqual(data['settings'],settings)
        self.assertNotIn(self.secret,json.dumps(data));self.assertNotIn('key',json.dumps(data))
        self.assertEqual(self.request(method='POST',data=dict(revision=data['revision'],settings=dict(settings,rows=8)),cookie=cookie)[0],400)
        self.assertEqual(self.request(cookie=cookie)[1]['settings']['rows'],5)


if __name__=='__main__':unittest.main()
