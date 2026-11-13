import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from engine import validate, evaluate, number
from store import Store, Conflict
from server import make_handler, send_event
from market import Market


def rule(**kwargs):
    return validate(dict(exchange='binance', market='future', symbol='BTCUSDT', priceType='last', condition='above', target='100', **kwargs))


def quote(price, at):
    return dict(last=str(price), lastAt=at, mark='90', markAt=at, observedAt=at)


class EngineTests(unittest.TestCase):
    def run_prices(self, r, samples):
        state, events = {}, []
        for at, price in samples:
            state, event = evaluate(r, state, quote(price, at), at)
            if event:
                events.append(event)
        return state, events

    def test_once_exact_boundary(self):
        state, events = self.run_prices(rule(), [(100,99),(101,100),(102,101),(103,99),(104,100)])
        self.assertEqual(len(events),1)
        self.assertEqual(state['status'],'triggered')

    def test_initial_satisfied_waits(self):
        _, events = self.run_prices(rule(), [(100,101),(101,102),(102,99),(103,100)])
        self.assertEqual([e['at'] for e in events],[103])

    def test_initial_immediate(self):
        _, events = self.run_prices(rule(immediate=True), [(100,101)])
        self.assertEqual(events[0]['reason'],'initial')

    def test_hold_resets_on_dip(self):
        _, events = self.run_prices(rule(hold=3), [(100,99),(101,100),(102,101),(103,99),(104,101),(106,102),(107,103)])
        self.assertEqual([e['at'] for e in events],[107])

    def test_repeat_uses_thirty_seconds_without_recovery(self):
        _, events = self.run_prices(rule(repeat=True,cooldown=30), [(100,99),(101,100),(110,101),(120,99.9),(130,100),(132,99.7),(133,100)])
        self.assertEqual([e['at'] for e in events],[101,133])

    def test_repeat_continues_while_condition_holds(self):
        samples=[(100,99),(101,100)]+[(i,101) for i in range(102,150)]
        _, events=self.run_prices(rule(repeat=True,cooldown=30),samples)
        self.assertEqual([e['at'] for e in events],[101,131])

    def test_stale_cancels_confirmation(self):
        r=rule(hold=3);s,_=evaluate(r,{},quote(99,100),100);s,_=evaluate(r,s,quote(101,101),101)
        s,e=evaluate(r,s,quote(101,101),120)
        self.assertEqual(s['status'],'stale');self.assertIsNone(s['pending']);self.assertIsNone(e)
        s,e=evaluate(r,s,quote(102,121),121);self.assertIsNone(e);self.assertFalse(s['armed'])

    def test_recovery_is_labelled(self):
        r=rule(recovery=True);s,_=evaluate(r,{},quote(99,100),100);s,_=evaluate(r,s,None,120)
        s,e=evaluate(r,s,quote(101,121),121);self.assertEqual(e['reason'],'recovery')

    def test_duplicate_samples_do_not_confirm(self):
        r=rule(hold=3);s,_=evaluate(r,{},quote(99,100),100);s,_=evaluate(r,s,quote(101,101),101)
        s,e=evaluate(r,s,quote(101,101),105);self.assertIsNone(e)

    def test_decimal_precision(self):
        r=rule();r['target']='0.000000010000000001'
        _,events=self.run_prices(r,[(100,'0.000000010000000000'),(101,'0.000000010000000001')])
        self.assertEqual(len(events),1)

    def test_down_cross(self):
        r=rule();r['condition']='below'
        _,events=self.run_prices(r,[(100,101),(101,100)])
        self.assertEqual(len(events),1)

    def test_enter_and_exit(self):
        for condition,points in [('enter',[(100,99),(101,100)]),('exit',[(100,105),(101,111)])]:
            r=rule();r.update(condition=condition,upper='110')
            _,events=self.run_prices(r,points);self.assertEqual(len(events),1)

    def test_pause_and_expiry(self):
        for r,status in [(rule(enabled=False),'paused'),(rule(expiresAt=50),'expired')]:
            s,e=evaluate(r,{},quote(101,100),100);self.assertEqual(s['status'],status);self.assertIsNone(e)

    def test_out_of_order_and_future(self):
        r=rule();s,_=evaluate(r,{},quote(99,100),100)
        for q in [quote(101,99),quote(101,200)]:
            _,e=evaluate(r,s,q,101);self.assertIsNone(e)

    def test_missing_mark_is_not_last(self):
        r=rule();r['priceType']='mark';q=quote(110,100);q['mark']=None
        s,e=evaluate(r,{},q,100);self.assertEqual(s['status'],'unavailable');self.assertIsNone(e)

    def test_invalid_numbers(self):
        for value in [None,True,0,-1,'NaN','Infinity','1e9999','x']:
            with self.subTest(value=value),self.assertRaises(ValueError):number(value)

    def test_all_rules_use_critical(self):
        for level in ['active', 'timeSensitive', 'critical']:
            self.assertEqual(rule(level=level)['level'], 'critical')

    def test_simple_repeat_does_not_spam_on_price_oscillation(self):
        r=rule(repeat=True,immediate=True,hold=0,cooldown=300,hysteresis='0')
        state,event=evaluate(r,{},quote(100,1000),1000)
        self.assertIsNotNone(event)
        state,event=evaluate(r,state,quote(101,1001),1001)
        self.assertIsNone(event)
        state,event=evaluate(r,state,quote(99,1002),1002)
        state,event=evaluate(r,state,quote(100,1003),1003)
        self.assertIsNone(event)

    def test_validation(self):
        for change in [dict(hold=-1),dict(cooldown=0),dict(hysteresis='NaN'),dict(expiresAt=float('inf')),dict(enabled='yes')]:
            with self.subTest(change=change),self.assertRaises(ValueError):rule(**change)
        r=rule();r.update(market='spot',priceType='mark')
        with self.assertRaises(ValueError):validate(r)

    def test_continuous_all_conditions_boundary_recovery(self):
        for condition, hit, restored in [('above','100','99.99'),('below','100','100.01'),('enter','100','99.99'),('exit','111','110')]:
            with self.subTest(condition=condition):
                r=rule(repeat=True);r.update(condition=condition,upper='110' if condition in ('enter','exit') else None)
                # Legacy values are ignored without rewriting saved settings.
                r.update(hold=60,cooldown=86400,immediate=False,recovery=False,hysteresis='10')
                state,events=self.run_prices(r,[(t,hit) for t in range(100,162,2)])
                self.assertEqual([e['at'] for e in events],[100,130,160]);self.assertEqual(state['status'],'alarming')
                state,event=evaluate(r,state,quote(restored,162),162)
                self.assertIsNone(event);self.assertEqual(state['status'],'watching')

    def test_continuous_stale_restart_resume_and_old_waiting(self):
        r=rule(repeat=True)
        state={'fired':True,'lastFire':100,'sampleAt':100,'armed':False,'gap':True,'status':'waiting'}
        state,event=evaluate(r,state,quote(101,110),110);self.assertIsNone(event)
        state,event=evaluate(r,state,quote(101,110),130);self.assertIsNone(event);self.assertEqual(state['status'],'stale')
        state,event=evaluate(r,state,quote(101,131),131);self.assertIsNotNone(event);self.assertEqual(state['status'],'alarming')
        state,event=evaluate(r,state,quote(101,132),132);self.assertIsNone(event)

    def test_once_immediate_resumes_after_gap_but_never_repeats(self):
        r=rule(immediate=True)
        s,_=evaluate(r,{},quote(99,100),100)
        s,e=evaluate(r,s,None,120);self.assertIsNone(e)
        s,e=evaluate(r,s,quote(101,121),121);self.assertIsNotNone(e)
        s,e=evaluate(r,s,quote(102,160),160);self.assertIsNone(e);self.assertEqual(s['status'],'triggered')

    def test_repeat_clock_uses_fresh_quote_not_only_new_stamp(self):
        r=rule(repeat=True);state,event=evaluate(r,{},quote(101,100),100)
        state,event=evaluate(r,state,quote(101,129),129);self.assertIsNone(event)
        state,event=evaluate(r,state,quote(101,129),130);self.assertIsNotNone(event)
        state,event=evaluate(r,state,quote(101,128),131);self.assertIsNone(event)

    def test_delayed_dispatch_spaces_next_event(self):
        r=rule(repeat=True);s={'fired':True,'lastFire':100,'lastDispatch':110,'sampleAt':120}
        s,e=evaluate(r,s,quote(101,130),130);self.assertIsNone(e)
        s,e=evaluate(r,s,quote(101,140),140);self.assertIsNotNone(e)

    def test_repeat_pause_expiry_and_missing_mark(self):
        for enabled,expiry,kind,expected in [(False,None,'last','paused'),(True,99,'last','expired'),(True,None,'mark','unavailable')]:
            r=rule(repeat=True,enabled=enabled,expiresAt=expiry);r['priceType']=kind;q=quote(101,100);q['mark']=None
            s,e=evaluate(r,{},q,100);self.assertIsNone(e);self.assertEqual(s['status'],expected)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.now=time.time()
        self.catalog={('binance','future','BTCUSDT'):quote(99,self.now)}

    def tearDown(self):
        self.store.db.close();self.temp.cleanup()

    def change(self,profile='a',**data):
        return self.store.mutate(profile,dict(requestId=__import__('secrets').token_hex(16),revision=self.store.view(profile)['revision'],**data),self.catalog)

    def create(self,profile='a',**kwargs):
        return self.change(profile,action='save',rule=rule(**kwargs))['id']

    def test_cross_profile_isolation(self):
        identity=self.create()
        self.assertEqual(self.store.view('b')['rules'],[])
        with self.assertRaises(ValueError):self.change('b',action='delete',id=identity)
        self.assertEqual(len(self.store.view('a')['rules']),1)

    def test_revision_conflict(self):
        self.create()
        with self.assertRaises(Conflict):self.store.mutate('a',dict(requestId='a'*32,revision=0,action='enabled',enabled=False),self.catalog)

    def test_idempotence_and_body_immutability(self):
        data=dict(requestId='a'*32,revision=0,action='save',rule=rule())
        first=self.store.mutate('a',data,self.catalog);second=self.store.mutate('a',data,self.catalog)
        self.assertEqual(first,second);self.assertEqual(len(self.store.view('a')['rules']),1)
        with self.assertRaises(Conflict):self.store.mutate('a',{**data,'rule':rule(hold=3)},self.catalog)

    def test_concurrent_idempotence(self):
        data=dict(requestId='a'*32,revision=0,action='save',rule=rule())
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.store.mutate('a',data,self.catalog),range(4)))
        self.assertTrue(all(r==results[0] for r in results));self.assertEqual(len(self.store.view('a')['rules']),1)

    def test_device_key_encrypted_and_unique(self):
        secret='synthetic_test_device_12345'
        self.change(action='bind',key='https://api.day.app/'+secret,label='合成设备')
        self.assertNotIn(secret,json.dumps(self.store.view('a')))
        for row in self.store.db.execute('SELECT secret FROM devices'):self.assertNotIn(secret,row['secret'])
        with self.assertRaises(Conflict):self.change('b',action='bind',key=secret,label='其他设备')

    def test_ssrf_urls_rejected(self):
        for key in ['http://127.0.0.1/hello','https://localhost/secret','https://api.day.app@evil.test/secret','https://api.day.app/key?redirect=x']:
            with self.subTest(key=key),self.assertRaises(ValueError):self.change(action='bind',key=key,label='设备')

    def test_event_and_state_persist_together(self):
        self.create();self.store.tick(self.catalog,self.now)
        self.catalog[('binance','future','BTCUSDT')]=quote(100,self.now+1);self.store.tick(self.catalog,self.now+1)
        self.assertEqual(len(self.store.view('a')['events']),1)
        self.assertEqual(self.store.view('a')['events'][0]['status'],'no_device')
        self.store.db.close();self.store=Store(self.temp.name)
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+2)},self.now+2)
        self.assertEqual(len(self.store.view('a')['events']),1)

    def test_rule_change_cancels_pending(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');identity=self.create(immediate=True)
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now)},self.now)
        self.change(action='toggle',id=identity,enabled=False)
        self.assertIsNone(self.store.claim());self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')

    def test_unbind_cancels_pending(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test');self.change(action='unbind')
        self.assertIsNone(self.store.claim())

    def test_restart_inflight_unknown(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test');event=self.store.claim();self.store.begin_send(event)
        self.store.db.close();self.store=Store(self.temp.name)
        self.assertEqual(self.store.view('a')['events'][0]['status'],'unknown');self.assertIsNone(self.store.claim())

    def test_no_snapshot_no_rule(self):
        self.catalog={}
        with self.assertRaises(ValueError):self.create()

    def test_monitoring_uses_only_rule_enabled(self):
        active=self.create(immediate=True);paused=self.create(enabled=False,immediate=True)
        self.assertTrue(self.store.view('a')['enabled'])
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now)},self.now)
        events=self.store.view('a')['events']
        self.assertEqual([e['ruleId'] for e in events],[active])
        self.assertEqual(next(r for r in self.store.view('a')['rules'] if r['id']==paused)['state']['status'],'paused')
        self.change(action='save',id=paused,rule=rule(enabled=True,immediate=True))
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+1)},self.now+1)
        self.assertEqual({e['ruleId'] for e in self.store.view('a')['events']},{active,paused})

    def test_retired_master_action_cannot_pause_rules(self):
        identity=self.create(immediate=True);before=self.store.view('a')['revision']
        for enabled in (False,True):
            with self.assertRaisesRegex(ValueError,'单条报警'):
                self.change(action='enabled',enabled=enabled)
        self.assertEqual(self.store.view('a')['revision'],before)
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now)},self.now)
        self.assertEqual(self.store.view('a')['events'][0]['ruleId'],identity)

    def test_legacy_total_pause_becomes_individual_pause_once(self):
        self.create(immediate=True,note='preserve');self.create(enabled=False)
        other=self.create('b',immediate=True)
        original={r['id']:r for r in self.store.view('a')['rules']};revision=self.store.view('a')['revision']
        with self.store.db:self.store.db.execute("UPDATE profiles SET enabled=0 WHERE id='a'")
        self.store.db.close();self.store=Store(self.temp.name)
        view=self.store.view('a');self.assertTrue(view['enabled']);self.assertEqual(view['revision'],revision+1)
        self.assertEqual(len(view['rules']),2)
        for r in view['rules']:
            self.assertFalse(r['enabled']);self.assertEqual(r['state']['status'],'paused')
            self.assertEqual(r['note'],original[r['id']]['note']);self.assertEqual(r['target'],original[r['id']]['target'])
        self.assertTrue(self.store.view('b')['rules'][0]['enabled'])
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now)},self.now)
        self.assertFalse(self.store.view('a')['events']);self.assertEqual(self.store.view('b')['events'][0]['ruleId'],other)
        self.store.db.close();self.store=Store(self.temp.name)
        self.assertEqual(self.store.view('a')['revision'],revision+1)

    def test_test_notification_rate_limit(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test')
        with self.assertRaises(ValueError):self.change(action='test')

    def test_history_pages_filters_and_detail_scope(self):
        now=time.time()
        with self.store.db:
            for i in range(45):
                self.store.event('a','r',dict(title='BTCUSDT 上穿 100',body='private body'),None,now-i)
            self.store.event('b','r',dict(title='BTCUSDT 上穿 100',body='other profile'),None,now)
            self.store.event('a','r',dict(title='WBTCUSDT 上穿 100',body='wrapped'),None,now-50)
        query=dict(q=['btc'],before=[str(now+1)])
        first=self.store.history('a',query)
        self.assertEqual(first['total'],45);self.assertEqual(len(first['items']),20)
        self.assertNotIn('body',first['items'][0])
        second=self.store.history('a',dict(query,page=['2']))
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
        identity=first['items'][0]['id']
        self.assertEqual(self.store.event_detail('a',identity)['body'],'private body')
        with self.assertRaises(ValueError):self.store.event_detail('b',identity)
        self.assertEqual(self.store.history('a',dict(q=['BT']))['total'],0)
        self.assertEqual(self.store.history('a',dict(status=['accepted']))['total'],0)
        self.assertEqual(self.store.view('a',compact=True)['events'],[])
        self.assertEqual(len(self.store.view('a')['events']),46)

    def test_http_scope(self):
        market=Market();market.quotes=self.catalog
        http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,market,lambda token:token if token in ('a','b') else None))
        threading.Thread(target=http.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{http.server_port}/radar/alarms-api/'
        try:
            self.create()
            with self.assertRaises(HTTPError) as result:urlopen(base+'state')
            self.assertEqual(result.exception.code,401)
            with urlopen(Request(base+'state',headers={'Authorization':'Bearer b'})) as res:self.assertEqual(json.load(res)['rules'],[])
            with urlopen(Request(base+'history',headers={'Authorization':'Bearer b'})) as res:self.assertEqual(json.load(res)['items'],[])
            with urlopen(Request(base+'state?events=latest-test',headers={'Authorization':'Bearer a'})) as res:
                value=json.load(res)
                self.assertEqual(value['events'],[])
                self.assertLess(abs(value['serverTime']-time.time()),2)
                self.assertEqual(value['sampleInterval'],2)
            with self.assertRaises(HTTPError) as result:urlopen(Request(base+'state',headers={'Authorization':'Bearer a','Origin':'https://evil.test'}))
            self.assertEqual(result.exception.code,403)
        finally:http.shutdown();http.server_close();market.pool.shutdown()

    def test_bark_timeout_not_retried(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test');event=self.store.claim()
        with patch('server.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError()
            send_event(self.store,event)
        self.assertEqual(self.store.view('a')['events'][0]['status'],'unknown')

    def test_bark_acceptance_and_request_scope(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test');event=self.store.claim()
        with patch('server.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"code":200}'
            send_event(self.store,event)
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.day.app/push')
            self.assertNotIn('synthetic_device',request.full_url)
            self.assertEqual(json.loads(request.data)['device_key'],'synthetic_device_12345')
            self.assertEqual(json.loads(request.data)['level'],'critical')
            self.assertEqual(json.loads(request.data)['volume'],5)
            self.assertEqual(json.loads(request.data)['call'],'1')
        self.assertEqual(self.store.view('a')['events'][0]['status'],'accepted')

    def test_legacy_queued_payload_forced_critical(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test');event=dict(self.store.claim())
        payload=json.loads(event['payload']);payload['level']='active';payload['call']='0';event['payload']=json.dumps(payload)
        with patch('server.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"code":200}'
            send_event(self.store,event)
            self.assertEqual(json.loads(opener.return_value.open.call_args.args[0].data)['level'],'critical')
            self.assertEqual(json.loads(opener.return_value.open.call_args.args[0].data)['call'],'1')

    def test_retry_limit(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test')
        for attempt in range(3):
            with self.store.db:self.store.db.execute('UPDATE events SET next_at=0')
            event=self.store.claim();self.assertIsNotNone(event);self.assertTrue(self.store.begin_send(event));self.store.finish(event,'retry','HTTP 429')
        self.assertEqual(self.store.view('a')['events'][0]['status'],'failed');self.assertIsNone(self.store.claim())

    def test_expired_outbox_never_sends(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备');self.change(action='test')
        with self.store.db:self.store.db.execute('UPDATE events SET expires=0')
        self.assertIsNone(self.store.claim());self.store.tick({},self.now)
        self.assertEqual(self.store.view('a')['events'][0]['status'],'expired')

    def repeat_fixture(self):
        self.change(action='bind',key='synthetic_device_12345',label='设备')
        identity=self.create(repeat=True)
        quotes={('binance','future','BTCUSDT'):quote(101,self.now)}
        self.store.tick(quotes,self.now)
        return identity,quotes

    def test_continuous_cancels_pending_and_claimed_on_recovery(self):
        for claimed in (False,True):
            with self.subTest(claimed=claimed):
                identity,quotes=self.repeat_fixture();event=self.store.claim() if claimed else None
                self.store.tick({('binance','future','BTCUSDT'):quote(99,self.now+1)},self.now+1)
                self.assertIsNone(self.store.claim())
                if event:self.assertFalse(self.store.begin_send(event,quotes,self.now+1))
                self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')
                self.change(action='delete',id=identity)

    def test_continuous_rechecks_latest_quote_before_http(self):
        identity,quotes=self.repeat_fixture();event=self.store.claim()
        self.assertFalse(self.store.begin_send(event,{('binance','future','BTCUSDT'):quote(99,self.now+1)},self.now+1))
        self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')

    def test_claimed_cannot_send_after_pause_delete_edit_or_unbind(self):
        for action in ('pause','delete','edit','unbind'):
            with self.subTest(action=action):
                identity,quotes=self.repeat_fixture();event=self.store.claim()
                if action=='pause':self.change(action='save',id=identity,rule=rule(repeat=True,enabled=False))
                elif action=='edit':self.change(action='save',id=identity,rule={**rule(repeat=True),'target':'200'})
                elif action=='delete':self.change(action='delete',id=identity)
                else:self.change(action='unbind')
                self.assertFalse(self.store.begin_send(event,quotes,self.now+1))
                if action!='delete':self.change(action='delete',id=identity)

    def test_repeat_restart_preserves_interval_and_cancels_claim(self):
        identity,quotes=self.repeat_fixture();self.store.claim()
        self.store.db.close();self.store=Store(self.temp.name)
        self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')
        for delta in (1,29):
            self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+delta)},self.now+delta)
            self.assertEqual(len(self.store.view('a')['events']),1)
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+30)},self.now+30)
        self.assertEqual(len(self.store.view('a')['events']),2)

    def test_repeat_outbox_superseded_no_backlog(self):
        identity,quotes=self.repeat_fixture()
        for delta in range(2,62,2):self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+delta)},self.now+delta)
        events=self.store.view('a')['events'];self.assertEqual(len(events),3)
        self.assertEqual(sum(e['status']=='queued' for e in events),1)
        self.assertEqual(sum(e['status']=='cancelled' for e in events),2)

    def test_repeat_edit_preserves_dispatch_interval(self):
        identity,quotes=self.repeat_fixture();event=self.store.claim()
        self.assertTrue(self.store.begin_send(event,quotes,self.now))
        self.change(action='save',id=identity,rule=rule(repeat=True))
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+1)},self.now+1)
        self.assertEqual(len(self.store.view('a')['events']),1)
        self.assertEqual(self.store.view('a')['rules'][0]['state']['lastDispatch'],self.now)

    def test_continuous_http_failure_waits_for_next_slot(self):
        identity,quotes=self.repeat_fixture();event=self.store.claim()
        with patch('server.build_opener') as opener:
            opener.return_value.open.side_effect=HTTPError('https://api.day.app/push',429,'rate limit',{},None)
            send_event(self.store,event)
        self.assertEqual(self.store.view('a')['events'][0]['status'],'failed');self.assertIsNone(self.store.claim())

    def test_continuous_critical_loop_payload_and_stale_cancellation(self):
        identity,quotes=self.repeat_fixture();event=self.store.claim()
        with patch('server.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"code":200}'
            send_event(self.store,event)
            payload=json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual((payload['level'],payload['volume'],payload['call']),('critical',5,'1'))
        self.store.tick({('binance','future','BTCUSDT'):quote(101,self.now+32)},self.now+32)
        self.store.tick({},self.now+33)
        self.assertIsNone(self.store.claim());self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')


if __name__=='__main__':unittest.main()
