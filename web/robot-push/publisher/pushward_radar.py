"""Event-driven, private PushWard consumer of the existing authorized robot feed.

No Feishu connection or writes to the publisher. Only normalized signal fields are
retained. HTTP acceptance is never reported as device delivery confirmation.
"""
import argparse
import hashlib
import json
import os
import re
import signal
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from pushward_settings import DEFAULTS, Store, SettingsServer, matches, validate

API = 'https://api.pushward.app'
EXCHANGES = {'BINANCE': 'BINANCE', 'BITGET': 'BITGET', 'BYBIT': 'BYBIT',
             'OKX': 'OKX', 'OKEX': 'OKX', 'GATE': 'GATE', 'GATE.IO': 'GATE',
             'ASTER': 'ASTER', 'HYPERLIQUID': 'HL', 'HL': 'HL'}
RANK = re.compile(r'(?<![A-Z0-9])R([0-9]{1,24})(?=\s|[+-])(\+(?=\s))?\s*([+-]?\d+(?:\.\d+)?)\s*%(?![\d.])', re.I)
TITLE = re.compile(r'^\s*([A-Z0-9][A-Z0-9._-]{0,23})\s*[|·]\s*(SF|FS|FF)\b', re.I)
DIRECTION = re.compile(r'(?:买入|买|做多)\s*([A-Z][A-Z0-9.]*)\s*(现货|永续|合约)?\s*(?:→|->|⇒)\s*(?:卖出|卖|做空)\s*([A-Z][A-Z0-9.]*)\s*(现货|永续|合约)?', re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def stamp(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return d.timestamp() if d.tzinfo else None
    except (TypeError, ValueError, AttributeError):
        return None


def clean(value):
    return unicodedata.normalize('NFKC', value).replace('**', '').replace('`', '')


def parse_message(message, now):
    if not isinstance(message, dict) or message.get('senderType') != 'bot':
        return None
    mid, title, body = (message.get(k) for k in ('id', 'title', 'body'))
    sent = stamp(message.get('sentAt'))
    if not isinstance(mid, str) or not re.fullmatch(r'[0-9a-f]{64}', mid):
        return None
    if not isinstance(title, str) or not isinstance(body, str) or len(title) > 1024 or len(body) > 16000:
        return None
    if sent is None or sent > now + 30 or now - sent > 1800:
        return None
    title, body = clean(title), clean(body)
    head, ranks, directions = TITLE.search(title), RANK.findall(title), DIRECTION.findall(body)
    # The percentage must follow the R rank in the title. Never substitute net/funding rates.
    if not head or len(ranks) != 1 or len(directions) != 1:
        return None
    coin, mode = head.group(1).upper(), head.group(2).upper()
    buy, buy_kind, sell, sell_kind = directions[0]
    buy, sell = EXCHANGES.get(buy.upper()), EXCHANGES.get(sell.upper())
    if not buy or not sell or (buy == sell and mode == 'FF'):
        return None
    for actual, expected in zip((buy_kind, sell_kind), mode):
        if actual and ('S' if actual == '现货' else 'F') != expected:
            return None
    rank, suffix, value = ranks[0]
    if len(value) > 12:
        return None
    if not value.startswith(('+', '-')):
        value = '+' + value
    fields = dict(coin=coin, mode=mode, buy=buy, sell=sell, rank='R'+str(int(rank))+suffix, value=value+'%')
    return dict(fields, id=mid, at=int(sent), fingerprint=digest(fields))


def render(rows, connected):
    state = None if connected else '消息源断线 · 内容未更新'
    if rows:
        coin_width = max(7, max(len(r['coin']) for r in rows))
        pair_width = max(11, max(len(r['buy']+'→'+r['sell']) for r in rows))
        lines = [dict(text=f"{r['coin']:<{coin_width}} {r['mode']} {r['buy']+'→'+r['sell']:<{pair_width}} {r['rank']} {r['value']}",
                      at=r['at'], level='info') for r in rows]
    else:
        lines = [dict(text='等待符合筛选条件的新消息' if connected else '消息源断线，等待恢复', level='info')]
    return dict(template='log', state=state, icon='waveform.path.ecg',
                accent_color='#00865F', progress=None, lines=lines)


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.pending')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=True, separators=(',', ':'))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class APIError(Exception):
    def __init__(self, code, retry=60, uncertain=False):
        self.code, self.retry, self.uncertain = code, retry, uncertain


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, key):
        if not re.fullmatch(r'hlk_[A-Za-z0-9_-]+', key):
            raise ValueError('invalid_key_file')
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect)

    def call(self, method, path, payload=None):
        raw = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(API+path, data=raw, method=method, headers={
            'Authorization': 'Bearer '+self.key, 'User-Agent': 'RadarPreview/1.0',
            'Accept': 'application/json', 'Content-Type': 'application/merge-patch+json' if method == 'PATCH' else 'application/json'})
        try:
            with self.opener.open(req, timeout=15) as res:
                data = res.read(1024*1024+1)
                if len(data) > 1024*1024:
                    raise APIError('oversize_response', uncertain=method != 'GET')
                result = json.loads(data)
                if not isinstance(result, dict):
                    raise APIError('invalid_response_schema', uncertain=method != 'GET')
                return result
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read(16384))
            except (ValueError, OSError):
                body = {}
            retry = max(30, min(86400*32, (stamp(body.get('reset_at')) or 0)-time.time()))
            if body.get('code') != 'quota.exceeded':
                try:
                    retry = max(30, min(3600, int(e.headers.get('Retry-After', '60'))))
                except ValueError:
                    retry = 60
            code = 'quota.exceeded' if body.get('code') == 'quota.exceeded' else 'http_'+str(e.code)
            raise APIError(code, retry, uncertain=e.code >= 500 and method != 'GET') from None
        except (OSError, ValueError, TimeoutError):
            raise APIError('network_or_response', 60, uncertain=method != 'GET') from None


class Bridge:
    def __init__(self, client, directory, slug, now, min_interval=30):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', slug):
            raise ValueError('invalid_slug')
        self.client, self.directory, self.slug = client, Path(directory), slug
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory/'state.json'
        if self.path.exists():
            self.s = json.loads(self.path.read_text(encoding='utf-8'))
            if self.s.get('version') != 1 or self.s.get('slug') != slug:
                raise ValueError('state_mismatch')
        else:
            self.s = dict(version=1, slug=slug, activated=now, rows=[], seen={}, pending=[],
                          pushed='', last_push=0, notify_after=0, update_after=0,
                          bootstrap_until=0, counters={})
        self.min_interval = max(30, min_interval)
        self.settings = validate(DEFAULTS)
        self.settings_revision = -1
        self.s.setdefault('history', list(self.s['rows']))
        self.remote = None
        self.remote_checked = 0
        self.quota_checked = 0
        self.status_written = 0
        self.connected = False
        self.status = dict(deviceDelivery='unverified', sourceConnected=False)
        if self.s.get('activity_error'):
            self.status['activityError'] = self.s['activity_error']
        self.save()

    def save(self):
        atomic(self.path, self.s)

    def count(self, key, value=1):
        self.s['counters'][key] = self.s['counters'].get(key, 0)+value

    def configure(self, settings, revision):
        if revision == self.settings_revision:
            return
        self.settings = validate(settings)
        self.settings_revision = revision
        self.refresh_selection()
        self.status['settingsRevision'] = revision
        self.status_written = 0
        self.save()

    def refresh_selection(self):
        self.s['rows'] = [r for r in self.s['history'] if matches(r, self.settings)][-self.settings['rows']:]
        self.s['pending'] = [r for r in self.s['pending'] if self.settings['notify_enabled'] and matches(r, self.settings)]

    def ingest(self, feed, now):
        updated = stamp(feed.get('updatedAt'))
        self.connected = feed.get('sourceConnected') is True and updated is not None and -30 <= now-updated <= 90
        self.status.update(sourceConnected=self.connected, sourceAgeSeconds=round(now-updated) if updated else None)
        if not self.connected:
            return
        messages = feed.get('messages', [])
        if not isinstance(messages, list) or len(messages) > 100:
            raise ValueError('feed_schema')
        messages = list(messages)
        if isinstance(feed.get('pinned'), dict):
            messages.append(feed['pinned'])
        changed = False
        self.s['seen'] = {k:v for k,v in self.s['seen'].items() if now-v < 172800}
        self.s['recent_content'] = {k:v for k,v in self.s.get('recent_content', {}).items() if now-v <= 120}
        for m in sorted(messages, key=lambda x: stamp(x.get('sentAt')) or 0 if isinstance(x, dict) else 0):
            row = parse_message(m, now)
            if row is None:
                continue
            if row['id'] in self.s['seen']:
                continue
            self.s['seen'][row['id']] = row['at']
            changed = True
            self.count('matched')
            # Same content from multiple groups/bot IDs within two minutes is one signal.
            previous = self.s['recent_content'].get(row['fingerprint'])
            if previous is not None and abs(row['at']-previous) <= 120:
                self.count('duplicate_content')
                continue
            self.s['recent_content'][row['fingerprint']] = row['at']
            self.s['history'] = sorted(self.s['history']+[row], key=lambda r:(r['at'], r['id']))[-100:]
            if not matches(row, self.settings) or not self.settings['notify_enabled']:
                self.count('filtered_or_muted')
            elif row['at'] >= self.s['activated'] and -30 <= now-row['at'] <= 120:
                self.s['pending'] = (self.s['pending']+[row])[-100:]
            else:
                self.count('history_without_alert')
        if len(self.s['seen']) > 10000:
            self.s['seen'] = dict(sorted(self.s['seen'].items(), key=lambda kv:kv[1])[-10000:])
        if changed:
            self.refresh_selection()
            self.save()

    def check_quota(self, now):
        if self.quota_checked and now-self.quota_checked < 3600:
            return
        me = self.client.call('GET', '/auth/me')
        q = me.get('usage', me)
        # Current API returns quota fields at the top level; support nested quota objects too.
        for key in ('quota', 'quotas'):
            if isinstance(me.get(key), dict):
                q = me[key]
        if not isinstance(q, dict):
            raise APIError('invalid_quota_schema')
        self.status['quota'] = {k:q.get(k) for k in ('live_activity_updates_used', 'live_activity_updates_limit',
                                                    'notifications_used', 'notifications_limit', 'quota_resets_at')}
        used, limit = q.get('live_activity_updates_used'), q.get('live_activity_updates_limit')
        if self.s.get('activity_error') == 'quota.exceeded' and (me.get('subscribed') is True or
                isinstance(used, int) and isinstance(limit, int) and used < limit):
            self.s['update_after'] = 0
            self.s.pop('activity_error', None)
            self.save()
        used, limit = q.get('notifications_used'), q.get('notifications_limit')
        if self.s.get('last_notification', {}).get('state') == 'quota.exceeded' and (me.get('subscribed') is True or
                isinstance(used, int) and isinstance(limit, int) and used < limit):
            self.s['notify_after'] = 0
            self.s['last_notification']['state'] = 'quota_available_again'
            self.save()
        self.quota_checked = now

    def check_activity(self, now):
        if self.remote is None or now-self.remote_checked >= 300:
            try:
                self.remote = self.client.call('GET', '/activities/'+self.slug)
            except APIError as e:
                if e.code != 'http_404':
                    raise
                self.remote = self.client.call('POST', '/activities', dict(slug=self.slug, name='雷达', stale_ttl=28800, dismissal_ttl=0))
            self.remote_checked = now
            if self.remote.get('state') not in ('ongoing', 'ended', 'preempted') or not isinstance(self.remote.get('content'), dict):
                self.remote = None
                raise APIError('invalid_activity_schema')

    def update_activity(self, now):
        if now < self.s['update_after'] or now-self.s['last_push'] < self.min_interval:
            return
        self.check_activity(now)
        content = render(self.s['rows'], self.connected)
        wanted = digest(content)
        if self.remote.get('state') != 'ongoing':
            # Do not renew an empty idle card indefinitely. New signals resume it.
            if not self.s['rows'] or now-self.s['rows'][-1]['at'] > 28800:
                self.status['activity'] = 'ended_waiting_for_new_signal'
                return
            self.remote = self.client.call('PATCH', '/activities/'+self.slug, dict(state='ongoing', content={
                'template':'generic', 'state':None, 'progress':0.5,
                'lines':None, 'icon':'waveform.path.ecg', 'accent_color':'#00865F'}))
            self.s['bootstrap_until'] = now+self.min_interval
            self.s['last_push'] = now
            self.s['pushed'] = ''
            self.save()
            self.status['activity'] = 'bootstrap_server_accepted'
            return
        if now < self.s['bootstrap_until']:
            return
        if wanted == self.s['pushed']:
            return
        # Reconcile unknown prior delivery via GET before retrying an identical update.
        if all(self.remote.get('content', {}).get(k) == v for k,v in content.items() if k != 'progress'):
            self.s['pushed'] = wanted
            self.s.pop('activity_error', None)
            self.s['failures'] = 0
            self.save()
            self.status.pop('activityError', None)
            return
        patch = dict(content)
        for key in self.remote.get('content', {}):
            if key not in patch:
                patch[key] = None
        self.remote = self.client.call('PATCH', '/activities/'+self.slug, dict(state='ongoing', content=patch))
        if self.remote.get('state') != 'ongoing' or self.remote.get('content', {}).get('lines') != content['lines']:
            raise APIError('update_response_mismatch', 60, True)
        self.s.update(pushed=wanted, last_push=now, bootstrap_until=0)
        self.s.pop('activity_error', None)
        self.s['failures'] = 0
        self.count('activity_server_accepted')
        self.save()
        self.status.update(activity='server_accepted', lastActivityAcceptedAt=now)
        self.status.pop('activityError', None)

    def notify(self, now):
        interval = self.settings['notify_interval_seconds']
        last_attempt = self.s.get('last_notification', {}).get('at', 0)
        if not self.settings['notify_enabled'] or now < self.s['notify_after'] or now < last_attempt+interval:
            return
        pending = [r for r in self.s['pending'] if 0 <= now-r['at'] <= max(120, interval+30)]
        future = [r for r in self.s['pending'] if 0 < r['at']-now <= 30]
        if not pending:
            if len(self.s['pending']) != len(future):
                self.count('expired_alerts', len(self.s['pending'])-len(future))
                self.s['pending'] = future
                self.save()
            return
        pending.sort(key=lambda r:(r['at'], r['id']))
        batch_id = digest([r['id'] for r in pending])
        rows = pending[-self.settings['rows']:]
        body = '\n'.join(f"{r['coin']} {r['mode']} {r['buy']}→{r['sell']} {r['rank']} {r['value']}" for r in rows)
        payload = dict(title='雷达 · '+str(len(pending))+'条新消息', body=body,
                       source='radar-live', source_display_name='雷达', thread_id='radar-live',
                       collapse_id=batch_id, activity_slug=self.slug, level='active', push=True)
        # Persist before sending: a crash/timeout cannot cause repeated alerts after restart.
        self.s['pending'] = future
        self.s['notify_after'] = now+self.min_interval
        self.s['last_notification'] = dict(batch=batch_id, count=len(pending), state='attempted', at=now)
        self.save()
        try:
            result = self.client.call('POST', '/notifications', payload)
        except APIError as e:
            self.s['last_notification']['state'] = 'unknown' if e.uncertain else e.code
            if e.code in ('quota.exceeded', 'http_429'):
                self.s['pending'] = (pending+future)[-100:]
                self.s['notify_after'] = now+e.retry
            self.save()
            raise
        pushed = result.get('pushed') is True
        self.s['last_notification']['state'] = 'server_pushed' if pushed else 'server_not_pushed'
        self.count('notification_server_pushed' if pushed else 'notification_not_pushed')
        self.save()
        self.status['lastNotification'] = self.s['last_notification']
        self.status.pop('notificationError', None)

    def quota_notice(self, now):
        # One ordinary notification per quota period; do not turn a failure into a retry storm.
        period = datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m')
        if not self.settings['notify_enabled'] or self.s.get('activity_error') != 'quota.exceeded' or self.s.get('quota_notice') == period:
            return
        self.s['quota_notice'] = period
        self.save()
        try:
            result = self.client.call('POST', '/notifications', dict(title='雷达 · 锁屏更新额度已用完',
                body='PushWard本月实时活动更新额度已用完，锁屏列表暂停更新。新信号普通提醒仍会尝试发送；可在PushWard查看额度。',
                source='radar-live', source_display_name='雷达', thread_id='radar-live-status',
                collapse_id='radar-quota-'+period, level='active', push=True))
            self.status['quotaNotice'] = 'server_pushed' if result.get('pushed') else 'server_not_pushed'
        except APIError:
            self.status['quotaNotice'] = 'unconfirmed'

    def tick(self, feed, now):
        try:
            self.ingest(feed, now)
        except (ValueError, TypeError, KeyError):
            self.connected = False
            self.status.update(sourceConnected=False, sourceError='invalid_feed')
        if not self.quota_checked or now-self.quota_checked >= 3600:
            try:
                self.check_quota(now)
            except APIError as e:
                self.quota_checked = now-3300
                self.status['quotaError'] = e.code
        try:
            self.update_activity(now)
        except APIError as e:
            self.status['activityError'] = e.code
            self.s['activity_error'] = e.code
            self.s['failures'] = min(5, self.s.get('failures', 0)+1)
            delay = e.retry if e.code in ('quota.exceeded', 'http_429') else max(e.retry, min(900, 30*2**self.s['failures']))
            self.s['update_after'] = now+delay
            self.remote = None
            self.save()
        self.quota_notice(now)
        if self.connected:
            try:
                self.notify(now)
            except APIError as e:
                self.status['notificationError'] = e.code
        if not self.status_written or now-self.status_written >= 30:
            self.status.update(checkedAt=now, rows=len(self.s['rows']), pending=len(self.s['pending']),
                               counters=self.s['counters'], lastNotification=self.s.get('last_notification'),
                               activityRetryAt=self.s['update_after'])
            atomic(self.directory/'status.json', self.status)
            self.status_written = now


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--feed', required=True)
    p.add_argument('--state-directory', required=True)
    p.add_argument('--slug', required=True)
    p.add_argument('--key-file', required=True)
    p.add_argument('--admin-key-file')
    p.add_argument('--settings-port', type=int, default=18884)
    p.add_argument('--settings-origin', default='https://leida.shenmiren.work')
    args = p.parse_args()
    # The deployed Linux service has one durable owner, including manual invocations.
    import fcntl
    directory = Path(args.state_directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory/'service.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    client = Client(Path(args.key_file).read_text(encoding='utf-8').strip())
    bridge = Bridge(client, args.state_directory, args.slug, time.time())
    store = Store(directory/'preferences.json')
    if args.admin_key_file:
        import threading
        settings_server = SettingsServer(('127.0.0.1', args.settings_port), store,
            Path(args.admin_key_file).read_text(encoding='utf-8').strip(), directory, args.settings_origin)
        threading.Thread(target=settings_server.serve_forever, daemon=True).start()
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        preferences = store.get()
        bridge.configure(preferences['settings'], preferences['revision'])
        try:
            path = Path(args.feed)
            if path.stat().st_size > 2*1024*1024:
                raise ValueError('feed_oversize')
            feed = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(feed, dict):
                raise ValueError('feed_schema')
            bridge.status.pop('feedReadError', None)
        except (OSError, ValueError) as e:
            feed = {}
            bridge.status['feedReadError'] = type(e).__name__
        bridge.tick(feed, time.time())
        time.sleep(2)


if __name__ == '__main__':
    main()
