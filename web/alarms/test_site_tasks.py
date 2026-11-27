import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import site_tasks
import tbtc_alert


class GlobalTaskTests(unittest.TestCase):
    def test_paused_inputs_do_not_open_snapshots_or_query_the_ledger(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(site_tasks, 'ROOT', Path(directory)):
            root = Path(directory)
            for name in ('alarm-price', 'alarm-sale', 'alarm-mint', 'alarm-deposit'):
                (root / (name + '.off')).touch()
            store = Mock()
            tbtc_alert.tick_prices(store)
            tbtc_alert.enqueue_sales(store, time.time(), batch='a' * 32)
            tbtc_alert.enqueue_mints(store, time.time())
            tbtc_alert.enqueue_deposits(store, time.time())
            self.assertEqual(store.mock_calls, [])
            self.assertEqual(site_tasks.since(tbtc_alert.SALE_RULE), float('inf'))
            (root / 'alarm-sale').write_text('resumed')
            (root / 'alarm-sale.off').unlink()
            self.assertGreater(site_tasks.since(tbtc_alert.SALE_RULE), time.time() - 3)
            self.assertEqual(site_tasks.since(tbtc_alert.RULE), float('inf'))

