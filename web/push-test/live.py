"""Production BOT feed consumer. Reuses the established phone subscription and sequence."""
import copy
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from server import Trial, compact_rows, validate_subscription, ORIGIN
from delivery import fingerprint, with_fallback, TTL
from signals import parse_message, stamp
from preferences import DEFAULTS, validate, matches


class Live(Trial):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state.setdefault('live', dict(settings=copy.deepcopy(DEFAULTS), revision=0,
            activated=time.time(), seen={}, history=[], pending=[], lastAttempt=0, retryAt=0, failures=0))
        validate(self.state['live']['settings'])
        self.source = {'connected': False, 'error': None}
        self.save()

    def authenticate(self, token):
        # A paired production device remains authorized after the trial window.
        import hmac
        return bool(self.state.get('token')) and hmac.compare_digest(token, self.state['token'])

    def pair(self, code):
        # Keep the existing owner code; access is additionally behind the site's login.
        expires = self.config['expiresAt']
        with self.lock:
            try:
                self.config['expiresAt'] = float('inf')
                return super().pair(code)
            finally:
                self.config['expiresAt'] = expires

    def public_status(self):
        with self.lock:
            result = super().public_status()
            s = self.state['live']
            rows = self.selected(time.time())
            result.update(mode='live', settings=copy.deepcopy(s['settings']), revision=s['revision'],
                          source=self.source.copy(), preview=self.render(rows),
                          lastDelivery=s.get('lastDelivery'), pending=len(s['pending']))
            result.update(subscriptionFingerprint=fingerprint(self.state.get('subscription')),
                          device=self.state.get('device'), deliveryTtl=TTL)
            return result

    def device_status(self, value):
        import re
        if value.get('permission') not in ('granted', 'denied', 'default', 'unsupported'):
            raise ValueError('无效的手机通知状态')
        fp = value.get('subscriptionFingerprint')
        if fp is not None and (not isinstance(fp, str) or not re.fullmatch('[a-f0-9]{64}', fp)):
            raise ValueError('无效的订阅状态')
        with self.lock:
            self.state['device'] = dict(at=time.time(), permission=value['permission'],
                subscribed=bool(fp), matches=fp == fingerprint(self.state.get('subscription')) and bool(fp),
                version=value.get('version') if value.get('version') in ('radar-delivery-v4', 'radar-delivery-v5', 'radar-delivery-v6') else 'unknown')
            self.save()
            return self.state['device'].copy()

    def notification_payload(self, payload):
        # Older workers only read event.data; don't send them Apple's data-less event.
        if self.state.get('device', {}).get('version') == 'radar-delivery-v5':
            return with_fallback(payload, ORIGIN)
        return payload

    def repair_subscription(self, value, expected):
        subscription = validate_subscription(value)
        with self.lock:
            current = self.state.get('subscription')
            if current != subscription and expected != fingerprint(current):
                raise ValueError('订阅已变化，请重新打开设置')
            self.state['subscription'] = subscription
            self.state.pop('device', None)
            self.save()

    def verify_delivery(self):
        """One authenticated, bounded diagnostic; never takes arbitrary message text."""
        with self.lock:
            now = time.time()
            if not self.state.get('subscription') or not self.state.get('device', {}).get('matches'):
                raise ValueError('请先在手机上恢复通知订阅')
            if now-self.state.get('lastVerificationAt', 0) < 300:
                raise ValueError('五分钟内已发送校验，请查看接收日志')
            self.state['lastVerificationAt'] = now
            self.state['seq'] += 1
            clock = datetime.fromtimestamp(now, timezone(timedelta(hours=8))).strftime('%H:%M')
            rows = [f'{clock} 雷达推送链路校验', '四行通知 · 非交易信号', '手机接收与显示自动记录', '后续按原设置接收真实消息']
            payload = self.notification_payload(dict(kind='radar-six-test', title='', seq=self.state['seq'], run='verify', rows=rows))
            s = self.state['live']
            s['lastAttempt'] = now
            s['lastDelivery'] = dict(at=now, seq=payload['seq'], rows=4, state='attempted', run='verify')
            self.save()
            status, error = None, None
            try:
                status = self.sender(self.state['subscription'], payload)
            except Exception as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                error = type(exc).__name__
            s['lastDelivery'].update(state='accepted' if status == 201 and error is None else 'failed', http=status, error=error)
            self.state['sends'] = (self.state['sends']+[dict(s['lastDelivery'], ttl=TTL)])[-2000:]
            self.save()
            return s['lastDelivery'].copy()

    def configure(self, value):
        settings = validate(value.get('settings'))
        with self.lock:
            s = self.state['live']
            if type(value.get('revision')) is not int or value['revision'] != s['revision']:
                raise ValueError('设置已在其他页面修改，请重新打开设置再保存')
            previous = copy.deepcopy(s)
            # Saving an unchanged form must not discard messages waiting for the interval.
            pending = [r['id'] for r in s['history'] if r['id'] in s['pending'] and matches(r, settings)] if settings['notify_enabled'] else []
            s.update(settings=settings, revision=s['revision']+1, pending=pending)
            try:
                self.save()
            except OSError:
                self.state['live'] = previous
                raise
            return self.public_status()

    def start(self):
        raise ValueError('已切换真实消息，示例测试已关闭')

    def resend(self, *args, **kwargs):
        raise ValueError('已切换真实消息，示例测试已关闭')

    def stop(self):
        # Retained for clients with the old cached trial UI.
        with self.lock:
            s = self.state['live']
            settings = dict(s['settings'], notify_enabled=False)
            self.configure(dict(settings=settings, revision=s['revision']))

    def selected(self, now):
        s = self.state['live']
        return [r for r in s['history'] if -30 <= now-r['at'] <= 1800
                and matches(r, s['settings'])][-s['settings']['rows']:]

    @staticmethod
    def render(rows):
        zone = timezone(timedelta(hours=8))
        # Reverse display only; chronological history/pending and dedup stay intact.
        rows = sorted(rows, key=lambda r: (r['at'], r['id']), reverse=True)
        return compact_rows([f"{r['coin']} {r['mode']} {r['buy']}→{r['sell']} {r['rank']} {r['value']} "
                             + datetime.fromtimestamp(r['at'], zone).strftime('%H:%M:%S') for r in rows])

    def tick(self, feed, now):
        with self.lock:
            updated = stamp(feed.get('updatedAt'))
            connected = feed.get('sourceConnected') is True and updated is not None and -30 <= now-updated <= 90
            self.source = dict(connected=connected, checkedAt=now, error=None)
            if not connected:
                return
            messages = feed.get('messages', [])
            if not isinstance(messages, list) or len(messages) > 100:
                raise ValueError('invalid_feed')
            messages = messages + ([feed['pinned']] if isinstance(feed.get('pinned'), dict) else [])
            s = self.state['live']
            old = json.dumps(s, sort_keys=True)
            s['seen'] = {k:v for k,v in s['seen'].items() if now-v < 172800}
            s['history'] = [r for r in s['history'] if now-r['at'] <= 1800]
            parsed = [r for m in messages if (r := parse_message(m, now))]
            for row in sorted(parsed, key=lambda r:(r['at'], r['id'])):
                if row['id'] in s['seen']:
                    continue
                s['seen'][row['id']] = row['at']
                if any(r['fingerprint'] == row['fingerprint'] and abs(r['at']-row['at']) <= 120 for r in s['history']):
                    continue
                s['history'] = sorted(s['history']+[row], key=lambda r:(r['at'], r['id']))[-100:]
                if (s['settings']['notify_enabled'] and matches(row, s['settings'])
                        and row['at'] >= s.get('acceptAfter', s['activated']-120) and -30 <= now-row['at'] <= 120):
                    s['pending'] = (s['pending']+[row['id']])[-100:]
            if len(s['seen']) > 10000:
                s['seen'] = dict(sorted(s['seen'].items(), key=lambda kv:kv[1])[-10000:])
            eligible = {r['id'] for r in s['history'] if matches(r, s['settings'])
                        and -30 <= now-r['at'] <= max(180, s['settings']['notify_interval_seconds']+30)}
            s['pending'] = [i for i in s['pending'] if i in eligible]
            if json.dumps(s, sort_keys=True) != old:
                self.save()
            if (not s['settings']['notify_enabled'] or not self.state.get('subscription') or not s['pending']
                    or ('device' in self.state and not (self.state['device']['permission'] == 'granted' and self.state['device']['matches']))
                    or now < max(s['retryAt'], s['lastAttempt']+s['settings']['notify_interval_seconds'])):
                return
            rows = self.render(self.selected(now))
            if not rows:
                return
            pending, s['pending'] = s['pending'], []
            s['lastAttempt'] = now
            self.state['seq'] += 1
            payload = self.notification_payload(dict(kind='radar-six-test', title='', seq=self.state['seq'], run='live', rows=rows))
            assert len(json.dumps(payload, ensure_ascii=False).encode()) < 3000
            # Persist intent before sending: an uncertain timeout/restart cannot replay an alert.
            s['lastDelivery'] = dict(at=now, seq=payload['seq'], rows=len(rows), state='attempted')
            self.save()
            status, error = None, None
            try:
                status = self.sender(self.state['subscription'], payload)
            except Exception as exc:
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                error = type(exc).__name__
            accepted = status == 201 and error is None
            s['lastDelivery'].update(state='accepted' if accepted else 'failed', http=status, error=error)
            self.state['sends'] = (self.state['sends']+[dict(s['lastDelivery'], run='live', ttl=TTL)])[-2000:]
            if accepted:
                s['failures'] = 0
            elif status in (404, 410):
                self.state.pop('subscription', None)
            elif status == 429 or status is not None and status >= 500:
                s['failures'] += 1
                if s['failures'] <= 3:
                    s['pending'] = pending
                    s['retryAt'] = now+min(900, 60*2**s['failures'])
            self.save()

    def run_feed(self, path):
        while True:
            try:
                source = Path(path)
                if source.stat().st_size > 2*1024*1024:
                    raise ValueError('feed_oversize')
                value = json.loads(source.read_text(encoding='utf-8'))
                if not isinstance(value, dict):
                    raise ValueError('feed_schema')
                self.tick(value, time.time())
            except (OSError, ValueError, TypeError, KeyError) as exc:
                with self.lock:
                    self.source = dict(connected=False, checkedAt=time.time(), error=type(exc).__name__)
            time.sleep(3)
