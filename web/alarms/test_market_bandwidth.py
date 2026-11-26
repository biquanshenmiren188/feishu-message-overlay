import gzip
import io
import unittest
from concurrent.futures import Future
from unittest.mock import patch

from market import Market, get


class BandwidthTests(unittest.TestCase):
    def test_compression_preserves_json_and_limits_decoded_size(self):
        for raw, oversize in [(b'{"lastPrice":"123.4500"}', False), (b' ' * 8000001, True)]:
            response = io.BytesIO(gzip.compress(raw))
            response.headers = {'Content-Encoding': 'gzip'}
            with patch('market.build_opener') as opener:
                opener.return_value.open.return_value = response
                if oversize:
                    with self.assertRaises(ValueError):
                        get('https://example.test/')
                else:
                    self.assertEqual(get('https://example.test/'), {'lastPrice':'123.4500'})
                req = opener.return_value.open.call_args.args[0]
                self.assertEqual(req.get_header('Accept-encoding'), 'gzip')

    def test_single_ticker_uses_the_original_exchange_fields(self):
        for exchange, symbol in [('binance','BTCUSDT'), ('okx','BTC-USDT-SWAP')]:
            def fetch(url):
                self.assertIn(symbol,url)
                if exchange == 'binance':
                    return (dict(symbol=symbol,markPrice='101',time=101000) if 'premiumIndex' in url
                            else dict(symbol=symbol,lastPrice='100',closeTime=100000))
                row = (dict(instId=symbol,markPx='101',ts='101000') if 'mark-price' in url
                       else dict(instId=symbol,last='100',ts='100000'))
                return {'code':'0','data':[row]}
            market = Market(getter=fetch)
            with patch.object(market,'instruments',return_value={symbol:{'base':'BTC','unit':'BTC'}}):
                quote = market.fetch(exchange,'future',symbol)[exchange,'future',symbol]
            self.assertEqual((quote['last'], quote['mark'], quote['lastAt'], quote['markAt']),
                             ('100','101',100,101))
            market.pool.shutdown()

    def test_partial_merge_preserves_other_prices_and_failure_retries_full(self):
        market = Market()
        group = ('binance','future')
        target = (*group,'BTCUSDT')
        other = (*group,'ETHUSDT')
        market.quotes = {target:{'last':'1'},other:{'last':'20'}}
        market.health[group] = {'count':2}
        result = Future()
        result.set_result({target:{'last':'2'}})
        market.pending[group] = result
        market.partial[group] = target[-1]
        with patch('market.VENUES', ('binance',)), patch.object(market.pool,'submit',return_value=Future()) as submit:
            market.poll({group:target[-1]})
            self.assertEqual(market.quotes, {target:{'last':'2'},other:{'last':'20'}})
            self.assertEqual(market.health[group]['count'],2)
            failure = Future()
            failure.set_exception(ValueError('single unavailable'))
            market.pending[group] = failure
            market.partial[group] = target[-1]
            market.poll({group:target[-1]})
            submit.assert_called_with(market.fetch,*group)
        market.pool.shutdown()
