"""Atomic rule revisions, trigger state and durable outbox in SQLite WAL."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from engine import evaluate, validate, validate_content, matches, number, REPEAT_SECONDS
from sources import select, active_groups, source_key, source_label, fresh
from content import render_content, validate_template


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, directory):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        key = root / 'bark-encryption.key'
        if not key.exists():
            with open(key, 'xb') as handle:
                handle.write(Fernet.generate_key())
            key.chmod(0o600)
        self.cipher = Fernet(key.read_bytes())
        self.lock = threading.RLock()
        self.db = sqlite3.connect(root / 'alarms.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS devices (profile TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, secret TEXT NOT NULL, label TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, profile TEXT NOT NULL, config TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS rules_profile ON rules(profile);
        CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, profile TEXT NOT NULL, rule_id TEXT NOT NULL, at REAL NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL, expires REAL NOT NULL, fingerprint TEXT, error TEXT);
        CREATE INDEX IF NOT EXISTS outbox ON events(status,next_at);
        CREATE INDEX IF NOT EXISTS events_profile ON events(profile,at);
        CREATE TABLE IF NOT EXISTS requests (profile TEXT NOT NULL, id TEXT NOT NULL, digest TEXT NOT NULL, response TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY(profile,id));
        ''')
        with self.db:
            # Transactional, one-time migration: preserve encrypted keys and labels verbatim.
            if 'id' not in {r['name'] for r in self.db.execute('PRAGMA table_info(devices)')}:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('ALTER TABLE devices RENAME TO devices_single')
                self.db.execute('CREATE TABLE devices (id TEXT PRIMARY KEY, profile TEXT NOT NULL, fingerprint TEXT UNIQUE NOT NULL, secret TEXT NOT NULL, label TEXT NOT NULL)')
                for device in self.db.execute('SELECT * FROM devices_single').fetchall():
                    self.db.execute('INSERT INTO devices VALUES (?,?,?,?,?)', (secrets.token_hex(16), *tuple(device)))
                self.db.execute('DROP TABLE devices_single')
            self.db.execute('CREATE INDEX IF NOT EXISTS devices_profile ON devices(profile)')
            self.db.execute('CREATE TABLE IF NOT EXISTS device_dispatch (rule_id TEXT NOT NULL, fingerprint TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY(rule_id,fingerprint))')
            # Preserve effective pauses when retiring the account-wide switch.
            for profile in self.db.execute('SELECT id FROM profiles WHERE enabled=0').fetchall():
                for row in self.db.execute('SELECT id,config,state FROM rules WHERE profile=?', (profile['id'],)).fetchall():
                    rule, state = json.loads(row['config']), json.loads(row['state'])
                    rule['enabled'] = False
                    state.update(gap=True, pending=None, status='paused')
                    self.db.execute('UPDATE rules SET config=?,state=? WHERE id=?', (dump(rule), dump(state), row['id']))
                self.cancel(profile['id'])
                self.db.execute('UPDATE profiles SET enabled=1,revision=revision+1 WHERE id=?', (profile['id'],))
            self.db.execute("UPDATE events SET status='unknown',error='发送过程中服务重启，结果未知' WHERE status='sending'")
            self.db.execute("UPDATE events SET status='queued' WHERE status='claimed' AND rule_id IN ('tbtc-mint','tbtc-backed-mint','tbtc-btc-deposit','tbtc-large-sale')")
            self.db.execute("UPDATE events SET status='queued' WHERE status='claimed' AND rule_id='tbtc-price' AND json_extract(payload,'$.target') IS NOT NULL")
            self.db.execute("UPDATE events SET status='cancelled',error='服务重启，取消尚未发送的消息' WHERE status='claimed'")
            for row in self.db.execute('SELECT id,state FROM rules').fetchall():
                state = json.loads(row['state'])
                state.update(gap=True, pending=None)
                self.db.execute('UPDATE rules SET state=? WHERE id=?', (dump(state), row['id']))

    def ensure(self, profile):
        self.db.execute('INSERT OR IGNORE INTO profiles(id) VALUES (?)', (profile,))

    def view(self, profile, compact=False):
        with self.lock, self.db:
            self.ensure(profile)
            p = dict(self.db.execute('SELECT * FROM profiles WHERE id=?', (profile,)).fetchone())
            devices = self.device_list(profile)
            d = devices[0] if devices else None
            rules = [dict(id=r['id'], **json.loads(r['config']), state=json.loads(r['state'])) for r in self.db.execute('SELECT * FROM rules WHERE profile=? ORDER BY created DESC', (profile,))]
            event_sql = "SELECT * FROM events WHERE profile=?" + (" AND rule_id='test' AND at=(SELECT MAX(at) FROM events WHERE profile=? AND rule_id='test') ORDER BY id" if compact else " ORDER BY at DESC LIMIT 100")
            events = [dict(json.loads(r['payload']), id=r['id'], ruleId=r['rule_id'], at=r['at'], status='queued' if r['status']=='claimed' else r['status'], attempts=r['attempts'], error=r['error']) for r in self.db.execute(event_sql, (profile, profile) if compact else (profile,))]
            return dict(revision=p['revision'], enabled=True, device=d, devices=devices, rules=rules, events=events)

    def device_list(self, profile, reveal=False):
        with self.lock:
            return [dict(id=d['id'], label=d['label'], suffix=d['fingerprint'][-6:],
                         **({'key': self.cipher.decrypt(d['secret'].encode()).decode()} if reveal else {}))
                    for d in self.db.execute('SELECT * FROM devices WHERE profile=? ORDER BY rowid', (profile,))]

    def selected_device(self, profile, identity):
        if identity:
            device = self.db.execute('SELECT * FROM devices WHERE profile=? AND id=?', (profile, identity)).fetchone()
            if not device:
                raise ValueError('设备不存在或不属于当前推送码')
            return device
        devices = self.db.execute('SELECT * FROM devices WHERE profile=?', (profile,)).fetchall()
        if len(devices) != 1:
            raise ValueError('请选择要操作的设备，请刷新页面')
        return devices[0]

    def history(self, profile, query):
        def arg(name, default=''): return query.get(name, [default])[0]
        page=max(1,min(100000,int(arg('page','1'))));days=int(arg('days','30'))
        if days not in (1,7,30): raise ValueError('时间范围不正确')
        anchor=float(arg('before',str(time.time())))
        if not 0 < anchor <= time.time()+60: raise ValueError('时间范围不正确')
        where=['profile=?','at>=?','at<=?'];args=[profile,anchor-days*86400,anchor]
        status=arg('status');q=arg('q').strip().upper()
        if len(q)>64: raise ValueError('搜索内容过长')
        if status:
            if status not in ('queued','sending','accepted','retry','failed','unknown','expired','cancelled','no_device'): raise ValueError('状态不正确')
            where.append("status IN ('queued','claimed')" if status=='queued' else 'status=?')
            if status!='queued':args.append(status)
        if q:
            title="json_extract(payload,'$.title')"
            symbol=f"upper(substr({title},1,instr({title},' ')-1))"
            where.append(f'({symbol}=? OR {symbol}=?)');args.extend([q,q+'USDT'])
        sql=' FROM events WHERE '+' AND '.join(where)
        with self.lock:
            total=self.db.execute('SELECT count(*)'+sql,args).fetchone()[0]
            rows=self.db.execute("SELECT id,at,status,attempts,json_extract(payload,'$.title') AS title"+sql+' ORDER BY at DESC,id DESC LIMIT 20 OFFSET ?',[*args,(page-1)*20]).fetchall()
            return dict(items=[{**dict(r),'status':'queued' if r['status']=='claimed' else r['status']} for r in rows],total=total,page=page,pageSize=20,before=anchor)

    def event_detail(self, profile, identity):
        with self.lock:
            r=self.db.execute('SELECT * FROM events WHERE profile=? AND id=?',(profile,identity)).fetchone()
            if not r: raise ValueError('记录不存在')
            return dict(id=r['id'],body=json.loads(r['payload']).get('body',''),error=r['error'],attempts=r['attempts'])

    def mutate(self, profile, data, catalog):
        request_id = data.get('requestId', '')
        if not isinstance(request_id, str) or not re.fullmatch('[a-f0-9]{32}', request_id):
            raise ValueError('请求编号无效')
        digest = hashlib.sha256(dump(data).encode()).hexdigest()
        with self.lock, self.db:
            self.ensure(profile)
            old = self.db.execute('SELECT * FROM requests WHERE profile=? AND id=?', (profile, request_id)).fetchone()
            if old:
                if old['digest'] != digest:
                    raise Conflict('同一请求编号的内容已改变，请重新载入')
                return json.loads(old['response'])
            p = self.db.execute('SELECT * FROM profiles WHERE id=?', (profile,)).fetchone()
            if type(data.get('revision')) is not int or data['revision'] != p['revision']:
                raise Conflict('设置已在其他页面更新，请刷新后再操作')
            action, now = data.get('action'), time.time()
            changed_id = None
            if action == 'save':
                rule = validate(data.get('rule'))
                q = catalog.get((rule['exchange'], rule['market'], rule['symbol']))
                if not q or not q.get(rule['priceType']) or now - q['observedAt'] > 90:
                    raise ValueError('交易对或价格暂不可用，请等待行情恢复后保存')
                if rule['expiresAt'] and rule['expiresAt'] <= now:
                    raise ValueError('有效期必须晚于当前时间')
                identity = data.get('id')
                if identity:
                    old_rule = self.db.execute('SELECT * FROM rules WHERE id=? AND profile=?', (identity, profile)).fetchone()
                    if not old_rule:
                        raise ValueError('报警不存在或不属于当前推送码')
                    # Older/general editors must not erase separately managed content.
                    if 'alarmContent' not in data['rule']:
                        rule['alarmContent'] = json.loads(old_rule['config']).get('alarmContent', '')
                        if json.loads(old_rule['config']).get('alarmContentMode') == 'template':
                            rule['alarmContentMode'] = 'template'
                    if 'fallbackExchanges' in json.loads(old_rule['config']) and 'fallbackExchanges' not in rule:
                        raise Conflict('此报警已使用备用源多选，请刷新页面后再保存')
                    old_state = json.loads(old_rule['state'])
                    # Editing a repeating rule must not bypass the 30-second interval.
                    state = {k: old_state[k] for k in ('lastFire', 'lastDispatch', 'fired') if k in old_state} if rule['repeat'] else {}
                    self.db.execute('UPDATE rules SET config=?,state=? WHERE id=? AND profile=?', (dump(rule), dump(state), identity, profile))
                    self.cancel(profile, identity)
                else:
                    if self.db.execute('SELECT count(*) FROM rules WHERE profile=?', (profile,)).fetchone()[0] >= 100:
                        raise ValueError('每个推送码最多 100 条报警')
                    identity = secrets.token_hex(16)
                    self.db.execute('INSERT INTO rules VALUES (?,?,?,?,?)', (identity, profile, dump(rule), '{}', now))
                changed_id = identity
            elif action == 'content':
                mode = data.get('alarmContentMode')
                content = validate_content(data.get('alarmContent'), 2000 if mode == 'template' else 1000)
                if mode is not None and mode != 'template':
                    raise ValueError('报警内容格式不正确')
                if mode == 'template':
                    validate_template(content)
                identity = data.get('id')
                row = self.db.execute('SELECT config FROM rules WHERE id=? AND profile=?', (identity, profile)).fetchone()
                if not row:
                    raise ValueError('报警不存在或不属于当前推送码')
                rule = json.loads(row['config'])
                rule['alarmContent'] = content
                if mode == 'template':
                    rule['alarmContentMode'] = mode
                else:
                    rule.pop('alarmContentMode', None)
                # Preserve state, dispatch clocks and the current round's immutable payloads.
                self.db.execute('UPDATE rules SET config=? WHERE id=? AND profile=?', (dump(rule), identity, profile))
                changed_id = identity
            elif action in ('delete', 'toggle'):
                identity = data.get('id')
                row = self.db.execute('SELECT * FROM rules WHERE id=? AND profile=?', (identity, profile)).fetchone()
                if not row:
                    raise ValueError('报警不存在或不属于当前推送码')
                self.cancel(profile, identity)
                if action == 'delete':
                    self.db.execute('DELETE FROM rules WHERE id=? AND profile=?', (identity, profile))
                else:
                    if type(data.get('enabled')) is not bool:
                        raise ValueError('开关格式错误')
                    rule, state = json.loads(row['config']), json.loads(row['state'])
                    rule['enabled'] = data['enabled']
                    state.update(gap=True, pending=None, status='waiting' if rule['enabled'] else 'paused')
                    self.db.execute('UPDATE rules SET config=?,state=? WHERE id=?', (dump(rule), dump(state), identity))
            elif action == 'enabled':
                raise ValueError('请在单条报警的编辑窗口中启用或暂停')
            elif action == 'bind':
                value = data.get('key', '')
                if not isinstance(value, str):
                    raise ValueError('请输入 Bark Key 或官方推送地址')
                value = value.strip()
                if value.startswith('https://'):
                    parsed = urlsplit(value)
                    if parsed.netloc != 'api.day.app' or parsed.query or parsed.fragment:
                        raise ValueError('当前支持 api.day.app 官方 Bark 地址')
                    value = parsed.path.strip('/')
                if not re.fullmatch('[A-Za-z0-9_-]{8,128}', value):
                    raise ValueError('Bark Key 格式不正确，请复制 App 首页的推送地址')
                fingerprint = hashlib.sha256(value.encode()).hexdigest()
                existing = self.selected_device(profile, data['deviceId']) if data.get('deviceId') else None
                owner = self.db.execute('SELECT profile,id FROM devices WHERE fingerprint=?', (fingerprint,)).fetchone()
                if owner and owner['profile'] != profile:
                    raise Conflict('该 Bark 设备已绑定其他推送码，请先在原码解除绑定')
                if owner and (not existing or owner['id'] != existing['id']):
                    raise ValueError('该 Bark Key 已绑定，无需重复添加')
                label = data.get('label', '我的 iPhone')
                if not isinstance(label, str) or not 1 <= len(label.strip()) <= 30:
                    raise ValueError('设备名称应为 1 至 30 字')
                if existing:
                    if existing['fingerprint'] != fingerprint:
                        self.cancel_device(profile, existing['fingerprint'])
                    self.db.execute('UPDATE devices SET fingerprint=?,secret=?,label=? WHERE id=? AND profile=?', (fingerprint, existing['secret'] if existing['fingerprint'] == fingerprint else self.cipher.encrypt(value.encode()).decode(), label.strip(), existing['id'], profile))
                    changed_id = existing['id']
                else:
                    if self.db.execute('SELECT count(*) FROM devices WHERE profile=?', (profile,)).fetchone()[0] >= 100:
                        raise ValueError('每个推送码最多绑定 100 台设备')
                    changed_id = secrets.token_hex(16)
                    self.db.execute('INSERT INTO devices VALUES (?,?,?,?,?)', (changed_id, profile, fingerprint, self.cipher.encrypt(value.encode()).decode(), label.strip()))
            elif action == 'unbind':
                device = self.selected_device(profile, data.get('deviceId'))
                self.cancel_device(profile, device['fingerprint'])
                self.db.execute('DELETE FROM devices WHERE profile=? AND id=?', (profile, device['id']))
            elif action == 'test':
                devices = [self.selected_device(profile, data['deviceId'])] if data.get('deviceId') else self.db.execute('SELECT * FROM devices WHERE profile=?', (profile,)).fetchall()
                if not devices:
                    raise ValueError('请先绑定 Bark')
                for device in devices:
                    if self.db.execute("SELECT 1 FROM events WHERE profile=? AND fingerprint=? AND rule_id='test' AND at>?", (profile, device['fingerprint'], now - 60)).fetchone():
                        raise ValueError('部分设备刚发送过测试，请间隔一分钟再试')
                round_id = secrets.token_hex(16)
                for device in devices:
                    self.event(profile, 'test', dict(title='雷达报警测试', body='这是一条手动测试通知。接收设备：' + device['label'], group='雷达报警测试', level='critical', url='https://leida.shenmiren.work/radar/robot-push/alarms/', roundId=round_id), device, now)
            else:
                raise ValueError('不支持的操作')
            self.db.execute('UPDATE profiles SET revision=revision+1 WHERE id=?', (profile,))
            result = dict(ok=True, revision=p['revision'] + 1, id=changed_id)
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)', (profile, request_id, digest, dump(result), now))
            # Retain idempotency responses for seven days; clients never silently replay older requests.
            self.db.execute('DELETE FROM requests WHERE at<?', (now - 7 * 86400,))
            return result

    def cancel(self, profile, identity=None, reason='规则或设备已变更'):
        sql = "UPDATE events SET status='cancelled',error=? WHERE profile=? AND status IN ('queued','retry','claimed')"
        args = [reason, profile]
        if identity:
            sql += ' AND rule_id=?'
            args.append(identity)
        self.db.execute(sql, args)

    def cancel_device(self, profile, fingerprint):
        self.db.execute("UPDATE events SET status='cancelled',error='设备已变更或解绑' WHERE profile=? AND fingerprint=? AND status IN ('queued','retry','claimed')", (profile, fingerprint))

    def event(self, profile, identity, payload, device, now):
        event_id = secrets.token_hex(16)
        payload = dict(payload)
        payload['id'] = event_id
        if device:
            payload.update(deviceId=device['id'], deviceLabel=device['label'])
        self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,0,?,?,?,?)', (event_id, profile, identity, now, dump(payload), 'queued' if device else 'no_device', now, now + payload.get('repeatInterval', 120), device['fingerprint'] if device else None, None if device else '未绑定 Bark，事件已记录'))

    def tick(self, quotes, now):
        active = set()
        with self.lock, self.db:
            rows = self.db.execute('SELECT * FROM rules').fetchall()
            for row in rows:
                rule = json.loads(row['config'])
                previous = json.loads(row['state'])
                key = rule['exchange'], rule['market'], rule['symbol']
                selected, effective, routing = select(rule, previous, quotes, now)
                state, event = evaluate(effective, routing, selected, now)
                old_route = (previous.get('sourceStatus'), source_key(previous.get('source')))
                new_route = (state.get('sourceStatus'), source_key(state.get('source')))
                if old_route != new_route:
                    transition = dict(at=now, status=state.get('sourceStatus'), source=state.get('source') if selected else None, reason=state.get('routingReason'))
                    state['routingHistory'] = [*previous.get('routingHistory', []), transition][-12:]
                if state['status'] not in ('paused', 'expired', 'triggered'):
                    active.update(active_groups(rule, state))
                if state != previous:
                    self.db.execute('UPDATE rules SET state=? WHERE id=?', (dump(state), row['id']))
                if rule['repeat'] and state['status'] != 'alarming':
                    self.cancel(row['profile'], row['id'], '价格条件已解除、行情失效或报警已停止')
                if event:
                    if rule['repeat']:
                        self.cancel(row['profile'], row['id'], '已由本轮报警替代')
                    names = dict(above='涨到', below='跌到', enter='进入区间', exit='离开区间')
                    clock = time.strftime('%m-%d %H:%M:%S', time.gmtime(now + 8 * 3600))
                    condition = rule['target'] + ('～' + rule['upper'] if rule['upper'] else '')
                    title = state.get('asset', {}).get('pair', rule['symbol']) + ' ' + names[rule['condition']] + ' ' + condition
                    reason = '价格仍满足条件，每 30 秒提醒' if event['reason'] == 'continuous' else '行情恢复时满足条件' if event['reason'] == 'recovery' else '启用时已满足条件' if event['reason'] == 'initial' else '价格穿越'
                    body = render_content(rule, {'行情来源': source_label(state['source']), '触发价格': event['price'],
                        '触发原因': reason, '时间': clock, '备注': rule['note'],
                        '币种': state.get('asset', {}).get('pair', rule['symbol']),
                        '触发条件': names[rule['condition']] + ' ' + condition})
                    payload = dict(title=title, body=body, group='雷达价格 · ' + rule['symbol'], level='critical', url='https://leida.shenmiren.work/radar/robot-push/alarms/?rule=' + row['id'], price=event['price'], sampleAt=event['sampleAt'], reason=event['reason'], source=state['source'])
                    if rule['repeat']:
                        payload['repeatInterval'] = REPEAT_SECONDS
                    payload['roundId'] = secrets.token_hex(16)
                    devices = self.db.execute('SELECT * FROM devices WHERE profile=?', (row['profile'],)).fetchall()
                    for device in devices or [None]:
                        self.event(row['profile'], row['id'], payload, device, now)
            self.db.execute("UPDATE events SET status='expired',error='超过发送时效' WHERE status IN ('queued','retry') AND expires<?", (now,))
            self.db.execute("DELETE FROM events WHERE at<? AND status NOT IN ('queued','retry','claimed','sending')", (now - 30 * 86400,))
        return active

    def claim(self):
        with self.lock, self.db:
            now = time.time()
            row = self.db.execute("SELECT e.*,d.secret FROM events e JOIN devices d ON e.profile=d.profile AND e.fingerprint=d.fingerprint WHERE e.status IN ('queued','retry') AND e.next_at<=? AND e.expires>? ORDER BY e.at LIMIT 1", (now, now)).fetchone()
            if not row:
                return None
            self.db.execute("UPDATE events SET status='claimed' WHERE id=?", (row['id'],))
            return dict(row)

    def begin_send(self, event, quotes=None, now=None):
        """Recheck immediately before HTTP; queued work is revocable, sent work is not."""
        now = time.time() if now is None else now
        with self.lock, self.db:
            row = self.db.execute('SELECT * FROM events WHERE id=?', (event['id'],)).fetchone()
            if not row or row['status'] != 'claimed':
                return False
            device = self.db.execute('SELECT fingerprint FROM devices WHERE profile=? AND fingerprint=?', (row['profile'], row['fingerprint'])).fetchone()
            valid = row['expires'] > now and device and device['fingerprint'] == row['fingerprint']
            round_id = json.loads(row['payload']).get('roundId', row['id'])
            if valid and row['rule_id'] == 'tbtc-price':
                from tbtc_alert import valid_delivery
                valid = valid_delivery(self, row['profile'], json.loads(row['payload']))
            elif valid and row['rule_id'] in ('tbtc-mint','tbtc-backed-mint','tbtc-btc-deposit','tbtc-large-sale'):
                from tbtc_alert import deposit_delivery, mint_delivery, sale_delivery
                payload=json.loads(row['payload'])
                if row['rule_id']=='tbtc-large-sale':
                    valid=sale_delivery(self,row['profile'],payload,now)
                elif row['rule_id']=='tbtc-btc-deposit':
                    valid=deposit_delivery(self,row['profile'],payload,now)
                else:
                    valid=mint_delivery(self,row['profile'],payload,now,row['rule_id'])
                if valid is None:
                    self.db.execute("UPDATE events SET status='retry',next_at=? WHERE id=?",(now+5,row['id']))
                    return False
            elif valid and row['rule_id'] != 'test':
                saved = self.db.execute('SELECT config,state FROM rules WHERE id=? AND profile=?', (row['rule_id'], row['profile'])).fetchone()
                valid = bool(saved)
                if saved:
                    rule, state = json.loads(saved['config']), json.loads(saved['state'])
                    valid = rule['enabled'] and (not rule['expiresAt'] or now < rule['expiresAt'])
                    if valid and not rule['repeat'] and quotes is not None:
                        selected, effective, routing = select(rule, state, quotes, now, advance=False)
                        queued_source = json.loads(row['payload']).get('source')
                        valid = fresh(selected, effective['priceType'], now) and (not queued_source or source_key(queued_source) == source_key(routing.get('source')))
                        dispatched = self.db.execute("SELECT 1 FROM events WHERE profile=? AND rule_id=? AND attempts>0 AND COALESCE(json_extract(payload,'$.roundId'),id)=?", (row['profile'], row['rule_id'], round_id)).fetchone()
                        if not valid and not dispatched:
                            # A cancelled, never-sent one-shot must not remain permanently fired.
                            state.update(fired=False, gap=True, pending=None, status='stale')
                            self.db.execute('UPDATE rules SET state=? WHERE id=?', (dump(state), row['rule_id']))
                    if valid and rule['repeat']:
                        key = rule['exchange'], rule['market'], rule['symbol']
                        selected, effective, routing = select(rule, state, quotes, now, advance=False) if quotes is not None else (None, rule, state)
                        q = selected if quotes is not None else {rule['priceType']: state.get('price'), 'observedAt': state.get('observedAt', 0), rule['priceType']+'At': state.get('sampleAt', 0)}
                        try:
                            stamp = q.get(effective['priceType']+'At') or q['observedAt']
                            valid = (state.get('lastDispatchRound') == round_id or now >= state.get('lastDispatch', 0) + REPEAT_SECONDS) and -2 <= now-q['observedAt'] <= 12 and -2 <= now-stamp <= 12 and matches(rule, number(q.get(effective['priceType'])))
                            queued_source = json.loads(row['payload']).get('source')
                            actual_source = routing.get('source')
                            valid = valid and (not queued_source or source_key(queued_source) == source_key(actual_source))
                        except (ValueError, TypeError, KeyError, AttributeError):
                            valid = False
            if not valid:
                self.db.execute("UPDATE events SET status='cancelled',error='发送前条件已失效' WHERE id=?", (row['id'],))
                return False
            if row['rule_id'] not in ('test','tbtc-price','tbtc-mint','tbtc-backed-mint','tbtc-btc-deposit','tbtc-large-sale') and rule['repeat']:
                last = self.db.execute('SELECT at FROM device_dispatch WHERE rule_id=? AND fingerprint=?', (row['rule_id'], row['fingerprint'])).fetchone()
                if last and now < last['at'] + REPEAT_SECONDS:
                    self.db.execute("UPDATE events SET status='retry',next_at=? WHERE id=?", (last['at'] + REPEAT_SECONDS, row['id']))
                    return False
                self.db.execute('INSERT OR REPLACE INTO device_dispatch VALUES (?,?,?)', (row['rule_id'], row['fingerprint'], now))
                if state.get('lastDispatchRound') != round_id:
                    state.update(lastDispatch=now, lastDispatchRound=round_id)
                    self.db.execute('UPDATE rules SET state=? WHERE id=?', (dump(state), row['rule_id']))
            self.db.execute("UPDATE events SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            return True

    def finish(self, event, status, error=None):
        with self.lock, self.db:
            attempt = event['attempts'] + 1
            if status == 'retry' and attempt >= 3:
                status = 'failed'
            self.db.execute("UPDATE events SET status=?,error=?,next_at=? WHERE id=? AND status='sending'", (status, error, time.time() + 5 * 2 ** attempt, event['id']))
