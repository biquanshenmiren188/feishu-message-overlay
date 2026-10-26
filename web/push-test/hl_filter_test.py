import copy,io,json,time,unittest
from unittest.mock import patch
from advanced_rules import OISnapshot,DEFAULT,reasons
from hyperliquid_oi import SOURCE
from oi_source_cache import OISourceCache

class HLFilterTest(unittest.TestCase):
    def setUp(self):
        self.now=time.time();self.ms=self.now*1000
        self.entry=dict(nativeCoin='HYPE',name='HYPEUSDT',quoteCurrency='USDC',settleCurrency='USDC',sourceUrl=SOURCE,
                        openInterestUsd=500000,oiTs=self.ms-2000,quoteConversion=1.001,quoteConversionAt=self.ms-1000)
        self.rule=dict(copy.deepcopy(DEFAULT),globalOI=50)
        self.row=dict(coin='HYPE',mode='FS',buy='HL',sell='BINANCE',oiContracts={'left':'HYPEUSDT'})
    def snapshot(self):
        return dict(data=dict(hyperliquidFuture=dict(list=[self.entry])))
    def reader(self):
        sources=OISourceCache();self.addCleanup(sources.close)
        return OISnapshot(source_cache=sources)
    def test_gateway_route_usdt_boundary_and_fx_expiry_are_enforced(self):
        with patch('advanced_rules.urlopen',return_value=io.BytesIO(json.dumps(self.snapshot()).encode())) as fetch:
            snap=self.reader();snap.enrich([self.row],self.rule,self.now)
        self.assertEqual(fetch.call_args.args[0],'http://127.0.0.1:8795/api/hyperliquid/market')
        self.assertFalse(reasons(self.row,self.rule))
        self.row['oiCheckedAt']=self.now+30
        self.assertIn('缺失或过期',reasons(self.row,self.rule)[0])
    def test_namespace_and_prefix_cannot_borrow_native_oi(self):
        for contract in ('xyz:HYPE','xyz:HYPEUSDT','kHYPEUSDT',None,''):
            self.row['oiContracts']={'left':contract}
            with patch('advanced_rules.urlopen',return_value=io.BytesIO(json.dumps(self.snapshot()).encode())):
                self.reader().enrich([self.row],self.rule,self.now)
            self.assertIn('缺失或过期',reasons(self.row,self.rule)[0])
    def test_text_message_uses_exact_native_coin_without_namespace_removal(self):
        self.row.pop('oiContracts');self.row['coin']='XYZ:HYPE'
        with patch('advanced_rules.urlopen',return_value=io.BytesIO(json.dumps(self.snapshot()).encode())):
            self.reader().enrich([self.row],self.rule,self.now)
        self.assertIn('缺失或过期',reasons(self.row,self.rule)[0])

if __name__=='__main__':unittest.main()
