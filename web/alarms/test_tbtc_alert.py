import tempfile
import unittest
import json
import time
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

import tbtc_alert as alerts
from store import Store, Conflict


class PriceAlertTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store=Store(temp.name)
        self.addCleanup(self.store.db.close)
        alerts.initialize(self.store)
        for i,profile in enumerate(('alice','bob')):
            self.store.mutate(profile,dict(action='bind',key='synthetic-key-'+profile,label=profile,
                              revision=0,requestId=str(i)*32),{})
            alerts.configure(self.store,profile,dict(target=('1.0026','1.0040')[i],revision=0))

    def test_mint_gap_is_personal_and_decided_on_missing_units(self):
        a=alerts.configure(self.store,'alice',dict(target='1.0026',revision=1,mintThreshold='0.00000001',mintEnabled=True))
        self.assertEqual(a['mintThreshold'],'0.00000001')
        self.assertEqual(alerts.state(self.store,'bob')['mintThreshold'],'10')
        legacy=alerts.configure(self.store,'alice',dict(target='1.0030',revision=a['revision']))
        self.assertEqual(legacy['mintThreshold'],a['mintThreshold'])
        for invalid in ('-1','0','1e3','0.000000001'):
            with self.assertRaises(ValueError):
                alerts.configure(self.store,'alice',dict(target=legacy['target'],revision=legacy['revision'],mintThreshold=invalid))
        record=dict(raw=str(12*10**18),unbackedRaw=str(10**18))
        self.assertFalse(alerts.meets_mint_threshold(record,18,'10'))
        self.assertTrue(alerts.meets_mint_threshold(record,18,'1'))

    def test_backed_mints_are_strictly_per_tx_and_independent_of_shortfall(self):
        config=alerts.configure(self.store,'alice',dict(target=None,revision=1,largeMintEnabled=True))
        self.assertFalse(config['mintEnabled'])
        self.assertEqual(config['largeMintThreshold'],'30')
        with tempfile.TemporaryDirectory() as tmp,patch.object(alerts,'SUPPLY',Path(tmp)/'supply.json'):
            now=int(time.time())+1
            def record(tx,raw,kind='matched'):
                return dict(tx=tx,raw=str(raw),reason='test',time=now,kind=kind)
            rows=[record('a',16*10**8),record('b',16*10**8),record('equal',30*10**8),
                  record('over',30*10**8+1),record('pending',100*10**8,'pending'),
                  record('review',100*10**8,'review')]
            alerts.SUPPLY.write_text(json.dumps(dict(time=now,chains=[dict(name='Sui',stamp=now,ok=True,decimals=8,history=rows)])))
            with patch('time.time',return_value=now+0.5):
                alerts.tick(self.store);alerts.tick(self.store)
                e=self.store.claim()
                self.assertEqual(e['rule_id'],alerts.LARGE_RULE)
                self.assertEqual(json.loads(e['payload'])['tx'],'over')
                self.assertEqual(len(self.store.view('alice')['events']),1)
                self.assertFalse(self.store.view('bob')['events'])
                alerts.configure(self.store,'alice',dict(target=None,revision=config['revision'],largeMintEnabled=False))
                self.assertFalse(self.store.begin_send(e))

    def update_price(self,stamp,value):
        with patch.object(alerts,'sample',return_value=(stamp,Decimal(value))):
            alerts.tick(self.store)

    def test_uses_second_rank_until_both_supporting_quotes_expire(self):
        row=dict(currency="cbBTC",size=1,reverse=False,at=99,rawOut=str(2*10**18),route="best")
        with tempfile.TemporaryDirectory() as d,patch.object(alerts,"SNAPSHOT",Path(d)/"q"):
            def write():alerts.SNAPSHOT.write_text(json.dumps(dict(time=99,quotes=[row])))
            write()
            self.assertIsNone(alerts.sample(100))
            row["second"]=dict(rawOut="1002600000000000000",at=98,validUntil=102,venue="1inch")
            write()
            self.assertEqual(alerts.sample(100),("1inch:98",Decimal("1.0026")))
            self.assertIsNone(alerts.sample(102))

    def test_personal_target_and_recovery(self):
        for stamp in ('1','1','2','3'):
            self.update_price(stamp,'1.0026')
        events=self.store.view('alice')['events']
        self.assertEqual(len(events),1)
        self.assertFalse(self.store.view('bob')['events'])
        event=self.store.claim()
        with patch.object(alerts,'sample',return_value=('4',Decimal('1.0026'))):
            self.assertTrue(self.store.begin_send(event))
        self.store.finish(event,'accepted')
        self.update_price('4','1.00259999999')
        self.update_price('5','1.003')
        self.update_price('6','1.003')
        self.assertEqual(len(self.store.view('alice')['events']),2)
        with self.assertRaises(Conflict):
            alerts.configure(self.store,'alice',dict(target=None,revision=0))
        alerts.configure(self.store,'alice',dict(target=None,revision=1))
        self.assertIsNone(self.store.claim())
        self.assertEqual(alerts.state(self.store,'bob')['target'],'1.0040')

    def test_expired_quote_cannot_be_sent(self):
        self.update_price('1','1.0027')
        self.update_price('2','1.0027')
        event=self.store.claim()
        with patch.object(alerts,'sample',return_value=None):
            self.assertFalse(self.store.begin_send(event))

    def test_channels_preserve_target_and_cancel_only_bark(self):
        def update(page,bark):
            return alerts.configure(self.store,'alice',dict(target='1.0026',pageEnabled=page,
              barkEnabled=bark,revision=alerts.state(self.store,'alice')['revision']))
        self.update_price('1','1.0026')
        update(False,True)
        self.update_price('2','1.0026')
        event=self.store.claim()
        self.assertEqual(event['profile'],'alice')
        result=update(False,False)
        self.assertEqual(result['target'],'1.0026')
        with patch.object(alerts,'sample',return_value=('3',Decimal('1.0026'))):
            self.assertFalse(self.store.begin_send(event))
        update(True,False)
        self.update_price('4','1.0026')
        self.update_price('5','1.0026')
        self.assertIsNone(self.store.claim())
        self.assertTrue(alerts.state(self.store,'bob')['barkEnabled'])

    def test_upgrade_preserves_rule_and_restarts_confirmation_on_new_rank(self):
        with self.store.db:
            self.store.db.execute('DROP TABLE tbtc_price_alerts')
            self.store.db.execute('CREATE TABLE tbtc_price_alerts(profile TEXT PRIMARY KEY,target TEXT,revision INTEGER,last_sample TEXT,hits INTEGER DEFAULT 0,fired INTEGER DEFAULT 0)')
            self.store.db.execute("INSERT INTO tbtc_price_alerts VALUES('alice','1.0035',12,'kyber:123',2,1)")
        alerts.initialize(self.store)
        alerts.initialize(self.store)
        result=alerts.state(self.store,'alice')
        self.assertEqual((result['target'],result['revision'],result['pageEnabled'],result['barkEnabled']),('1.0035',12,True,True))
        self.assertEqual(self.store.db.execute('SELECT fired FROM tbtc_price_alerts').fetchone()[0],0)

    def test_mint_push_opt_in_is_independent_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(alerts,'SUPPLY',Path(directory)/'supply.json'):
            cfg=alerts.configure(self.store,'alice',dict(target=None,pageEnabled=False,barkEnabled=False,mintEnabled=True,revision=1))
            self.assertTrue(cfg['mintEnabled'])
            ts=time.time()
            record=dict(kind='review',time=int(ts)-60,flaggedAt=ts,tx='tx1',raw='1000300001',reason='归集不符')
            def write(rows,ok=True):
                alerts.SUPPLY.write_text(json.dumps(dict(time=int(ts),chains=[dict(name='Sui',ok=ok,stamp=int(ts),decimals=8,history=rows)])))
                alerts.read_mints.cache_clear()
            write([dict(record,tx='old',flaggedAt=ts-600),dict(record,tx='pending',kind='pending'),
                   dict(record,tx=None),dict(record,tx='matched',kind='matched'),record])
            alerts.tick(self.store);alerts.tick(self.store)
            self.assertFalse(self.store.view('bob')['events'])
            self.assertEqual(len(self.store.view('alice')['events']),1)
            event=self.store.claim()
            self.assertIn('10.00300001 tBTC',json.loads(event['payload'])['body'])
            self.assertEqual(event['rule_id'],'tbtc-mint')
            self.assertTrue(self.store.begin_send(event))
            self.store.finish(event,'accepted')
            # Older price-setting clients omit the new field.
            alerts.configure(self.store,'alice',dict(target='1.0020',revision=cfg['revision']))
            self.assertTrue(alerts.state(self.store,'alice')['mintEnabled'])
            write([dict(record,tx='tx2')]);alerts.tick(self.store);event=self.store.claim()
            write([]);self.assertFalse(self.store.begin_send(event))
            write([dict(record,tx='tx3')]);alerts.tick(self.store);event=self.store.claim()
            alerts.configure(self.store,'alice',dict(target='1.0020',mintEnabled=False,revision=3))
            self.assertFalse(self.store.begin_send(event))
            alerts.initialize(self.store)
            cfg=alerts.configure(self.store,'alice',dict(target='1.0020',mintEnabled=True,revision=4))
            write([dict(record,flaggedAt=time.time())]);alerts.tick(self.store)
            self.assertIsNone(self.store.claim())
