import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from pushward_radar import APIError, Bridge, parse_message, render

NOW = 1800000000


def message(n=1, at=NOW, title='BTC | FF | V2收敛 | R0 +0.39%', body='买 OKX 永续 → 卖 Bitget 永续\n净收益0.13% · 盘口差+0.21%'):
    return dict(id=f'{n:064x}', senderType='bot', sentAt=datetime.fromtimestamp(at, timezone.utc).isoformat(), title=title, body=body)


def feed(messages, at=NOW, connected=True):
    return dict(messages=messages, sourceConnected=connected,
                updatedAt=datetime.fromtimestamp(at, timezone.utc).isoformat())


class FakeClient:
    def __init__(self):
        self.activity = dict(state='ongoing', content=dict(template='log', lines=[{'text':'example'}]))
        self.calls = []
        self.fail = None

    def call(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if self.fail and self.fail[0] == path and method != 'GET':
            raise self.fail[1]
        if path == '/auth/me':
            return dict(live_activity_updates_used=36, live_activity_updates_limit=250)
        if path == '/notifications':
            return dict(pushed=True, delivery='all')
        if method == 'PATCH':
            self.activity['state'] = payload.get('state', self.activity['state'])
            for k,v in payload.get('content', {}).items():
                if v is None:
                    self.activity['content'].pop(k, None)
                else:
                    self.activity['content'][k] = copy.deepcopy(v)
        return copy.deepcopy(self.activity)


class ParserTests(unittest.TestCase):
    def test_title_rank_percentage_only(self):
        r = parse_message(message(), NOW)
        self.assertEqual((r['value'], r['rank'], r['mode'], r['buy'], r['sell']), ('+0.39%', 'R0', 'FF', 'OKX', 'BITGET'))

    def test_fullwidth_markdown_and_negative(self):
        r = parse_message(message(title='**ZEREBRO｜SF｜V2收敛｜R1 -0.230%**', body='买 GATE 现货 → 卖 ASTER 永续'), NOW)
        self.assertEqual((r['coin'], r['mode'], r['rank'], r['value']), ('ZEREBRO', 'SF', 'R1', '-0.230%'))

    def test_no_funding_or_net_fallback(self):
        for title in ['BTC | FF | R0', 'BTC | FF | R2 +0.8%', 'BTC | FF | R10 +0.8%', 'BTC | FF | R0 净收益 +0.8%']:
            with self.subTest(title=title):
                self.assertIsNone(parse_message(message(title=title), NOW))

    def test_aggregation_ambiguous_is_rejected(self):
        self.assertIsNone(parse_message(message(title='强信号聚集 | BTC | 3组', body='R1 | SF | 买 GATE → 卖 ASTER\n净均 +0.23%'), NOW))
        self.assertIsNone(parse_message(message(title='BTC | FF | R0 +0.3% R1 +0.5%'), NOW))
        self.assertIsNone(parse_message(message(body='买 OKX → 卖 Bitget\n买 Gate → 卖 Bybit'), NOW))

    def test_source_and_time(self):
        for changes in [dict(senderType='user'), dict(id='invalid'), dict(sentAt='bad'), dict(sentAt='2026-01-01T00:00:00')]:
            self.assertIsNone(parse_message(dict(message(), **changes), NOW))
        self.assertIsNone(parse_message(message(at=NOW-1801), NOW))
        self.assertIsNone(parse_message(message(at=NOW+31), NOW))

    def test_mode_and_unknown_exchange_fail_closed(self):
        for body in ['买 OKX 现货 → 卖 Bitget 永续', '买 FAKE → 卖 Bitget', '买 OKX → 卖 OKX']:
            self.assertIsNone(parse_message(message(body=body), NOW))
        self.assertEqual(parse_message(message(body='买 Hyperliquid 永续 → 卖 Bitget 永续'), NOW)['buy'], 'HL')

    def test_same_exchange_spot_future_is_valid(self):
        r = parse_message(message(title='SUPER｜FS｜V2收敛｜R0 +0.43%', body='买 Bitget 永续 → 卖 Bitget 现货\n均值：净收益0.181%｜盘口差+0.246%'), NOW)
        self.assertEqual((r['buy'], r['sell'], r['mode'], r['value']), ('BITGET', 'BITGET', 'FS', '+0.43%'))
        self.assertIsNotNone(parse_message(message(title='SUPER | SF | R1 +0.43%', body='买 Bitget 现货 → 卖 Bitget 永续'), NOW))


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = FakeClient()
        self.bridge = Bridge(self.client, self.temp.name, 'unit-test', NOW)

    def tearDown(self):
        self.temp.cleanup()

    def notifications(self):
        return [c for c in self.client.calls if c[0] == 'POST' and c[1] == '/notifications']

    def patches(self):
        return [c for c in self.client.calls if c[0] == 'PATCH']

    def test_six_latest_oldest_first_original_times(self):
        msgs = [message(n=i, at=NOW+i, title=f'COIN{i} | FF | R0 +0.39%') for i in range(1, 9)]
        self.bridge.tick(feed(list(reversed(msgs)), NOW+10), NOW+10)
        rows = self.bridge.s['rows']
        self.assertEqual([r['coin'] for r in rows], ['COIN3','COIN4','COIN5','COIN6','COIN7','COIN8'])
        self.assertEqual([r['at'] for r in rows], list(range(NOW+3, NOW+9)))
        self.assertEqual(len(self.notifications()), 1)
        self.assertIn('8条新消息', self.notifications()[0][2]['title'])

    def test_restart_dedup_and_no_timer_pushes(self):
        self.bridge.tick(feed([message()]), NOW)
        self.bridge = Bridge(self.client, self.temp.name, 'unit-test', NOW+60)
        for t in range(NOW+60, NOW+400, 10):
            self.bridge.tick(feed([message()], t), t)
        self.assertEqual(len(self.notifications()), 1)
        self.assertEqual(len(self.patches()), 1)

    def test_cross_group_duplicate(self):
        self.bridge.tick(feed([message(), message(n=2, at=NOW+1)], NOW+1), NOW+1)
        self.assertEqual(len(self.bridge.s['rows']), 1)
        self.assertEqual(self.bridge.s['counters']['duplicate_content'], 1)

    def test_history_seeds_without_alert_and_old_pin_ignored(self):
        f = feed([message(at=NOW-60)])
        f['pinned'] = message(n=2, at=NOW-3600)
        self.bridge.tick(f, NOW)
        self.assertEqual(len(self.bridge.s['rows']), 1)
        self.assertEqual(len(self.notifications()), 0)

    def test_missing_or_stale_feed_never_generates_signal(self):
        self.bridge.tick(feed([message()], NOW-100), NOW)
        self.assertEqual(self.bridge.s['rows'], [])
        self.assertIn('断线', self.client.activity['content']['lines'][0]['text'])
        self.assertEqual(len(self.notifications()), 0)

    def test_coalescing_and_minimum_interval(self):
        self.bridge.tick(feed([message()]), NOW)
        second = message(n=2, at=NOW+1, title='ETH | FF | R1 +0.41%')
        self.bridge.tick(feed([second], NOW+1), NOW+1)
        self.assertEqual(len(self.patches()), 1)
        self.assertEqual(len(self.notifications()), 1)
        self.bridge.tick(feed([second], NOW+30), NOW+30)
        self.assertEqual(len(self.patches()), 2)
        self.assertEqual(len(self.notifications()), 2)

    def test_activity_quota_does_not_disable_ordinary_notifications(self):
        self.client.fail = ('/activities/unit-test', APIError('quota.exceeded', 3600))
        self.bridge.tick(feed([message()]), NOW)
        self.bridge.tick(feed([message()], NOW+60), NOW+60)
        self.assertEqual(len(self.patches()), 1)
        self.assertEqual(len(self.notifications()), 2)
        self.assertEqual(sum(c[2]['thread_id'] == 'radar-live-status' for c in self.notifications()), 1)
        self.assertEqual(sum(c[2]['thread_id'] == 'radar-live' for c in self.notifications()), 1)
        self.assertEqual(self.bridge.s['update_after'], NOW+3600)

    def test_backoff_error_remains_visible(self):
        self.client.fail = ('/activities/unit-test', APIError('network_or_response', 60, True))
        self.bridge.tick(feed([message()]), NOW)
        self.bridge.tick(feed([message()], NOW+30), NOW+30)
        self.assertEqual(self.bridge.status['activityError'], 'network_or_response')
        self.assertEqual(len(self.patches()), 1)

    def test_reconnect_delivers_recent_new_messages(self):
        self.bridge.tick(feed([], connected=False), NOW)
        self.bridge.tick(feed([message(at=NOW+10)], NOW+40), NOW+40)
        self.assertEqual(len(self.bridge.s['rows']), 1)
        self.assertEqual(len(self.notifications()), 1)
        self.assertTrue(self.bridge.status['sourceConnected'])

    def test_unknown_notification_not_replayed_after_restart(self):
        self.client.fail = ('/notifications', APIError('network_or_response', 60, True))
        self.bridge.tick(feed([message()]), NOW)
        self.assertEqual(self.bridge.s['last_notification']['state'], 'unknown')
        self.client.fail = None
        b = Bridge(self.client, self.temp.name, 'unit-test', NOW+60)
        b.tick(feed([message()], NOW+60), NOW+60)
        self.assertEqual(len(self.notifications()), 1)

    def test_notification_rate_limit_retry_then_expiry(self):
        self.client.fail = ('/notifications', APIError('http_429', 60))
        self.bridge.tick(feed([message()]), NOW)
        self.client.fail = None
        self.bridge.tick(feed([message()], NOW+60), NOW+60)
        self.assertEqual(len(self.notifications()), 2)
        self.assertEqual(self.bridge.s['pending'], [])

    def test_expired_pending_alert_is_not_replayed(self):
        self.client.fail = ('/notifications', APIError('quota.exceeded', 3600))
        self.bridge.tick(feed([message()]), NOW)
        self.client.fail = None
        self.bridge.tick(feed([], NOW+3601), NOW+3601)
        self.assertEqual(len(self.notifications()), 1)
        self.assertEqual(self.bridge.s['pending'], [])

    def test_expired_activity_bootstrap_then_log_same_slug(self):
        self.client.activity['state'] = 'ended'
        self.bridge.tick(feed([message()]), NOW)
        self.assertEqual(self.client.activity['content']['template'], 'generic')
        self.bridge.tick(feed([message()], NOW+30), NOW+30)
        self.assertEqual(self.client.activity['content']['template'], 'log')
        self.assertNotIn('progress', self.client.activity['content'])
        self.assertEqual(len(self.patches()), 2)

    def test_unknown_update_reconciles_without_duplicate_patch(self):
        original = self.client.call
        def lost_response(method, path, payload=None):
            result = original(method, path, payload)
            if method == 'PATCH':
                raise APIError('network_or_response', 60, True)
            return result
        self.client.call = lost_response
        self.bridge.tick(feed([message()]), NOW)
        self.client.call = original
        self.bridge.tick(feed([message()], NOW+60), NOW+60)
        self.assertEqual(len(self.patches()), 1)

    def test_state_has_no_full_body_or_key(self):
        self.bridge.tick(feed([message()]), NOW)
        text = (Path(self.temp.name)/'state.json').read_text()
        self.assertNotIn('净收益', text)
        self.assertNotIn('hlk_', text)
        self.assertNotIn('groupId', text)


if __name__ == '__main__':
    unittest.main()
