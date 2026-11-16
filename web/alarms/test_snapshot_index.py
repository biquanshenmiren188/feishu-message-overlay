import unittest
from concurrent.futures import Future
from unittest.mock import patch
from test_sources import rule,quote,book
from sources import select,QuoteSnapshot
from market import Market

class IndexTests(unittest.TestCase):
    def test_route_equivalence_over_warmup_failover_recovery_and_age(self):
        for base in ('BTC','ETH','1000PEPE','LUNA','PAY'):
            for backup in ([],['binance'],['bybit','binance','gate']):
                r=rule(base,fallbackExchanges=backup);left=right={}
                for step in range(40):
                    now=100+step*2
                    primary=quote(base,'okx','future',now if step<4 or step>24 else 106)
                    q=book(primary,*[quote(base,v,at=now if step<20 else now-20,price='101' if step!=7 else '120') for v in ('binance','bybit','gate')])
                    for n in range(100):q.update(book(quote('OTHER'+str(n),'binance',at=now)))
                    if step==9:
                        duplicate=quote(base,'binance',at=now);duplicate['symbol']+='X';q.update(book(duplicate))
                    a=select(r,left,q,now);b=select(r,right,QuoteSnapshot(q),now)
                    self.assertEqual(a,b,(base,backup,step));left,right=a[2],b[2]
                    self.assertEqual(select(r,left,q,now,advance=False),select(r,right,QuoteSnapshot(q),now,advance=False))
    def test_snapshot_reuse_and_completed_poll_invalidation(self):
        m=Market();self.addCleanup(m.pool.shutdown,wait=False,cancel_futures=True)
        m.quotes=book(quote());one,health=m.snapshot();self.assertIs(one,m.snapshot()[0])
        complete=Future();complete.set_result(book(quote(at=104)));m.pending[('binance','spot')]=complete
        with patch.object(m.pool,'submit',return_value=Future()):m.poll(set())
        two,health=m.snapshot();self.assertIsNot(one,two)
        self.assertEqual(next(iter(one.values()))['observedAt'],100)
        self.assertEqual(next(iter(two.values()))['observedAt'],104)
        fail=Future();fail.set_exception(ValueError('fixture'));m.pending[('binance','spot')]=fail
        with patch.object(m.pool,'submit',return_value=Future()):m.poll(set())
        self.assertIs(two,m.snapshot()[0]);self.assertFalse(m.snapshot()[1]['binance/spot']['ok'])
