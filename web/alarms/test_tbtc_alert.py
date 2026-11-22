import tempfile
import unittest
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

    def update_price(self,stamp,value):
        with patch.object(alerts,'sample',return_value=(stamp,Decimal(value))):
            alerts.tick(self.store)

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
