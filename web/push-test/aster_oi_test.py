"""Aster source-routing regression: shared normalized cache, never card text."""
import copy
import io
import json
import unittest
from unittest.mock import patch

from advanced_rules import DEFAULT, OISnapshot, reasons


class AsterOITest(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000
        self.rule = dict(copy.deepcopy(DEFAULT), globalOI=50)
        self.row = dict(coin='BULLA', buy='ASTER', sell='GATE', mode='FS')
        self.value = dict(value=9890000, rawValue=9890000, multiplier=1,
                          basis='double-v1', time=self.now*1000-7000,
                          timeBasis='observed', sourceTime=None, source='official')

    def read(self, payload, row=None, rule=None):
        snap = OISnapshot()
        with patch('advanced_rules.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as fetch:
            snap.enrich([row or self.row], rule or self.rule, self.now)
        return snap, fetch

    def test_aster_uses_existing_stats_and_preserves_value_basis_and_time(self):
        _, fetch = self.read(dict(asterOI={'aster:BULLAUSDT':self.value}))
        self.assertEqual(fetch.call_args.args[0], 'http://127.0.0.1:8792/api/market-stats')
        self.assertEqual(self.row['oi']['left'], self.value)
        self.assertEqual(reasons(self.row, self.rule), [])

    def test_zero_below_equal_and_above_threshold(self):
        for value, blocked in [(0,True),(499999,True),(500000,False),(9890000,False)]:
            self.value['value']=value
            self.read(dict(asterOI={'aster:BULLAUSDT':self.value}))
            result=reasons(self.row,self.rule)
            self.assertEqual(bool(result),blocked)
            if blocked:self.assertIn('低于',result[0])

    def test_stale_future_bad_basis_missing_and_invalid_value_stay_blocked(self):
        for change in [dict(time=self.now*1000-300001),dict(time=self.now*1000+30001),
                       dict(basis='raw'),dict(value=None),dict(value=True),dict(value=-1),dict(value='9890000')]:
            self.read(dict(asterOI={'aster:BULLAUSDT':dict(self.value,**change)}))
            self.assertIn('缺失或过期',reasons(self.row,self.rule)[0])

    def test_exact_venue_symbol_no_alias_or_payload_fallback(self):
        for payload in [dict(asterOI={'aster:1000BULLAUSDT':self.value}),
                        dict(asterOI={'binance:BULLAUSDT':self.value}),
                        dict(basis='double-v1',data={'aster:BULLAUSDT':self.value}),
                        dict(asterOI=[]),dict(asterOI={'aster:BULLAUSDT':None}),{},[]]:
            self.read(payload)
            self.assertIn('缺失或过期',reasons(self.row,self.rule)[0])

    def test_retry_does_not_refresh_observation_or_reuse_failed_payload(self):
        snap, _ = self.read(dict(asterOI={'aster:BULLAUSDT':self.value}))
        with patch('advanced_rules.urlopen', side_effect=OSError('offline')) as fetch:
            snap.enrich([self.row],self.rule,self.now+29)
            fetch.assert_not_called()
            self.assertEqual(self.row['oi']['left']['time'],self.value['time'])
            snap.enrich([self.row],self.rule,self.now+30)
        self.assertIn('缺失或过期',reasons(self.row,self.rule)[0])
        with patch('advanced_rules.urlopen', return_value=io.BytesIO(json.dumps(dict(asterOI={'aster:BULLAUSDT':self.value})).encode())):
            snap.enrich([self.row],self.rule,self.now+60)
        self.assertEqual(reasons(self.row,self.rule),[])

    def test_no_request_when_aster_is_spot_or_not_limited(self):
        for row,rule in [(dict(self.row,mode='SF',sell='ASTER'),copy.deepcopy(DEFAULT)),
                         (dict(self.row,mode='SS'),self.rule),
                         (self.row,dict(self.rule,exchangeOI={'aster':dict(mode='none',value=None)}))]:
            with patch('advanced_rules.urlopen') as fetch:
                OISnapshot().enrich([row],rule,self.now)
                fetch.assert_not_called()

    def test_other_venues_keep_relay_route(self):
        for ex in ('binance','bybit','bitget','okx','gate','hyperliquid'):
            with patch('advanced_rules.urlopen',return_value=io.BytesIO(b'{"basis":"double-v1","data":{}}')) as fetch:
                self.assertEqual(OISnapshot()._read(ex,self.now),(ex,{}))
            self.assertEqual(fetch.call_args.args[0],f'http://127.0.0.1:8787/api/open-interest?exchange={ex}&basis=double-v1')


if __name__=='__main__':unittest.main()
