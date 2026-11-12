import json
import tempfile
import time
import unittest
from unittest.mock import patch
from engine import validate, evaluate
from sources import select, identity, eligible, active_groups, fresh
from instruments import load
from store import Store


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
        for base in ('1000PEPE','PAY','BTC3L'):
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
    def test_fallback_payload_and_dispatch_use_same_source(self):
        quotes=book(quote(at=self.now,price='99'))
        self.store.tick(quotes,self.now);event=self.store.claim();self.assertIsNotNone(event)
        payload=json.loads(event['payload'])
        self.assertIn('备用行情：BINANCE · 现货',payload['body']);self.assertIn('BTC/USDT',payload['title'])
        self.assertTrue(self.store.begin_send(event,quotes,self.now))
    def test_stale_or_changed_source_cancels_claim(self):
        self.store.tick(book(quote(at=self.now,price='99')),self.now);event=self.store.claim()
        self.assertFalse(self.store.begin_send(event,book(quote(venue='bybit',at=self.now,price='99')),self.now))
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


if __name__ == '__main__':unittest.main()
