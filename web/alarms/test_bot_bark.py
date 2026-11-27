import json
import secrets
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import bot_bark
import server
import site_tasks
from store import Store


class BotBarkTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        mock = patch.object(site_tasks, 'ROOT', self.root)
        mock.start()
        self.addCleanup(mock.stop)
        self.store = Store(temp.name)
        self.addCleanup(self.store.db.close)
        bot_bark.setup(self.store)
        for plan in ('a', 'b'):
            self.store.mutate(plan, dict(action='bind', requestId=secrets.token_hex(16),
                revision=self.store.view(plan)['revision'], key='synthetic_device_'+plan, label=plan), {})
        (self.root / 'bot-bark').touch()

    def queue(self, ident):
        now = time.time()
        row = dict(id=ident, senderType='bot', title='test', body='sample',
                   sentAt=datetime.fromtimestamp(now, timezone.utc).isoformat())
        rows = bot_bark.candidates(dict(sourceConnected=True, messages=[row]), 0, now+.01)
        self.assertEqual(len(rows), 1)
        self.assertFalse(bot_bark.candidates(dict(sourceConnected=True, messages=[row], pinned=row), 0, now))
        decision = dict(action='allow', fingerprint=rows[0][1])
        policy = dict(desktopEnabled=True, decisions={ident:decision})
        for _ in range(2):
            bot_bark.enqueue(self.store, 'a', rows, policy, now)
        bot_bark.enqueue(self.store, 'b', rows, dict(policy, desktopEnabled=False), now)
        bot_bark.enqueue(self.store, 'b', rows, dict(policy, decisions={ident:dict(decision,action='mute')}), now)

    def test_modes_and_delivery_isolation(self):
        for mode in ('active', 'critical'):
            if mode == 'critical':
                (self.root / 'bot-bark.mode').write_text(mode)
            self.queue(mode)
            event = self.store.claim()
            self.assertEqual(event['profile'], 'a')
            with patch.object(server, 'build_opener') as make:
                make.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"code":200}'
                server.send_event(self.store, event)
                req = make.return_value.open.call_args.args[0]
                body = json.loads(req.data)
                self.assertEqual(body['level'], mode)
                self.assertEqual(body['device_key'], 'synthetic_device_a')
                self.assertEqual('call' in body, mode == 'critical')
                self.assertEqual('volume' in body, mode == 'critical')
            self.assertIsNone(self.store.claim())

    def test_disable_before_dispatch(self):
        self.queue('pending')
        (self.root/'bot-bark.off').touch()
        with patch.object(server, 'build_opener') as make:
            server.send_event(self.store, self.store.claim())
            make.assert_not_called()
