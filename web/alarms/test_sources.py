import json
import tempfile
import time
import unittest
from unittest.mock import patch
from engine import validate, evaluate
from sources import select, identity, eligible, active_groups, fresh, backup_venues
from instruments import load
from store import Store
from market import Market, VENUES
from server import send_event


def rule(base='BTC', exchange='okx', **kw):
    symbol = base + '-USDT-SWAP' if exchange == 'okx' else base + 'USDT'
    return validate(dict(exchange=exchange, market='future', symbol=symbol, priceType='last', condition='below', target='100', repeat=True, **kw))


def quote(base='BTC', venue='binance', market='spot', at=100, price='101', **kw):
    symbol = base + ('-USDT-SWAP' if market == 'future' else '-USDT') if venue == 'okx' else base + 'USDT'
    return dict(exchange=venue, market=market, symbol=symbol, base=base, quote='USDT', unit=base, instrumentVerified=True, observedAt=at, lastAt=at, last=price, **kw)


def book(*rows):
    return {(r['exchange'], r['market'], r['symbol']): r for r in rows}


def warm(base='BTC', venue='okx', start=100):
    r, state = rule(base, venue), {}
    for t in (start, start+2, start+4):
        p = quote(base, venue, 'future', t)
        backups = [quote(base, v, at=t) for v in ('binance', 'bybit', 'bitget') if v != venue]
        q, effective, state = select(r, state, book(p, *backups), t)
        state, _ = evaluate(effective, state, q, t)
    return r, state


class SourceTests(unittest.TestCase):
    def test_multi_selection_validation_and_legacy_compatibility(self):
        for invalid in (None, 'auto', True, ['binance','binance'], ['okx'], ['unknown'], [None], [[]]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                rule(fallbackExchanges=invalid)
        self.assertEqual(backup_venues(rule()),('binance','bybit','bitget','gate'))
        self.assertEqual(backup_venues(rule(fallbackExchange='aster')),('aster',))
        self.assertEqual(backup_venues(rule(fallbackExchanges=[])),())
        self.assertEqual(backup_venues(rule(fallbackExchange='auto',fallbackExchanges=['aster','bybit'])),('bybit','aster'))

    def test_every_subset_only_routes_to_selected_venues(self):
        from itertools import combinations
        for main in VENUES:
            others=[v for v in ('binance','okx','bybit','bitget','gate','aster') if v!=main]
            for size in range(6):
                for subset in combinations(others,size):
                    with self.subTest(main=main,selected=subset):
                        r=rule(exchange=main,fallbackExchanges=list(subset));state={}
                        for t in (100,102,104):
                            q,e,state=select(r,state,book(quote(venue=main,market='future',at=t),*[quote(venue=v,at=t) for v in others]),t)
                        self.assertEqual(active_groups(r,state),{(main,'future'),*((v,'spot') for v in subset)})
                        for failed_count in range(len(subset)+1):
                            available=[v for v in others if v not in subset[:failed_count]]
                            q,e,result=select(r,state,book(*[quote(venue=v,at=118,price='99') for v in available]),118)
                            expected=subset[failed_count:]
                            if expected:
                                self.assertEqual(result['source']['exchange'],expected[0])
                            else:
                                self.assertIsNone(q) # All unchecked feeds are healthy but forbidden.
                                self.assertEqual(result['routingReason'],'no_fresh_backup' if subset else 'backup_disabled')

    def test_fallback_choice_validation(self):
        self.assertEqual(rule()['fallbackExchange'],'auto')
        for choice in ('auto','off','binance','bybit','bitget','gate','aster'):
            self.assertEqual(rule(fallbackExchange=choice)['fallbackExchange'],choice)
        for choice in ('okx','unknown',None,[],True):
            with self.subTest(choice=choice), self.assertRaises(ValueError):rule(fallbackExchange=choice)

    def test_explicit_choice_and_off_never_use_an_unselected_venue(self):
        r,s=warm();r['fallbackExchange']='bybit'
        q,e,t=select(r,s,book(quote(at=118),quote(venue='bybit',at=118)),118)
        self.assertEqual(t['source']['exchange'],'bybit')
        q,e,t=select(r,s,book(quote(at=118)),118);self.assertIsNone(q)
        self.assertEqual(active_groups(r,s),{('okx','future'),('bybit','spot')})
        r['fallbackExchange']='off'
        q,e,t=select(r,s,book(quote(at=118),quote(venue='bybit',at=118)),118);self.assertIsNone(q)
        self.assertEqual(active_groups(r,s),{('okx','future')})

    def test_explicit_aster_uses_same_identity_and_freshness_checks(self):
        r=rule('ETH',fallbackExchange='aster');s={}
        for t in (100,102,104):
            q,e,s=select(r,s,book(quote('ETH','okx','future',t),quote('ETH','aster',at=t)),t)
        q,e,s=select(r,s,book(quote('ETH','aster',at=118)),118)
        self.assertEqual(s['source']['exchange'],'aster')
        q,e,s=select(r,s,book(quote('ETH','aster',at=118)),131);self.assertIsNone(q)

    def test_normalization_uses_metadata_not_symbol_guessing(self):
        for venue in ('binance','okx','bybit','bitget','gate','aster'):
            q = quote(venue=venue, market='future')
            self.assertEqual(identity(q)['pair'], 'BTC/USDT')
        self.assertIsNone(identity(dict(quote(), instrumentVerified=False)))
        self.assertIsNone(identity(dict(quote(), quote='USDC')))

    def test_other_coins_not_btc_only(self):
        for base in ('BTC','ETH','SOL','DOGE','XRP','PEPE','JCT'):
            with self.subTest(base=base):
                r,s=warm(base)
                q,e,s=select(r,s,book(quote(base, at=118,price='99')),118)
                self.assertEqual(s['asset']['pair'],base+'/USDT')
                self.assertEqual(s['source']['exchange'],'binance')
                self.assertEqual(e['priceType'],'last')
                s,event=evaluate(e,s,q,118)
                self.assertIsNotNone(event)

    def test_fresh_primary_wins_despite_backup_crossing(self):
        r,s=warm()
        q,e,s=select(r,s,book(quote(venue='okx',market='future',at=110),quote(at=110,price='99')),110)
        self.assertFalse(s['source']['fallback'])
        s,event=evaluate(e,s,q,110);self.assertIsNone(event)

    def test_12_second_limit_and_future_invalid_samples(self):
        r,s=warm()
        for at in (104,):
            q,e,s=select(r,s,book(quote(venue='okx',market='future',at=at),quote(at=116)),116)
            self.assertFalse(s['source']['fallback'])
        q,e,s=select(r,s,book(quote(venue='okx',market='future',at=104),quote(at=117)),117)
        self.assertTrue(s['source']['fallback'])
        for q in (quote(at=100),quote(at=999),dict(quote(at=117),last='NaN'),dict(quote(at=117),observedAt=float('nan'))):
            self.assertFalse(fresh(q,'last',117))

    def test_no_cross_quote_wrapped_multiplier_or_ambiguous_match(self):
        r,s=warm()
        for bad in [quote('WBTC',at=118),dict(quote(at=118),quote='USD'),dict(quote(at=118),unit='1000BTC'),quote('1000BTC',at=118),dict(quote(at=118),instrumentVerified=False)]:
            q,_,_=select(r,s,book(bad),118);self.assertIsNone(q)
        for base in ('1000UNKNOWN','PAY','BTC3L'):
            self.assertFalse(eligible(identity(quote(base))))

    def test_never_use_original_exchange_spot(self):
        r,s=warm()
        q,_,_=select(r,s,book(quote(venue='okx',at=118)),118)
        self.assertIsNone(q)

    def test_backup_priority_and_second_failure(self):
        r,s=warm()
        q,_,s=select(r,s,book(quote(at=118),quote(venue='bybit',at=118)),118)
        self.assertEqual(s['source']['exchange'],'binance')
        q,_,s=select(r,s,book(quote(at=118),quote(venue='bybit',at=131)),131)
        self.assertEqual(s['source']['exchange'],'bybit')
        q,_,s=select(r,s,{},144);self.assertIsNone(q);self.assertEqual(s['sourceStatus'],'unavailable')

    def test_recovery_requires_three_distinct_samples_not_ticks(self):
        r,s=warm();q,e,s=select(r,s,book(quote(at=118)),118)
        for now in (119,119.5,120):
            q,e,s=select(r,s,book(quote(at=now),quote(venue='okx',market='future',at=119)),now)
            self.assertTrue(s['source']['fallback'])
            self.assertEqual(s['primaryRecoveryCount'],1)
        for now in (121,123):
            q,e,s=select(r,s,book(quote(at=now),quote(venue='okx',market='future',at=now)),now)
        self.assertFalse(s['source']['fallback'])

    def test_restart_and_no_30_second_burst(self):
        r,s=warm();s.update(fired=True,lastFire=110,lastDispatch=112)
        q,e,s=select(r,json.loads(json.dumps(s)),book(quote(at=118,price='99')),118)
        s,event=evaluate(e,s,q,118);self.assertIsNone(event)
        q,e,s=select(r,s,book(quote(at=142,price='99')),142)
        s,event=evaluate(e,s,q,142);self.assertIsNotNone(event)

    def test_prequalification_requires_three_samples_and_price_unit_sanity(self):
        r=rule();s={}
        for now in (100,101,102,103):
            q,e,s=select(r,s,book(quote(venue='okx',market='future',at=100),quote(at=100)),now)
        q,e,s=select(r,s,book(quote(at=118)),118);self.assertIsNone(q)
        r,s=warm()
        q,e,s=select(r,s,book(quote(venue='okx',market='future',at=110),quote(at=110,price='0.1')),110)
        q,e,s=select(r,s,book(quote(at=123,price='0.1')),123);self.assertIsNone(q)

    def test_active_backup_prewarm_and_no_side_effect_at_dispatch(self):
        r,s=warm();self.assertEqual(len(active_groups(r,s)),5)
        before=json.dumps(s,sort_keys=True)
        select(r,s,book(quote(at=118)),118,advance=False)
        self.assertEqual(before,json.dumps(s,sort_keys=True))

    def test_mark_rule_falls_back_to_explicit_spot_last(self):
        r,s=warm();r['priceType']='mark'
        q,e,s=select(r,s,book(quote(at=118,price='99')),118)
        self.assertEqual(e['priceType'],'last');self.assertEqual(s['source']['priceType'],'last')
        s,event=evaluate(e,s,q,118);self.assertEqual(event['price'],'99')

    def test_one_shot_keeps_once_only_policy(self):
        r,s=warm();r.update(repeat=False,immediate=True)
        q,e,s=select(r,s,book(quote(at=118,price='99')),118)
        s,event=evaluate(e,s,q,118);self.assertIsNotNone(event)
        q,e,s=select(r,s,book(quote(at=150,price='98')),150)
        s,event=evaluate(e,s,q,150);self.assertIsNone(event);self.assertEqual(s['status'],'triggered')

    def test_identity_change_revokes_qualified_sources(self):
        r,s=warm();p=quote(venue='okx',market='future',at=110);p['unit']='1000BTC'
        q,e,s=select(r,s,book(p,quote(at=110)),110)
        self.assertEqual(s['qualifiedSources'],{})
        q,e,s=select(r,s,book(quote(at=123)),123);self.assertIsNone(q)

    def test_metadata_gate_quantity_not_price_multiplier(self):
        result=load(lambda url:[dict(name='BTC_USDT',quanto_multiplier='0.0001')],'gate','future','')
        self.assertEqual(result['BTC_USDT']['unit'],'BTC')

    def test_metadata_okx_and_bitget(self):
        result=load(lambda url:dict(code='0',data=[dict(instId='BTC-USDT-SWAP',uly='BTC-USDT',ctValCcy='BTC',ctType='linear',settleCcy='USDT',state='live',ctVal='0.01')]),'okx','future','')
        self.assertEqual(result['BTC-USDT-SWAP']['unit'],'BTC')
        result=load(lambda url:dict(code='00000',data=[dict(symbol='ETHUSDT',baseCoin='ETH',quoteCoin='USDT',symbolStatus='normal',symbolType='perpetual')]),'bitget','future','')
        self.assertEqual(result['ETHUSDT']['base'],'ETH')

    def test_bybit_pagination_and_status(self):
        calls=[]
        def get(url):
            calls.append(url);last='cursor=' in url
            return dict(retCode=0,result=dict(list=[dict(symbol='ETHUSDT' if last else 'BTCUSDT',baseCoin='ETH' if last else 'BTC',quoteCoin='USDT',status='Trading',contractType='LinearPerpetual')],nextPageCursor='' if last else 'a&b'))
        result=load(get,'bybit','future','');self.assertEqual(len(result),2);self.assertIn('cursor=a%26b',calls[1])


class RoutingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name);self.now=time.time()
        self.r,self.state=warm(start=self.now-20)
        self.change(action='bind',key='synthetic_device_for_routing',label='synthetic')
        self.id=self.change(action='save',rule=self.r)['id']
        with self.store.db:self.store.db.execute('UPDATE rules SET state=? WHERE id=?',(json.dumps(self.state),self.id))
    def tearDown(self):
        self.store.db.close();self.temp.cleanup()
    def change(self,**kw):
        return self.store.mutate('a',dict(requestId=__import__('secrets').token_hex(16),revision=self.store.view('a')['revision'],**kw),book(quote(venue='okx',market='future',at=self.now)))
    def test_multi_selection_create_edit_reload_and_old_client_guard(self):
        import secrets
        for main in VENUES:
            for base in ('BTC','ETH','SOL'):
                native=base+'-USDT-SWAP' if main=='okx' else base+'_USDT' if main=='gate' else base+'USDT'
                q=quote(base,main,'future',self.now);q['symbol']=native
                choices=[v for v in ('binance','okx','bybit','bitget','gate','aster') if v!=main]
                def save(r, rid=None):
                    return self.store.mutate('multiselect',dict(action='save',rule=r,id=rid,requestId=secrets.token_hex(16),revision=self.store.view('multiselect')['revision']),book(q))
                r=rule(base,main,fallbackExchanges=choices[1:3]);r['symbol']=native
                rid=save(r)['id']
                for selected in (choices[1:3], [], [choices[-1]], choices):
                    r=rule(base,main,fallbackExchanges=selected);r['symbol']=native
                    save(r,rid)
                    self.store.db.close();self.store=Store(self.temp.name)
                    saved=next(x for x in self.store.view('multiselect')['rules'] if x['id']==rid)
                    self.assertEqual((saved['symbol'],saved['fallbackExchanges'],saved['enabled']),(native,selected,True))
                old=dict(r);old.pop('fallbackExchanges')
                with self.assertRaisesRegex(Exception,'刷新页面'):save(old,rid)
                saved=next(x for x in self.store.view('multiselect')['rules'] if x['id']==rid)
                self.assertEqual(saved['fallbackExchanges'],choices)

    def test_unchecking_a_queued_source_cancels_delivery(self):
        self.store.tick(book(quote(at=self.now,price='99')),self.now)
        event=self.store.claim();self.assertIsNotNone(event)
        r=dict(self.r,fallbackExchanges=['bybit'])
        self.change(action='save',id=self.id,rule=r)
        self.assertFalse(self.store.begin_send(event,book(quote(at=self.now,price='99')),self.now))
        self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')

    def test_fallback_payload_and_dispatch_use_same_source(self):
        quotes=book(quote(at=self.now,price='99'))
        self.store.tick(quotes,self.now);event=self.store.claim();self.assertIsNotNone(event)
        payload=json.loads(event['payload'])
        self.assertIn('备用行情：BINANCE · 现货',payload['body']);self.assertIn('BTC/USDT',payload['title'])
        self.assertTrue(self.store.begin_send(event,quotes,self.now))
    def test_stale_or_changed_source_cancels_claim(self):
        self.store.tick(book(quote(at=self.now,price='99')),self.now);event=self.store.claim()
        self.assertFalse(self.store.begin_send(event,book(quote(venue='bybit',at=self.now,price='99')),self.now))

    def test_fallback_reaches_bark_request_every_30_seconds_and_stops_on_recovery(self):
        selected=validate(dict(self.r,fallbackExchanges=['binance','bitget']))
        with self.store.db:self.store.db.execute('UPDATE rules SET config=? WHERE id=?',(json.dumps(selected),self.id))
        market=Market();self.addCleanup(market.pool.shutdown)
        sent=[]
        with patch('server.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"code":200}'
            for seconds,price,expected in [(0,'99',1),(29,'99',1),(30,'99',2),(59,'99',2),(60,'99',3),(90,'101',3)]:
                now=self.now+seconds
                with patch('store.time.time',return_value=now):
                    market.quotes=book(quote(at=now,price=price))
                    self.store.tick(market.quotes,now)
                    event=self.store.claim()
                    if event:
                        send_event(self.store,event,market)
                        request=opener.return_value.open.call_args.args[0]
                        payload=json.loads(request.data)
                        self.assertEqual(request.full_url,'https://api.day.app/push')
                        self.assertEqual((payload['level'],payload['volume'],payload['call']),('critical',5,'1'))
                        self.assertIn('备用行情：BINANCE · 现货',payload['body'])
                        self.assertIn('触发价格：99 USDT',payload['body'])
                        self.assertIn('BTC/USDT',payload['title'])
                        self.assertTrue(payload['device_key'].startswith('synthetic_'))
                        sent.append(seconds)
                    self.assertEqual(opener.return_value.open.call_count,expected)
            self.assertEqual(sent,[0,30,60])
            self.assertEqual({e['status'] for e in self.store.view('a')['events']},{'accepted'})
            self.assertEqual(self.store.view('a')['rules'][0]['state']['status'],'watching')

    def test_fallback_stales_after_queuing_never_reaches_bark_http(self):
        market=Market();self.addCleanup(market.pool.shutdown)
        with patch('store.time.time',return_value=self.now):
            market.quotes=book(quote(at=self.now,price='99'))
            self.store.tick(market.quotes,self.now);event=self.store.claim()
            self.assertIsNotNone(event)
            market.quotes={}
            with patch('server.build_opener') as opener:
                send_event(self.store,event,market)
                opener.assert_not_called()
        self.assertEqual(self.store.view('a')['events'][0]['status'],'cancelled')
    def test_all_failed_no_zero_price_or_old_price_trigger(self):
        self.store.tick({},self.now)
        view=self.store.view('a');self.assertEqual(view['rules'][0]['state']['status'],'stale');self.assertFalse(view['events'])
    def test_rules_and_device_unchanged(self):
        before=self.store.view('a');self.store.tick(book(quote(at=self.now)),self.now);after=self.store.view('a')
        self.assertEqual(before['revision'],after['revision']);self.assertEqual(before['device'],after['device'])
        self.assertEqual({k:v for k,v in before['rules'][0].items() if k!='state'}, {k:v for k,v in after['rules'][0].items() if k!='state'})

    def test_cancelled_one_shot_rearms_without_sending_stale_source(self):
        self.r.update(repeat=False,immediate=True)
        with self.store.db:self.store.db.execute('UPDATE rules SET config=? WHERE id=?',(json.dumps(self.r),self.id))
        self.store.tick(book(quote(at=self.now,price='99')),self.now);event=self.store.claim()
        self.assertFalse(self.store.begin_send(event,{},self.now+13))
        self.assertFalse(self.store.view('a')['rules'][0]['state']['fired'])
        self.store.tick(book(quote(at=self.now+14,price='99')),self.now+14)
        self.assertEqual(len(self.store.view('a')['events']),2)

    def test_all_venues_and_coins_create_edit_persist_native_identity_and_choice(self):
        import secrets
        venues=('binance','okx','bybit','bitget','gate','aster')
        for venue in venues:
            for base in ('BTC','ETH','SOL','PEPE','1000PEPE','WBTC'):
                with self.subTest(venue=venue,base=base):
                    native=base+'-USDT-SWAP' if venue=='okx' else base+'_USDT' if venue=='gate' else base+'USDT'
                    q=quote(base,venue,'future',self.now);q['symbol']=native
                    r=validate(dict(exchange=venue,market='future',symbol=native,priceType='last',condition='below',target='100',fallbackExchange='auto'))
                    def mutate(**data):
                        return self.store.mutate('matrix',dict(requestId=secrets.token_hex(16),revision=self.store.view('matrix')['revision'],**data),book(q))
                    rid=mutate(action='save',rule=r)['id']
                    for choice in ('auto','off',*tuple(v for v in venues if v!=venue)):
                        mutate(action='save',id=rid,rule=dict(r,fallbackExchange=choice))
                        saved=next(x for x in self.store.view('matrix')['rules'] if x['id']==rid)
                        self.assertEqual((saved['symbol'],saved['exchange'],saved['fallbackExchange'],saved['target']),(native,venue,choice,'100'))
        self.store.db.close();self.store=Store(self.temp.name)
        self.assertEqual(len(self.store.view('matrix')['rules']),36)


class OutageSimulationTests(unittest.TestCase):
    """Run real Market.poll -> Store.tick -> outbox with isolated timed-out feeds."""
    def run_scenario(self, venue='binance', base='BTC', choice='auto', selected=None):
        import secrets
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        clock=[time.time()];clock_patch=patch('market.time.time',side_effect=lambda:clock[0]);clock_patch.start();self.addCleanup(clock_patch.stop)
        failed=set();prices={'value':'101'}
        class SimulatedMarket(Market):
            def fetch(self, exchange, market):
                if (exchange,market) in failed:raise TimeoutError('isolated simulated feed outage')
                q=quote(base,exchange,market,clock[0],prices['value'])
                if exchange=='gate':q['symbol']=base+'_USDT'
                return book(q)
        market=SimulatedMarket();self.addCleanup(market.pool.shutdown)
        store=Store(temp.name);self.addCleanup(lambda:store.db.close())
        r=rule(base,venue,fallbackExchange=choice,**({'fallbackExchanges':selected} if selected is not None else {}))
        if venue=='gate':r['symbol']=base+'_USDT'
        primary=market.fetch(venue,'future')
        store.mutate('simulation',dict(action='save',rule=r,requestId=secrets.token_hex(16),revision=0),primary)
        start=clock[0];active={(e,m) for e in VENUES for m in ('future','spot')}
        def step(seconds):
            clock[0]=start+seconds
            market.poll(active)
            for future in list(market.pending.values()):
                try:future.result(timeout=2)
                except TimeoutError:pass
            market.poll(active)
            store.tick(market.snapshot()[0],clock[0])
            return store.view('simulation')['rules'][0]['state']
        for t in (0,3,6):step(t)
        return store,market,failed,prices,step,start

    def test_timeout_matrix_six_primary_venues_three_coins_reaches_actual_fallback_event(self):
        for venue in VENUES:
            for base in ('BTC','ETH','SOL'):
                with self.subTest(venue=venue,base=base):
                    store,market,failed,prices,step,start=self.run_scenario(venue,base)
                    failed.add((venue,'future'));prices['value']='99'
                    self.assertFalse(step(9)['source']['fallback'])
                    state=step(19)
                    self.assertEqual(state['status'],'alarming');self.assertTrue(state['source']['fallback'])
                    self.assertNotEqual(state['source']['exchange'],venue);self.assertEqual(state['source']['market'],'spot')
                    event=store.view('simulation')['events'][0]
                    self.assertEqual(event['source'],state['source']);self.assertEqual(event['price'],'99')
                    self.assertIn('备用行情',event['body'])
                    self.assertEqual(market.health[(venue,'future')]['error'],'TimeoutError')

    def test_backup_timeout_moves_to_next_and_all_timeout_pauses_without_false_event(self):
        store,market,failed,prices,step,start=self.run_scenario()
        failed.add(('binance','future'));prices['value']='99'
        first=step(19);self.assertEqual(first['source']['exchange'],'okx')
        failed.add(('okx','spot'))
        second=step(33);self.assertEqual(second['source']['exchange'],'bybit')
        self.assertEqual(len(store.view('simulation')['events']),1) # no new 30-second slot
        failed.update((v,m) for v in VENUES for m in ('spot','future'))
        state=step(47)
        self.assertEqual(state['status'],'stale');self.assertEqual(state['routingReason'],'no_fresh_backup')
        self.assertEqual(len(store.view('simulation')['events']),1)
        self.assertEqual([x['status'] for x in state['routingHistory']],['primary','fallback','fallback','unavailable'])

    def test_three_distinct_primary_recoveries_and_no_duplicate_repeat(self):
        store,market,failed,prices,step,start=self.run_scenario()
        failed.add(('binance','future'));prices['value']='99';step(19)
        failed.clear()
        self.assertTrue(step(22)['source']['fallback']);self.assertTrue(step(25)['source']['fallback'])
        self.assertFalse(step(28)['source']['fallback']);self.assertEqual(len(store.view('simulation')['events']),1)
        step(49);self.assertEqual(len(store.view('simulation')['events']),2)

    def test_selected_backup_failure_does_not_silently_use_another(self):
        store,market,failed,prices,step,start=self.run_scenario(choice='bybit')
        failed.update({('binance','future'),('bybit','spot')})
        state=step(19)
        self.assertEqual(state['status'],'stale');self.assertEqual(state['sourceStatus'],'unavailable')
        self.assertFalse(store.view('simulation')['events'])

    def test_multi_selected_outage_delivery_and_failure_never_uses_unchecked(self):
        store,market,failed,prices,step,start=self.run_scenario(selected=['bybit','gate'])
        failed.add(('binance','future'));prices['value']='99'
        self.assertEqual(step(19)['source']['exchange'],'bybit') # OKX healthy but unchecked
        failed.add(('bybit','spot'))
        self.assertEqual(step(33)['source']['exchange'],'gate') # Bitget healthy but unchecked
        self.assertEqual(len(store.view('simulation')['events']),1)
        step(49)
        self.assertEqual(len(store.view('simulation')['events']),2)
        self.assertEqual(store.view('simulation')['events'][0]['source']['exchange'],'gate')
        failed.add(('gate','spot'))
        self.assertEqual(step(63)['status'],'stale')
        self.assertEqual(len(store.view('simulation')['events']),2)

    def test_disabled_backup_is_reported_explicitly(self):
        store,market,failed,prices,step,start=self.run_scenario(choice='off')
        failed.add(('binance','future'))
        state=step(19)
        self.assertEqual(state['status'],'stale');self.assertEqual(state['routingReason'],'backup_disabled')


if __name__ == '__main__':unittest.main()
