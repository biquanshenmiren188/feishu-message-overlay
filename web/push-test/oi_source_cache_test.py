"""Public OI sharing and bounded concurrency; no network or profile state."""
import copy
import threading
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from advanced_rules import DEFAULT, reasons
from oi_source_cache import OISourceCache, VENUES, shared_read, shared_read_many


class OISourceCacheTest(unittest.TestCase):
    def setUp(self):
        self.cache = OISourceCache()
        self.addCleanup(self.cache.close)
        self.now = 1800000000
        self.record = dict(value=9890000, basis='double-v1', time=self.now*1000-7000,
                           expiresAt=self.now*1000+10000)

    def test_28_callers_coalesce_seven_sources_and_run_at_most_three_loaders(self):
        barrier = threading.Barrier(28)
        lock = threading.Lock()
        three_started = threading.Event()
        release = threading.Event()
        calls = Counter()
        active = peak = 0
        exchanges = sorted(VENUES)

        def loader(ex):
            nonlocal active, peak
            with lock:
                calls[ex] += 1
                active += 1
                peak = max(peak, active)
                if active == 3:
                    three_started.set()
            try:
                if not release.wait(5):
                    raise TimeoutError('test loader was not released')
                return {ex+':BULLAUSDT':dict(self.record)}
            finally:
                with lock:
                    active -= 1

        def caller(index):
            barrier.wait(5)
            ex = exchanges[index % 7]
            return ex, self.cache.read(ex, self.now, 30, lambda: loader(ex))

        with ThreadPoolExecutor(max_workers=28) as callers:
            futures = [callers.submit(caller, i) for i in range(28)]
            try:
                self.assertTrue(three_started.wait(5))
                self.assertEqual(peak, 3)
            finally:
                release.set()
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual(calls, Counter({ex:1 for ex in exchanges}))
        self.assertEqual(peak, 3)
        for ex in exchanges:
            values = [data for name,data in results if name == ex]
            self.assertTrue(all(data is values[0] for data in values))

    def test_different_consumers_share_only_source_objects(self):
        data = {'aster:BULLAUSDT':self.record}
        with patch('oi_source_cache._shared', self.cache):
            first = shared_read('aster', self.now, 30, lambda: data)
            second = shared_read_many(['aster'], self.now+1, {'aster':30},
                                      lambda ex: self.fail('duplicate source read'))['aster']
        self.assertIs(first, second)
        allow = dict(copy.deepcopy(DEFAULT), globalOI=50)
        block = dict(copy.deepcopy(DEFAULT), globalOI=1000)
        row = dict(coin='BULLA', buy='ASTER', sell='GATE', mode='FS',
                   oiCheckedAt=self.now, oi={'left':first['aster:BULLAUSDT']})
        before = copy.deepcopy(data)
        self.assertEqual(reasons(row, allow), [])
        self.assertIn('低于', reasons(row, block)[0])
        self.assertEqual(reasons(row, allow), [])
        self.assertEqual(data, before)
        self.assertEqual(set(self.cache._entries), {'aster'})

    def test_ttl_is_per_caller_and_refresh_replaces_without_renewing_observation(self):
        original = {'hyperliquid:BULLAUSDT':self.record}
        latest = {'hyperliquid:OTHERUSDT':dict(self.record, value=100)}
        self.assertIs(self.cache.read('hyperliquid', self.now, 10, lambda: original), original)
        self.assertIs(self.cache.read('hyperliquid', self.now+9, 10,
                                     lambda: self.fail('early refresh')), original)
        self.assertIs(self.cache.read('hyperliquid', self.now+10, 30,
                                     lambda: self.fail('caller TTL ignored')), original)
        self.assertIs(self.cache.read('hyperliquid', self.now+10, 10, lambda: latest), latest)
        self.assertIs(self.cache._entries['hyperliquid']['data'], latest)
        self.assertNotIn('hyperliquid:BULLAUSDT', latest)
        self.assertEqual(original['hyperliquid:BULLAUSDT']['time'], self.now*1000-7000)
        self.assertEqual(latest['hyperliquid:OTHERUSDT']['expiresAt'], self.now*1000+10000)

    def test_failed_refresh_clears_success_and_is_throttled_then_recovers(self):
        data = {'aster:BULLAUSDT':self.record}
        self.cache.read('aster', self.now, 30, lambda: data)

        def offline():
            raise OSError('offline')

        missing = self.cache.read('aster', self.now+30, 30, offline)
        self.assertEqual(missing, {})
        self.assertIs(self.cache.read('aster', self.now+59, 30,
                                     lambda: self.fail('failure retry storm')), missing)
        self.assertIs(self.cache.read('aster', self.now+60, 30, lambda: data), data)
        self.assertEqual(self.record['time'], self.now*1000-7000)

    def test_empty_and_invalid_source_payloads_remain_missing(self):
        for index, value in enumerate(({}, None, [], 'bad', 0)):
            self.assertEqual(self.cache.read('aster', self.now+index*30, 30, lambda: value), {})

    def test_read_many_is_source_bounded_and_cache_cannot_grow_with_profile_keys(self):
        data = self.cache.read_many(VENUES, self.now, dict.fromkeys(VENUES,30),
                                    lambda ex: {ex+':BULLAUSDT':dict(self.record)})
        self.assertEqual(set(data), VENUES)
        self.assertEqual(len(self.cache._entries), 7)
        for ex in ('profile-1', 'binance:user-2', 'unknown'):
            with self.assertRaises(ValueError):
                self.cache.read(ex, self.now, 30, lambda: {})
        self.assertEqual(len(self.cache._entries), 7)


if __name__ == '__main__':
    unittest.main()
