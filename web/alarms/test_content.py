"""Content-only edits preserve routing, rounds, bindings and cadence."""
import json
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch
from store import Store, Conflict
from engine import validate_content
from test_alarms import rule, quote
from server import send_event

class ContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name);self.now=time.time()
        self.quotes={('binance','future','BTCUSDT'):quote(101,self.now)}
        self.id=self.change(action='save',rule=rule(repeat=True))['id']
    def tearDown(self):
        self.s.db.close();self.tmp.cleanup()
    def change(self,profile='a',**kw):
        return self.s.mutate(profile,dict(requestId=secrets.token_hex(16),revision=self.s.view(profile)['revision'],**kw),self.quotes)
    def saved(self):return self.s.view('a')['rules'][0]
    def test_validation_and_default(self):
        self.assertEqual(self.saved()['alarmContent'],'')
        for value in (None,False,{},'a'*1001):
            with self.assertRaises(ValueError):validate_content(value)
        self.assertEqual(validate_content('  提醒\n第二行  '),'提醒\n第二行')
    def test_content_only_preserves_every_other_field_state_and_devices(self):
        self.change(action='bind',key='DemoKey_content_123',label='演示')
        self.s.tick(self.quotes,self.now)
        before=self.saved();devices=self.s.device_list('a',True)
        self.quotes={}
        self.change(action='content',id=self.id,alarmContent='检查仓位\n不要追单')
        after=self.saved();self.assertEqual(after.pop('alarmContent'),'检查仓位\n不要追单');before.pop('alarmContent')
        self.assertEqual(after,before);self.assertEqual(devices,self.s.device_list('a',True))
        with self.assertRaises(ValueError):self.change('other',action='content',id=self.id,alarmContent='other')
    def test_replay_conflict_clear_and_legacy_editor_preserve(self):
        data=dict(action='content',id=self.id,alarmContent='自定义提醒',requestId=secrets.token_hex(16),revision=self.s.view('a')['revision'])
        a=self.s.mutate('a',data,{});self.assertEqual(a,self.s.mutate('a',data,{}))
        with self.assertRaises(Conflict):self.s.mutate('a',dict(data,requestId=secrets.token_hex(16)),{})
        r=rule(repeat=True);r.pop('alarmContent',None)
        self.change(action='save',id=self.id,rule=r);self.assertEqual(self.saved()['alarmContent'],'自定义提醒')
        self.change(action='content',id=self.id,alarmContent='  ');self.assertEqual(self.saved()['alarmContent'],'')
    def test_three_devices_edit_during_round_and_30_second_sender(self):
        for n in range(3):self.change(action='bind',key='DemoKey_content_'+str(n),label=str(n))
        self.change(action='content',id=self.id,alarmContent='第一版')
        sent=[]
        class MarketView:
            def snapshot(inner):return self.quotes,{}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,*_):return b'{"code":200}'
        def transport(req,**kw):
            body=json.loads(req.data);sent.append((clock,body));return Response()
        for delta in (0,29,30,59,60):
            clock=self.now+delta;self.quotes={('binance','future','BTCUSDT'):quote(101,clock)}
            with patch('store.time.time',return_value=clock),patch('server.build_opener') as opener:
                opener.return_value.open.side_effect=transport
                self.s.tick(self.quotes,clock)
                if delta==0:
                    event=self.s.claim();send_event(self.s,event,MarketView())
                    self.change(action='content',id=self.id,alarmContent='第二版 <原样文本>')
                while (event:=self.s.claim()) is not None:send_event(self.s,event,MarketView())
        self.assertEqual(len(sent),9)
        for n in range(3):
            rows=[(at,b) for at,b in sent if b['device_key']=='DemoKey_content_'+str(n)]
            self.assertEqual([at-self.now for at,b in rows],[0,30,60])
            self.assertTrue(rows[0][1]['body'].startswith('第一版\n\n'))
            self.assertTrue(all(b['body'].startswith('第二版 <原样文本>\n\n') for _,b in rows[1:]))
            self.assertTrue(all('触发价格：101 USDT' in b['body'] and b['call']=='1' and b['level']=='critical' for _,b in rows))
        for delta in (0,30,60):self.assertEqual(len({b['body'] for at,b in sent if at-self.now==delta}),1)
