import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from delivery import fingerprint
from live import Live
from live_test import message
from profiles import Profiles
from server import BASE, ORIGIN, handler


def subscription(name):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return dict(endpoint='https://fixture.push.apple.com/'+name, keys=dict(p256dh=encode(key), auth=encode(b'0'*16)))


class ProfilesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.config = self.root/'config.json'
        self.config.write_text(json.dumps(dict(pairCode='12345678', expiresAt=0, publicKey='fixture')))
        self.sent = []
        self.sender = lambda sub,payload: self.sent.append((sub['endpoint'], copy.deepcopy(payload))) or 201
        legacy = Live(self.root/'state', self.config, self.sender)
        self.old_token = legacy.pair('12345678')
        legacy.state['seq'] = 42
        legacy.state['live']['settings'].update(rows=2, min_percent=.3, excluded_coins=['OLD'])
        legacy.state['live']['revision'] = 7
        legacy.state['live']['pending'] = ['existing-pending']
        legacy.state['subscription'] = subscription('original')
        legacy.receipt(dict(seq=42, stage='display-requested'))
        self.before = copy.deepcopy(legacy.state)
        self.app = Profiles(self.root/'state', self.config, self.sender)
        self.old = self.app.resolve(self.old_token)

    def create(self, n=1):
        result = self.app.create_code(f'{n:032x}')
        return result, self.app.resolve(result['token'])

    def feed(self, rows, now):
        return dict(sourceConnected=True, updatedAt=datetime.fromtimestamp(now, timezone.utc).isoformat(), messages=rows)

    def test_legacy_state_and_token_remain_exact_and_restart_safe(self):
        self.assertEqual(self.old.state, self.before)
        self.assertEqual(self.app.pair('12345678'), self.old_token)
        self.assertEqual(self.old.path, self.root/'state/state.json')
        after = Profiles(self.root/'state', self.config, self.sender)
        self.assertEqual(after.resolve(self.old_token).state, self.before)
        self.assertFalse(self.sent)

    def test_creation_fresh_defaults_unique_idempotent_and_persistent(self):
        result, account = self.create()
        self.assertEqual(result, self.app.create_code('0'*31+'1'))
        self.assertNotEqual(result['token'], self.old_token)
        self.assertNotEqual(result['pushCode'], '12345678')
        self.assertRegex(result['pushCode'], r'^\d{8}$')
        self.assertEqual(account.state['seq'], 0)
        self.assertEqual(account.state['live']['settings']['rows'], 4)
        self.assertEqual(account.state['live']['pending'], [])
        self.assertNotIn('subscription', account.state)
        self.assertEqual(self.old.state, self.before)
        after = Profiles(self.root/'state', self.config, self.sender)
        self.assertEqual(after.pair(result['pushCode']), result['token'])
        self.assertEqual(after.create_code('0'*31+'1'), result)

    def test_creation_failure_does_not_publish_partial_account(self):
        with patch.object(self.app, 'save_registry', side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.create()
        self.assertEqual(len(self.app.accounts), 1)
        self.assertEqual(self.old.state, self.before)
        self.assertEqual(len(Profiles(self.root/'state', self.config).accounts), 1)

    def test_concurrent_create_retry_produces_one_plan_and_shared_vapid_cache(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(self.app.create_code, ['f'*32]*4))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(self.app.accounts), 2)
        account = self.app.resolve(results[0]['token'])
        self.assertEqual(account.vapid_directory, self.old.vapid_directory)
        self.assertIs(account.vapid_lock, self.old.vapid_lock)
        account.configure(dict(revision=0, settings=dict(account.state['live']['settings'], rows=3, min_percent=.75)))
        restarted = Profiles(self.root/'state', self.config, self.sender)
        self.assertEqual(restarted.resolve(results[0]['token']).state['live']['settings'], account.state['live']['settings'])
        self.assertEqual(restarted.resolve(self.old_token).state, self.before)

    def test_settings_revision_queue_receipts_device_and_stop_isolated(self):
        _, other = self.create()
        state = copy.deepcopy(self.old.state)
        other.configure(dict(revision=0, settings=dict(other.state['live']['settings'], rows=1, excluded_coins=['BTC'])))
        other.receipt(dict(seq=1, stage='push-received'))
        other.device_status(dict(permission='default', subscriptionFingerprint=None))
        other.stop()
        self.assertEqual(self.old.state, state)
        self.assertEqual(other.state['live']['revision'], 2)
        with self.assertRaises(ValueError): other.configure(dict(revision=7, settings=other.state['live']['settings']))
        self.assertEqual(self.old.state, state)

    def test_delivery_filters_intervals_and_failures_are_independent(self):
        _, a = self.create(1)
        _, b = self.create(2)
        a.subscribe(subscription('a')); b.subscribe(subscription('b'))
        a.configure(dict(revision=0, settings=dict(a.state['live']['settings'], excluded_coins=['ETH'], notify_interval_seconds=30)))
        b.configure(dict(revision=0, settings=dict(b.state['live']['settings'], excluded_coins=['BTC'], notify_interval_seconds=60)))
        now = time.time()+1
        feed = self.feed([message(1, now, coin='BTC'), message(2, now, coin='ETH')], now)
        a.tick(feed, now); b.tick(feed, now)
        self.assertEqual(len(self.sent), 2)
        self.assertTrue(self.sent[0][1]['rows'][0].endswith('BTC'))
        self.assertTrue(self.sent[1][1]['rows'][0].endswith('ETH'))
        self.assertEqual([x[1]['seq'] for x in self.sent], [1, 1])
        feed = self.feed([message(3, now+31, coin='BTC', percent='+0.49%'), message(4, now+31, coin='ETH', percent='+0.49%')], now+31)
        a.tick(feed, now+31); b.tick(feed, now+31)
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(len(b.state['live']['pending']), 1)
        class Limited(Exception):
            response = type('Response', (), dict(status_code=429))()
        a.sender = lambda *args: (_ for _ in ()).throw(Limited())
        feed = self.feed([message(5, now+62, coin='BTC', percent='+0.59%')], now+62)
        a.tick(feed, now+62); b.tick(feed, now+62)
        self.assertGreater(a.state['live']['retryAt'], now+62)
        self.assertEqual(b.state['live']['failures'], 0)
        self.assertEqual(b.state['seq'], 2)
        self.assertEqual(self.old.state, self.before)

    def test_new_plan_never_queues_pre_creation_history(self):
        _, a = self.create()
        a.subscribe(subscription('new'))
        now = time.time()
        a.tick(self.feed([message(1, now-60)], now), now)
        self.assertEqual(a.state['live']['pending'], [])
        self.assertFalse(self.sent)

    def test_duplicate_device_rejected_without_altering_either_plan(self):
        _, a = self.create()
        sub = self.old.state['subscription']
        before = copy.deepcopy(a.state)
        with self.assertRaises(ValueError): a.subscribe(sub)
        with self.assertRaises(ValueError): a.repair_subscription(sub, None)
        with self.assertRaises(ValueError): a.device_status(dict(permission='granted', subscriptionFingerprint=fingerprint(sub)))
        changed_keys = subscription('original')
        with self.assertRaises(ValueError): a.repair_subscription(changed_keys, None)
        self.assertEqual(a.state, before)
        self.assertEqual(self.old.state, self.before)
        replacement = subscription('replacement')
        self.old.repair_subscription(replacement, fingerprint(sub))
        self.assertEqual(self.old.state['subscription'], replacement)

    def test_slow_or_broken_sender_does_not_block_another_plan(self):
        _, a = self.create(1); _, b = self.create(2)
        a.subscribe(subscription('slow')); b.subscribe(subscription('fast'))
        started, release, delivered = threading.Event(), threading.Event(), threading.Event()
        def slow(*args):
            started.set()
            release.wait(3)
            raise OSError('synthetic-private-error')
        a.sender = slow
        b.sender = lambda *args: delivered.set() or 201
        now = time.time()+1
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = {}
            try:
                self.app.dispatch(pool, pending, self.feed([message(1, now)], now), now)
                self.assertTrue(started.wait(1))
                self.assertTrue(delivered.wait(1))
                self.assertIs(self.app.resolve(self.old_token), self.old)
                prior = pending[a.profile_id]
                self.app.dispatch(pool, pending, self.feed([], now), now)
                self.assertIs(pending[a.profile_id], prior)
            finally: release.set()
        self.assertNotIn('synthetic-private-error', json.dumps(a.public_status()))

    def test_transfer_preserves_plans_and_routes_only_target_after_device_ack(self):
        created, target = self.create()
        sub = self.old.state['subscription']
        request = dict(targetToken=created['token'], subscription=sub, requestId='b'*32)
        settings = copy.deepcopy(self.old.state['live'])
        moved = self.app.transfer_subscription(self.old, request)
        self.assertEqual(moved['profileId'], target.profile_id)
        self.assertNotIn('subscription', self.old.state)
        self.assertEqual(self.old.state['live'], settings)
        self.assertEqual(self.old.state['seq'], 42)
        self.assertEqual(target.state['live']['settings']['rows'], 4)
        self.assertEqual(target.state['subscription'], sub)
        self.assertFalse(target.state['device']['matches'])
        # A lost HTTP response can safely retry the exact operation.
        self.app.transfer_subscription(self.old, request)
        now = time.time()+1
        feed = self.feed([message(8, now)], now)
        self.old.tick(feed, now); target.tick(feed, now)
        self.assertFalse(self.sent)
        target.device_status(dict(permission='granted', subscriptionFingerprint=fingerprint(sub), version='radar-delivery-v6'))
        target.tick(feed, now)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][1]['profile'], target.profile_id)
        self.assertEqual(self.sent[0][1]['seq'], 1)
        self.assertNotIn('web_push', self.sent[0][1])
        self.app.transfer_subscription(target, dict(targetToken=self.old_token, subscription=sub, requestId='c'*32))
        self.assertEqual(self.old.state['subscription'], sub)
        self.assertNotIn('subscription', target.state)
        with self.assertRaises(ValueError): self.app.transfer_subscription(self.old, request)

    def test_transfer_rejects_occupied_target_wrong_device_and_bad_authorization(self):
        created, target = self.create()
        target.subscribe(subscription('other-phone'))
        before = copy.deepcopy(target.state)
        request = dict(targetToken=created['token'], subscription=self.old.state['subscription'], requestId='b'*32)
        with self.assertRaisesRegex(ValueError, '另一台手机'): self.app.transfer_subscription(self.old, request)
        self.assertEqual(target.state, before); self.assertEqual(self.old.state, self.before)
        with self.assertRaises(ValueError): self.app.transfer_subscription(self.old, dict(request, subscription=subscription('forged')))
        with self.assertRaises(ValueError): self.app.transfer_subscription(self.old, dict(request, targetToken='invalid'))
        self.assertFalse(self.app.transfer_path.exists())

    def test_interrupted_transfer_recovers_without_rewinding_settings_or_sequence(self):
        created, target = self.create()
        sub = self.old.state['subscription']
        request = dict(targetToken=created['token'], subscription=sub, requestId='d'*32)
        original = self.app.write_private
        def fail_state(path, value):
            if path.name == 'state.json': raise OSError('disk interrupted')
            return original(path, value)
        with patch.object(self.app, 'write_private', side_effect=fail_state):
            with self.assertRaises(OSError): self.app.transfer_subscription(self.old, request)
        self.assertTrue(self.app.transfer_path.exists())
        now = time.time()+1
        self.old.tick(self.feed([message(1, now)], now), now)
        self.assertFalse(self.sent)
        restarted = Profiles(self.root/'state', self.config, self.sender)
        self.assertFalse(restarted.transfer_path.exists())
        old, new = restarted.resolve(self.old_token), restarted.resolve(created['token'])
        self.assertNotIn('subscription', old.state)
        self.assertEqual(new.state['subscription'], sub)
        self.assertEqual(old.state['seq'], 42)
        self.assertEqual(old.state['live']['settings'], self.before['live']['settings'])
        restarted.transfer_subscription(old, request)

    def test_pair_throttling_scoped_to_client_and_creation_retries_survive_limit(self):
        for _ in range(10):
            with self.assertRaises(ValueError): self.app.pair('00000000', client='bad-client')
        with self.assertRaises(ValueError): self.app.pair('12345678', client='bad-client')
        self.assertEqual(self.app.pair('12345678', client='good-client'), self.old_token)
        result, _ = self.create()
        self.app.MAX_CREATES_PER_HOUR = 1
        with self.assertRaises(ValueError): self.create(2)
        self.assertEqual(self.app.create_code('0'*31+'1'), result)
        self.assertEqual(self.old.state, self.before)

    def test_http_routes_use_only_bearer_account_and_create_is_available_unpaired(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def request(route, token='', data=None, origin=ORIGIN):
            connection = HTTPConnection(*server.server_address)
            headers = {'Authorization':'Bearer '+token, 'Origin':origin, 'Content-Type':'application/json'}
            connection.request('GET' if data is None else 'POST', BASE+'api/'+route,
                               body=None if data is None else json.dumps(data), headers=headers)
            response = connection.getresponse(); body = json.loads(response.read())
            self.assertEqual(response.getheader('Cache-Control'), 'no-store')
            status = response.status; connection.close(); return status, body
        try:
            self.assertEqual(request('create-code', data={'requestId':'a'*32}, origin='https://evil.invalid')[0], 403)
            status, created = request('create-code', data={'requestId':'a'*32})
            self.assertEqual(status, 200)
            token = created['token']
            self.assertEqual(request('binding')[0], 401)
            self.assertEqual(request('binding', 'wrong')[0], 401)
            self.assertEqual(request('binding', self.old_token)[1], {'pushCode':'12345678'})
            self.assertEqual(request('binding', token)[1], {'pushCode':created['pushCode']})
            status, current = request('status', token)
            self.assertEqual(current['revision'], 0)
            current['settings']['rows'] = 1
            status, _ = request('settings', token, dict(revision=0, settings=current['settings'], code='12345678'))
            self.assertEqual(status, 200)
            self.assertEqual(request('status', self.old_token)[1]['revision'], 7)
            self.assertEqual(request('receipt-batch', token, {'records':[{'seq':3,'stage':'push-received'}]})[0], 200)
            self.assertEqual(request('stop', token, {})[0], 200)
            self.assertEqual(self.old.state, self.before)
            self.assertEqual(request('pair', data={'code':created['pushCode']})[1]['token'], token)
            self.assertIsNone(self.app.resolve('非英文'))
            public = json.dumps(request('status', token)[1])
            self.assertNotIn(self.old_token, public)
            self.assertNotIn('original', public)
            self.assertFalse(self.sent)
            self.assertEqual(request('switch-subscription', data={})[0], 401)
            self.assertEqual(request('switch-subscription', self.old_token, dict(targetToken=token,
                subscription=self.old.state['subscription'], requestId='e'*32))[0], 200)
            self.assertFalse(request('status', self.old_token)[1]['subscribed'])
            self.assertTrue(request('status', token)[1]['subscribed'])
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
