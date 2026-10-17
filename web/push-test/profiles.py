"""Independent push plans. The legacy owner stays at the original state path."""
import copy
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from delivery import fingerprint
from live import Live
from server import validate_subscription


class Profile(Live):
    def __init__(self, manager, key, directory, config, sender):
        self.manager = manager
        self.profile_id = key
        self.vapid_directory = manager.directory
        self.vapid_lock = manager.vapid_lock
        super().__init__(directory, None, sender, config=config)

    def subscribe(self, value):
        sub = validate_subscription(value)
        with self.lock, self.manager.lock:
            self.manager.check_subscription(self, sub)
            return super().subscribe(sub)

    def repair_subscription(self, value, expected):
        sub = validate_subscription(value)
        with self.lock, self.manager.lock:
            self.manager.check_subscription(self, sub)
            return super().repair_subscription(sub, expected)

    def device_status(self, value):
        with self.lock, self.manager.lock:
            fp = value.get('subscriptionFingerprint')
            if fp:
                self.manager.check_fingerprint(self, fp)
            return super().device_status(value)


class Profiles:
    MAX_PROFILES = 100
    MAX_CREATES_PER_HOUR = 20

    def __init__(self, state_dir, config_path, sender=None):
        self.directory = Path(state_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory/'profiles.json'
        self.config = json.loads(Path(config_path).read_text())
        self.lock = threading.RLock()
        self.vapid_lock = threading.RLock()
        self.sender = sender
        self.pair_attempts = {}
        # No renaming/copying the old state: token, subscription, sequence, queues,
        # settings, receipts and VAPID cache keep their exact original locations.
        self.accounts = {'legacy': Profile(self, 'legacy', self.directory, self.config, sender)}
        self.registry = json.loads(self.path.read_text()) if self.path.exists() else {'version': 1, 'profiles': []}
        if self.registry.get('version') != 1 or not isinstance(self.registry.get('profiles'), list):
            raise ValueError('invalid_profile_registry')
        codes = {self.config['pairCode']}
        requests = set()
        for item in self.registry['profiles']:
            key, code = item['id'], item['code']
            if (not re.fullmatch('[a-f0-9]{32}', key) or not re.fullmatch('[0-9]{8}', code)
                    or code in codes or key in self.accounts or item['requestHash'] in requests):
                raise ValueError('invalid_profile_registry')
            codes.add(code)
            requests.add(item['requestHash'])
            directory = self.directory/'profiles'/key
            if not (directory/'state.json').is_file():
                raise ValueError('missing_profile_state')
            account = Profile(self, key, directory, dict(self.config, pairCode=code), sender)
            if not account.state.get('token'):
                raise ValueError('missing_profile_token')
            self.accounts[key] = account
        tokens = [a.state.get('token') for a in self.accounts.values() if a.state.get('token')]
        if len(tokens) != len(set(tokens)):
            raise ValueError('duplicate_profile_token')
        if not self.path.exists():
            self.save_registry(self.registry)

    def save_registry(self, value):
        temp = self.path.with_suffix('.next')
        temp.write_text(json.dumps(value), encoding='utf-8')
        temp.chmod(0o600)
        os.replace(temp, self.path)

    def resolve(self, token):
        if not isinstance(token, str) or not token.isascii() or len(token) > 100:
            return None
        with self.lock:
            return next((a for a in self.accounts.values() if a.authenticate(token)), None)

    def pair(self, code, client='local'):
        with self.lock:
            now = time.time()
            self.pair_attempts = {k:v for k,v in self.pair_attempts.items() if v[-1] > now-300}
            attempts = [at for at in self.pair_attempts.get(client, []) if at > now-300]
            if len(attempts) >= 10 or client not in self.pair_attempts and len(self.pair_attempts) >= 10000:
                raise ValueError('尝试过多，请五分钟后再试')
            self.pair_attempts[client] = attempts+[now]
            if not isinstance(code, str) or not re.fullmatch('[0-9]{8}', code):
                raise ValueError('请输入有效的 8 位推送码')
            account = next((a for a in self.accounts.values() if hmac.compare_digest(a.config['pairCode'], code)), None)
            if account is None:
                raise ValueError('推送码不正确')
        # Never hold the registry lock while waiting on an account sending push.
        return account.pair(code)

    @staticmethod
    def client_key(headers, peer):
        # The HTTP listener is loopback-only behind the existing Cloudflare/nginx
        # access policy; Cloudflare overwrites this header with the visitor IP.
        value = headers.get('CF-Connecting-IP', peer)
        try:
            value = str(ipaddress.ip_address(value))
        except ValueError:
            value = peer
        return hashlib.sha256(value.encode()).hexdigest()

    def create_code(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch('[a-f0-9]{32}', request_id):
            raise ValueError('创建请求无效，请重新打开设置')
        digest = hashlib.sha256(request_id.encode()).hexdigest()
        with self.lock:
            for item in self.registry['profiles']:
                if hmac.compare_digest(item['requestHash'], digest):
                    account = self.accounts[item['id']]
                    return {'pushCode': item['code'], 'token': account.state['token']}
            now = time.time()
            if len(self.accounts) >= self.MAX_PROFILES:
                raise ValueError('推送方案数量已达上限，请联系管理员')
            if sum(item['createdAt'] > now-3600 for item in self.registry['profiles']) >= self.MAX_CREATES_PER_HOUR:
                raise ValueError('新建推送码过于频繁，请稍后再试')
            existing = {a.config['pairCode'] for a in self.accounts.values()}
            while True:
                code = f'{secrets.randbelow(100000000):08d}'
                if code not in existing:
                    break
            key = secrets.token_hex(16)
            account = Profile(self, key, self.directory/'profiles'/key, dict(self.config, pairCode=code), self.sender)
            account.state['token'] = secrets.token_urlsafe(32)
            # A new plan starts fresh; never inherit the old plan's history/queue.
            account.state['live']['acceptAfter'] = now
            account.save()
            candidate = copy.deepcopy(self.registry)
            candidate['profiles'].append(dict(id=key, code=code, createdAt=now, requestHash=digest))
            self.save_registry(candidate)
            self.registry = candidate
            self.accounts[key] = account
            return {'pushCode': code, 'token': account.state['token']}

    def check_fingerprint(self, owner, fp):
        for account in self.accounts.values():
            if account is not owner and fingerprint(account.state.get('subscription')) == fp:
                raise ValueError('本机通知已绑定其他推送码，请使用原推送码；新码请在另一台手机开启通知。')

    def check_subscription(self, owner, sub):
        # Endpoint uniqueness also catches a changed key tuple for the same device.
        for account in self.accounts.values():
            other = account.state.get('subscription')
            if account is not owner and other and other['endpoint'] == sub['endpoint']:
                raise ValueError('本机通知已绑定其他推送码，请使用原推送码；新码请在另一台手机开启通知。')

    @staticmethod
    def tick_account(account, feed, now):
        try:
            account.tick(feed, max(now, time.time()))
        except Exception as exc:
            # A malformed/failed plan never stops other plans; no secrets in status.
            account.source = dict(connected=False, checkedAt=now, error=type(exc).__name__)

    def dispatch(self, executor, pending, feed, now):
        with self.lock:
            accounts = list(self.accounts.items())
        for key, account in accounts:
            if key not in pending or pending[key].done():
                pending[key] = executor.submit(self.tick_account, account, feed, now)

    def run_feed(self, path):
        pending = {}
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix='push-plan') as executor:
            while True:
                try:
                    source = Path(path)
                    if source.stat().st_size > 2*1024*1024:
                        raise ValueError('feed_oversize')
                    feed = json.loads(source.read_text(encoding='utf-8'))
                    if not isinstance(feed, dict):
                        raise ValueError('feed_schema')
                    self.dispatch(executor, pending, feed, time.time())
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    with self.lock:
                        for account in self.accounts.values():
                            account.source = dict(connected=False, checkedAt=time.time(), error=type(exc).__name__)
                time.sleep(3)
