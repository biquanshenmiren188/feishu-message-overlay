"""Denomination-aware route, storage and actual sender contract tests. No network."""
import json
import secrets
import tempfile
import time
import unittest
from decimal import Decimal
from unittest.mock import patch

from denominations import FUTURES, REGISTRY, denomination, native, converted
from engine import validate, number
from market import Market
from sources import select, identity, source_key
from store import Store
from server import send_event
from test_sources import quote, book


def sample(venue, market, base, at, price):
    q = quote(base, venue, market, at, price)
    q['symbol'] = native(venue, market, base)
    return q


class DenominationTests(unittest.TestCase):
    def test_registry_is_exact_and_not_a_prefix_or_lot_size_guess(self):
        for base in ('1INCH','0G','4','1000UNKNOWN','1000WBTC'):
            self.assertIsNone(denomination(sample('binance','future',base,100,'1')))
        q = sample('binance','future','1000PEPE',100,'0.004')
        self.assertEqual(denomination(q)['units'],'1000')
        for bad in (dict(q,symbol='PEPEUSDT'),dict(q,base='PEPE'),dict(q,quote='USDC'),
                    dict(q,instrumentVerified=False),dict(q,unit='PEPE')):
            self.assertIsNone(denomination(bad))
        q = sample('okx','future','PEPE',100,'0.000004')
        q.update(ctVal='1000000',priceScale='8',quanto_multiplier='1000000')
        self.assertEqual(denomination(q)['units'],'1')

    def test_decimal_conversion_both_directions_and_already_scaled_spot(self):
        cases = [
            ('binance','1000PEPE','okx','PEPE','0.0000041234567890123456789','0.0041234567890123456789000'),
            ('bybit','10000SATS','binance','1000SATS','0.00000815','0.00008150'),
            ('bybit','1000CAT','binance','1000CAT','0.00155','0.00155'),
            ('bitget','1MCHEEMS','binance','1000CHEEMS','0.00035','0.35000'),
            ('gate','CHEEMS','binance','1000CHEEMS','0.00035','0.00000035'),
            ('bybit','1000000BABYDOGE','binance','1MBABYDOGE','0.000275','0.000275'),
            ('bybit','SHIB1000','okx','SHIB','0.0000042','0.0042000'),
        ]
        for main,base,backup,spot,price,expected in cases:
            with self.subTest(base=base,spot=spot):
                target=identity(sample(main,'future',base,100,'1'))
                q=sample(backup,'spot',spot,100,price);before=dict(q)
                out=converted(q,target)
                self.assertEqual(Decimal(out['last']),Decimal(expected))
                self.assertEqual(q,before)
                self.assertEqual(out['lastAt'],100)
                self.assertEqual(out['rawLast'],price)
        self.assertIsNone(converted(sample('binance','spot','WBTC',100,'1'),identity(sample('binance','future','1000PEPE',100,'1'))))

    def test_every_reviewed_scaled_contract_create_edit_reload_fails_over_and_sends_30s(self):
        # Exercise every reviewed primary against EVERY reviewed other-venue spot
        # denomination, above and below. Actual Store + send_event; only HTTP mocked.
        self.scenarios = 0
        for main, aliases in FUTURES.items():
            for base,(asset,units) in aliases.items():
                backups=[(venue,entry[0],entry[2]) for (venue,market,symbol),entry in REGISTRY.items()
                         if market=='spot' and venue!=main and entry[1]==asset]
                self.assertTrue(backups,base)
                for backup,spot,spot_units in backups:
                    for condition in ('above','below'):
                        with self.subTest(main=main,base=base,backup=backup,spot=spot,condition=condition):
                            self.exercise(main,base,units,backup,spot,spot_units,condition)
                            self.scenarios+=1
        self.assertGreater(self.scenarios,200)

    def exercise(self,main,base,units,backup,spot,spot_units,condition):
        now=time.time();clock=[now]
        with tempfile.TemporaryDirectory() as temp, patch('store.time.time',side_effect=lambda:clock[0]):
            store=Store(temp);market=Market()
            try:
                target=Decimal('0.000004')*units
                clear=target*(Decimal('1.01') if condition=='below' else Decimal('.99'))
                hit=target*(Decimal('.99') if condition=='below' else Decimal('1.01'))
                r=validate(dict(exchange=main,market='future',symbol=native(main,'future',base),
                    priceType='last',condition=condition,target=str(target),repeat=True,fallbackExchanges=[backup]))
                def primary(t):return sample(main,'future',base,t,str(clear))
                def secondary(t,p):return sample(backup,'spot',spot,t,str(p*Decimal(spot_units)/units))
                def mutate(**kw):return store.mutate('isolated',dict(requestId=secrets.token_hex(16),revision=store.view('isolated')['revision'],**kw),book(primary(clock[0])))
                rid=mutate(action='save',rule=r)['id']
                mutate(action='save',id=rid,rule=r)
                mutate(action='bind',key='synthetic_denomination_test_only',label='isolated')
                store.db.close();store=Store(temp)
                saved=store.view('isolated')['rules'][0]
                self.assertEqual((saved['symbol'],saved['target'],saved['fallbackExchanges']),(r['symbol'],r['target'],[backup]))
                for sec in (0,2,4):
                    clock[0]=now+sec
                    market.quotes=book(primary(clock[0]),secondary(clock[0],clear))
                    store.tick(market.quotes,clock[0])
                before={k:v for k,v in store.view('isolated')['rules'][0].items() if k!='state'}
                with patch('server.build_opener') as transport:
                    transport.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"code":200}'
                    sends=[]
                    for sec,expected in ((20,1),(49,1),(50,2),(79,2),(80,3)):
                        clock[0]=now+sec
                        market.quotes=book(secondary(clock[0],hit)) # main stream absent
                        store.tick(market.quotes,clock[0])
                        state=store.view('isolated')['rules'][0]['state']
                        self.assertEqual(state['source']['exchange'],backup)
                        self.assertEqual(number(state['price']),hit)
                        event=store.claim()
                        if event:
                            send_event(store,event,market)
                            payload=json.loads(transport.return_value.open.call_args.args[0].data)
                            self.assertIn(base+'/USDT',payload['title'])
                            self.assertIn('触发价格：'+state['price']+' USDT',payload['body'])
                            self.assertEqual((payload['level'],payload['call'],payload['volume']),('critical','1',5))
                            sends.append(sec)
                        self.assertEqual(transport.return_value.open.call_count,expected)
                    self.assertEqual(sends,[20,50,80])
                    self.assertEqual({e['status'] for e in store.view('isolated')['events']},{'accepted'})
                    # Converted CLEAR price prevents sending, despite a misleading raw magnitude.
                    clock[0]=now+110;market.quotes=book(secondary(clock[0],hit))
                    store.tick(market.quotes,clock[0]);event=store.claim();self.assertIsNotNone(event)
                    market.quotes=book(secondary(clock[0],clear));send_event(store,event,market)
                    self.assertEqual(transport.return_value.open.call_count,3)
                    self.assertEqual(store.view('isolated')['events'][0]['status'],'cancelled')
                    # A healthy but UNCHECKED exact-asset source cannot replace selected source.
                    clock[0]=now+140;market.quotes={}
                    store.tick(market.quotes,clock[0]);self.assertIsNone(store.claim())
                    self.assertEqual(store.view('isolated')['rules'][0]['state']['status'],'stale')
                    for sec in (142,144,146):
                        clock[0]=now+sec;market.quotes=book(primary(clock[0]),secondary(clock[0],clear))
                        store.tick(market.quotes,clock[0]);self.assertIsNone(store.claim())
                    self.assertFalse(store.view('isolated')['rules'][0]['state']['source']['fallback'])
                after={k:v for k,v in store.view('isolated')['rules'][0].items() if k!='state'}
                self.assertEqual(before,after)
            finally:store.db.close();market.pool.shutdown()

    def test_reverse_conversion_also_reaches_sender_at_30_seconds(self):
        for condition in ('above','below'):
            self.exercise('gate','CHEEMS',1,'binance','1000CHEEMS',1000,condition)
            self.exercise('okx','SATS',1,'binance','1000SATS',1000,condition)
            self.exercise('okx','BABYDOGE',1,'binance','1MBABYDOGE',1000000,condition)

    def test_whitelist_identity_qualification_and_source_change_guard(self):
        r=validate(dict(exchange='binance',market='future',symbol='1000PEPEUSDT',priceType='last',
                        condition='below',target='0.004',repeat=True,fallbackExchanges=['okx']))
        state={}
        for t in (100,102,104):
            p=sample('binance','future','1000PEPE',t,'0.0041')
            s=sample('okx','spot','PEPE',t,'0.0000041')
            q,_,state=select(r,state,book(p,s),t)
        q,_,out=select(r,state,book(sample('okx','spot','PEPE',118,'0.0000039')),118)
        self.assertEqual(number(q['last']),Decimal('.0039'))
        self.assertNotEqual(source_key(out['source']),source_key(dict(out['source'],conversionFactor='1')))
        for wrong in (sample('bitget','spot','PEPE',118,'0.0000039'),
                      sample('okx','spot','WPEPE',118,'0.0000039'),
                      dict(sample('okx','spot','PEPE',118,'0.0000039'),quote='USDC')):
            self.assertIsNone(select(r,state,book(wrong),118)[0])
        # Invalid/wild values cannot allocate unbounded decimal strings or qualify.
        for value in ('NaN','Infinity','1e999999999','-1','0'):
            self.assertIsNone(select(r,state,book(sample('okx','spot','PEPE',118,value)),118)[0])


if __name__ == '__main__':unittest.main()
