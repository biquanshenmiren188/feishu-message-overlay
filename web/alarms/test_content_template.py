import json
import unittest
from unittest.mock import patch
from content import DEFAULT_TEMPLATE, render_content, validate_template
import test_content as legacy
from test_alarms import rule
from test_sources import quote, book
from server import send_event


class TemplateRenderTests(unittest.TestCase):
    def test_defaults_match_legacy_exactly_and_expand_once(self):
        values={'行情来源':'OKX · 现货（备用）','触发价格':'0.0039','触发原因':'价格穿越','时间':'11-14 12:00:00','备注':'{{触发价格}}是备注原文'}
        base=dict(note='')
        self.assertEqual(render_content(base,values),render_content(dict(base,alarmContentMode='template',alarmContent=DEFAULT_TEMPLATE),values))
        result=render_content(dict(base,note=values['备注'],alarmContentMode='template',alarmContent=DEFAULT_TEMPLATE+'\n{{备注}}'),values)
        self.assertIn('{{触发价格}}是备注原文',result)
        self.assertEqual(result.count('触发价格：0.0039'),1)

    def test_deleted_fields_still_keep_actual_facts_and_unknown_fields_rejected(self):
        values={'行情来源':'Bybit 现货（备用）','触发价格':'99','触发原因':'价格穿越','时间':'12:00','备注':''}
        result=render_content(dict(alarmContentMode='template',alarmContent='检查仓位',note=''),values)
        self.assertTrue(result.startswith('检查仓位\n\n'))
        self.assertIn('Bybit 现货（备用）',result)
        self.assertIn('触发价格：99 USDT',result)
        with self.assertRaises(ValueError):validate_template('{{触发价错字}}')


class TemplateStoreTests(unittest.TestCase):
    setUp = legacy.ContentTests.setUp
    tearDown = legacy.ContentTests.tearDown
    change = legacy.ContentTests.change
    saved = legacy.ContentTests.saved
    def test_template_save_reopen_general_edit_clear_and_no_other_mutations(self):
        self.change(action='bind',key='DemoKey_template',label='测试')
        before=self.saved();devices=self.s.device_list('a',True)
        text='检查仓位\n'+DEFAULT_TEMPLATE
        self.change(action='content',id=self.id,alarmContent=text,alarmContentMode='template')
        saved=self.saved()
        self.assertEqual(saved.pop('alarmContentMode'),'template')
        self.assertEqual(saved.pop('alarmContent'),text);before.pop('alarmContent')
        self.assertEqual(saved,before);self.assertEqual(devices,self.s.device_list('a',True))
        r=rule(repeat=True);r.pop('alarmContent')
        self.change(action='save',id=self.id,rule=r)
        self.assertEqual(self.saved()['alarmContentMode'],'template')
        self.assertEqual(self.saved()['alarmContent'],text)
        for kw in (dict(alarmContent='{{错字}}',alarmContentMode='template'),dict(alarmContent='x',alarmContentMode='bad')):
            with self.assertRaises(ValueError):self.change(action='content',id=self.id,**kw)
        self.change(action='content',id=self.id,alarmContent='',alarmContentMode='template')
        self.assertEqual(self.saved()['alarmContent'],'')

    def test_selected_backup_three_devices_new_content_next_round_every_30_seconds(self):
        for n in range(3):self.change(action='bind',key='DemoKey_template_'+str(n),label=str(n))
        r=rule(repeat=True, fallbackExchanges=['okx','bybit'])
        self.change(action='save',id=self.id,rule=r)
        self.change(action='content',id=self.id,alarmContent='第一版\n'+DEFAULT_TEMPLATE,alarmContentMode='template')
        sent=[]
        class MarketView:
            def snapshot(inner):return self.quotes,{}
        class Response:
            def __enter__(inner):return inner
            def __exit__(inner,*_):pass
            def read(inner,*_):return b'{"code":200}'
        def transport(req,**kw):sent.append((clock,json.loads(req.data)));return Response()
        for delta in (0,2,4,20,49,50,79,80):
            clock=self.now+delta
            self.quotes=book(*([quote(venue='binance',market='future',at=clock,price='99')] if delta<20 else []),
                *([quote(venue='okx',at=clock,price='99' if delta<20 else '101')] if delta<50 else []),
                quote(venue='bybit',at=clock,price='99' if delta<20 else '102'))
            with patch('store.time.time',return_value=clock),patch('server.build_opener') as opener:
                opener.return_value.open.side_effect=transport
                self.s.tick(self.quotes,clock)
                if delta==20:
                    event=self.s.claim();self.assertIsNotNone(event);send_event(self.s,event,MarketView())
                    self.change(action='content',id=self.id,alarmContent='第二版\n'+DEFAULT_TEMPLATE,alarmContentMode='template')
                while (event:=self.s.claim()) is not None:send_event(self.s,event,MarketView())
        self.assertEqual(len(sent),9)
        for n in range(3):
            rows=[(at,b) for at,b in sent if b['device_key']=='DemoKey_template_'+str(n)]
            self.assertEqual([at-self.now for at,b in rows],[20,50,80])
            self.assertTrue(rows[0][1]['body'].startswith('第一版\n备用行情：OKX'))
            self.assertTrue(all(b['body'].startswith('第二版\n备用行情：BYBIT') for _,b in rows[1:]))
            for _,b in rows:
                self.assertNotIn('{{',b['body']);self.assertEqual(b['body'].count('触发价格：'),1)
                self.assertEqual((b['level'],b['call'],b['volume']),('critical','1',5))
        for delta in (20,50,80):self.assertEqual(len({b['body'] for at,b in sent if at-self.now==delta}),1)
