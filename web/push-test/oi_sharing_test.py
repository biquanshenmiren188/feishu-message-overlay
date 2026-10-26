import copy,unittest
from advanced_rules import OISnapshot,DEFAULT,reasons
from oi_source_cache import OISourceCache

class OISharingTest(unittest.TestCase):
    def test_consumers_do_not_extend_ttl_or_retain_entire_old_maps(self):
        source=OISourceCache();self.addCleanup(source.close)
        a,b=OISnapshot(source),OISnapshot(source);calls=[]
        def read(ex,now):
            calls.append(now)
            return ex,{ex+':'+coin+'USDT':dict(value=1000000,time=now*1000,basis='double-v1') for coin in ('BTC','ETH','OTHER')}
        a._read=b._read=read;rule=dict(copy.deepcopy(DEFAULT),globalOI=50)
        row=dict(coin='BTC',buy='BINANCE',sell='GATE',mode='FS')
        a.enrich([row],rule,1000);b.enrich([row],rule,1029)
        self.assertEqual(calls,[1000]);self.assertEqual(list(b.cache['binance']),['binance:BTCUSDT'])
        b.enrich([row],rule,1030)
        self.assertEqual(calls,[1000,1030]);self.assertEqual(row['oi']['left']['time'],1030000)
        a.enrich([row],rule,1031);self.assertIs(a.cache['binance']['binance:BTCUSDT'],b.cache['binance']['binance:BTCUSDT'])
        a.enrich([row],DEFAULT,1032);self.assertEqual(a.cache,{})

    def test_invalid_exchange_stays_missing_without_cache_key_or_fetch(self):
        source=OISourceCache();self.addCleanup(source.close);snap=OISnapshot(source)
        snap._read=lambda *args:self.fail('unknown venue must not fetch')
        row=dict(coin='BTC',mode='FS',buy='',sell='GATE');rule=dict(copy.deepcopy(DEFAULT),globalOI=50)
        snap.enrich([row],rule,1000)
        self.assertIn('缺失或过期',reasons(row,rule)[0])

if __name__=='__main__':unittest.main()
