import copy
import unittest

from hyperliquid_oi import SOURCE, hyperliquid_oi


class HyperliquidOITest(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000000

    def row(self, coin='BTC', **changes):
        row = dict(name=coin+'USDT', nativeCoin=coin, quoteCurrency='USDC' if coin in ('HYPE','PURR') else 'USDT',
                   settleCurrency='USDC', quoteConversion=1, quoteConversionAt=self.now,
                   openInterestUsd=1000000, oiTs=self.now-10000, sourceUrl=SOURCE)
        row.update(changes)
        return row

    def read(self, *rows):
        return hyperliquid_oi(dict(data=dict(hyperliquidFuture=dict(ts=self.now,list=list(rows)))), self.now)

    def test_usdt_native_contracts_use_exact_notional_without_doubling_or_fx(self):
        value = self.read(self.row())['hyperliquid:BTCUSDT']
        self.assertEqual(value['value'],1000000)
        self.assertEqual(value['multiplier'],1)
        self.assertEqual(value['basis'],'double-v1')
        self.assertEqual(value['time'],self.now-10000)
        self.assertEqual(value['nativeSymbol'],'BTCUSDT')
        self.assertEqual(value['nativeQuote'],'USDT')

    def test_hype_and_purr_use_fresh_fx_and_oldest_observation(self):
        for coin in ('HYPE','PURR'):
            value=self.read(self.row(coin,quoteConversion=.998,quoteConversionAt=self.now-20000))['hyperliquid:'+coin+'USDT']
            self.assertEqual(value['value'],998000)
            self.assertEqual(value['rawValue'],1000000)
            self.assertEqual(value['time'],self.now-20000)
            self.assertEqual(value['observedAt'],self.now-10000)
            self.assertEqual(value['nativeQuote'],'USDC')

    def test_namespace_and_quote_or_collateral_mismatches_never_fall_back(self):
        for row in [self.row('xyz:BTC'),self.row('BTC',name='xyz:BTCUSDT'),
                    self.row('xyz:BTC',name='BTCUSDT'),self.row('BTC',quoteCurrency='USDC'),
                    self.row('BTC',quoteCurrency='UNKNOWN'),self.row('HYPE',quoteCurrency='USDT'),
                    self.row('BTC',settleCurrency='USDH'),self.row('BTC',sourceUrl='other')]:
            self.assertEqual(self.read(row),{})

    def test_k_prefix_and_numeric_prefix_are_not_aliases(self):
        values=self.read(self.row('kPEPE'),self.row('1000PEPE'),self.row('PEPE'))
        self.assertEqual(set(values),{'hyperliquid:KPEPEUSDT','hyperliquid:1000PEPEUSDT','hyperliquid:PEPEUSDT'})
        self.assertEqual(values['hyperliquid:KPEPEUSDT']['nativeCoin'],'kPEPE')
        self.assertEqual(values['hyperliquid:KPEPEUSDT']['nativeSymbol'],'kPEPEUSDT')

    def test_case_collisions_or_duplicate_native_names_are_missing(self):
        for rows in [(self.row('kPEPE'),self.row('KPEPE')),
                     (self.row('BTC'),self.row('BTC')),
                     (self.row('btc',openInterestUsd=None),self.row('BTC'))]:
            self.assertEqual(self.read(*rows),{})
        self.assertEqual(self.read(self.row('kPEPE',name='KPEPEUSDT')),{})

    def test_source_and_fx_freshness_boundaries(self):
        for age,valid in [(120000,True),(120001,False),(-1000,True),(-1001,False)]:
            self.assertEqual(bool(self.read(self.row(oiTs=self.now-age))),valid)
        for age,valid in [(30000,True),(30001,False),(-1000,True),(-1001,False)]:
            self.assertEqual(bool(self.read(self.row('HYPE',quoteConversionAt=self.now-age))),valid)

    def test_bad_numbers_and_overflow_never_become_fresh_zero(self):
        for field in ('openInterestUsd','oiTs','quoteConversion','quoteConversionAt'):
            for value in (None,True,'1',float('nan'),float('inf'),10**400,-1):
                self.assertEqual(self.read(self.row('HYPE',**{field:value})),{})
        self.assertEqual(self.read(self.row('HYPE',openInterestUsd=1e308,quoteConversion=1e308)),{})
        self.assertEqual(self.read(self.row('HYPE',openInterestUsd=10**200,quoteConversion=10**200)),{})
        self.assertEqual(self.read(self.row(quoteConversion=1.001)),{})
        self.assertEqual(self.read(self.row('HYPE',quoteConversion=0)),{})

    def test_real_zero_and_no_mutation_or_read_time_renewal(self):
        row=self.row(openInterestUsd=0);before=copy.deepcopy(row)
        self.assertEqual(self.read(row)['hyperliquid:BTCUSDT']['value'],0)
        self.assertEqual(row,before)
        self.assertEqual(self.read(row)['hyperliquid:BTCUSDT']['time'],row['oiTs'])

    def test_only_perpetual_book_and_valid_payloads_are_accepted(self):
        for payload in [None,[],{},dict(data=None),dict(data=dict(hyperliquidFuture=[])),
                        dict(data=dict(hyperliquidFuture=dict(list=None))),
                        dict(data=dict(hyperliquidSpot=dict(list=[self.row()])))]:
            self.assertEqual(hyperliquid_oi(payload,self.now),{})
        self.assertEqual(self.read(None,[],{},self.row('bad coin')),{})
        self.assertEqual(hyperliquid_oi(dict(data=dict(hyperliquidFuture=dict(list=[self.row()]))),True),{})


if __name__=='__main__':unittest.main()
