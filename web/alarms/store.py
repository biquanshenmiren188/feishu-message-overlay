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
from engine import evaluate, validate


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
            d = self.db.execute('SELECT label,fingerprint FROM devices WHERE profile=?', (profile,)).fetchone()
            rules = [dict(id=r['id'], **json.loads(r['config']), state=json.loads(r['state'])) for r in self.db.execute('SELECT * FROM rules WHERE profile=? ORDER BY created DESC', (profile,))]
            event_sql = "SELECT * FROM events WHERE profile=?" + (" AND rule_id='test' ORDER BY at DESC LIMIT 1" if compact else " ORDER BY at DESC LIMIT 100")
            events = [dict(json.loads(r['payload']), id=r['id'], ruleId=r['rule_id'], at=r['at'], status=r['status'], attempts=r['attempts'], error=r['error']) for r in self.db.execute(event_sql, (profile,))]
            return dict(revision=p['revision'], enabled=True, device=dict(label=d['label'], suffix=d['fingerprint'][-6:]) if d else None, rules=rules, events=events)

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
            where.append('status=?');args.append(status)
        if q:
            title="json_extract(payload,'$.title')"
            symbol=f"upper(substr({title},1,instr({title},' ')-1))"
            where.append(f'({symbol}=? OR {symbol}=?)');args.extend([q,q+'USDT'])
        sql=' FROM events WHERE '+' AND '.join(where)
        with self.lock:
            total=self.db.execute('SELECT count(*)'+sql,args).fetchone()[0]
            rows=self.db.execute("SELECT id,at,status,attempts,json_extract(payload,'$.title') AS title"+sql+' ORDER BY at DESC,id DESC LIMIT 20 OFFSET ?',[*args,(page-1)*20]).fetchall()
            return dict(items=[dict(r) for r in rows],total=total,page=page,pageSize=20,before=anchor)

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
                    self.db.execute('UPDATE rules SET config=?,state=? WHERE id=? AND profile=?', (dump(rule), '{}', identity, profile))
                    self.cancel(profile, identity)
                else:
                    if self.db.execute('SELECT count(*) FROM rules WHERE profile=?', (profile,)).fetchone()[0] >= 100:
                        raise ValueError('每个推送码最多 100 条报警')
                    identity = secrets.token_hex(16)
                    self.db.execute('INSERT INTO rules VALUES (?,?,?,?,?)', (identity, profile, dump(rule), '{}', now))
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
                owner = self.db.execute('SELECT profile FROM devices WHERE fingerprint=?', (fingerprint,)).fetchone()
                if owner and owner['profile'] != profile:
                    raise Conflict('该 Bark 设备已绑定其他推送码，请先在原码解除绑定')
                label = data.get('label', '我的 iPhone')
                if not isinstance(label, str) or not 1 <= len(label.strip()) <= 30:
                    raise ValueError('设备名称应为 1 至 30 字')
                self.cancel(profile)
                self.db.execute('INSERT OR REPLACE INTO devices VALUES (?,?,?,?)', (profile, fingerprint, self.cipher.encrypt(value.encode()).decode(), label.strip()))
            elif action == 'unbind':
                self.cancel(profile)
                self.db.execute('DELETE FROM devices WHERE profile=?', (profile,))
            elif action == 'test':
                device = self.db.execute('SELECT * FROM devices WHERE profile=?', (profile,)).fetchone()
                if not device:
                    raise ValueError('请先绑定 Bark')
                if self.db.execute("SELECT 1 FROM events WHERE profile=? AND rule_id='test' AND at>?", (profile, now - 60)).fetchone():
                    raise ValueError('请间隔一分钟再发送测试通知')
                self.event(profile, 'test', dict(title='雷达报警测试', body='这是一条手动测试通知。收到后，当前 Bark 设备即可用于价格报警。', group='雷达报警测试', level='critical', url='https://leida.shenmiren.work/radar/robot-push/alarms/'), device, now)
            else:
                raise ValueError('不支持的操作')
            self.db.execute('UPDATE profiles SET revision=revision+1 WHERE id=?', (profile,))
            result = dict(ok=True, revision=p['revision'] + 1, id=changed_id)
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)', (profile, request_id, digest, dump(result), now))
            # Retain idempotency responses for seven days; clients never silently replay older requests.
            self.db.execute('DELETE FROM requests WHERE at<?', (now - 7 * 86400,))
            return result

    def cancel(self, profile, identity=None):
        sql = "UPDATE events SET status='cancelled',error='规则或设备已变更' WHERE profile=? AND status IN ('queued','retry')"
        args = [profile]
        if identity:
            sql += ' AND rule_id=?'
            args.append(identity)
        self.db.execute(sql, args)

    def event(self, profile, identity, payload, device, now):
        event_id = secrets.token_hex(16)
        payload['id'] = event_id
        self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,0,?,?,?,?)', (event_id, profile, identity, now, dump(payload), 'queued' if device else 'no_device', now, now + 120, device['fingerprint'] if device else None, None if device else '未绑定 Bark，事件已记录'))

    def tick(self, quotes, now):
        active = set()
        with self.lock, self.db:
            rows = self.db.execute('SELECT * FROM rules').fetchall()
            for row in rows:
                rule = json.loads(row['config'])
                previous = json.loads(row['state'])
                key = rule['exchange'], rule['market'], rule['symbol']
                state, event = evaluate(rule, previous, quotes.get(key), now)
                if state['status'] not in ('paused', 'expired', 'triggered'):
                    active.add(key[:2])
                if state != previous:
                    self.db.execute('UPDATE rules SET state=? WHERE id=?', (dump(state), row['id']))
                if event:
                    names = dict(above='上穿', below='下穿', enter='进入区间', exit='离开区间')
                    price_kind = '最新成交价' if rule['priceType'] == 'last' else '标记价格'
                    clock = time.strftime('%m-%d %H:%M:%S', time.gmtime(now + 8 * 3600))
                    condition = rule['target'] + ('～' + rule['upper'] if rule['upper'] else '')
                    title = rule['symbol'] + ' ' + names[rule['condition']] + ' ' + condition
                    reason = '行情恢复时满足条件' if event['reason'] == 'recovery' else '启用时已满足条件' if event['reason'] == 'initial' else '价格穿越'
                    body = f"{rule['exchange'].upper()} · {'永续' if rule['market']=='future' else '现货'} · {price_kind}\n触发价格：{event['price']} USDT\n{reason} · 持续 {rule['hold']} 秒\n{clock}（北京时间）"
                    if rule['note']:
                        body += '\n' + rule['note']
                    payload = dict(title=title, body=body, group='雷达价格 · ' + rule['symbol'], level='critical', url='https://leida.shenmiren.work/radar/robot-push/alarms/?rule=' + row['id'], price=event['price'], sampleAt=event['sampleAt'], reason=event['reason'])
                    device = self.db.execute('SELECT * FROM devices WHERE profile=?', (row['profile'],)).fetchone()
                    self.event(row['profile'], row['id'], payload, device, now)
            self.db.execute("UPDATE events SET status='expired',error='超过两分钟发送时效' WHERE status IN ('queued','retry') AND expires<?", (now,))
            self.db.execute("DELETE FROM events WHERE at<? AND status NOT IN ('queued','retry','sending')", (now - 30 * 86400,))
        return active

    def claim(self):
        with self.lock, self.db:
            now = time.time()
            row = self.db.execute("SELECT e.*,d.secret FROM events e JOIN devices d ON e.profile=d.profile AND e.fingerprint=d.fingerprint WHERE e.status IN ('queued','retry') AND e.next_at<=? AND e.expires>? ORDER BY e.at LIMIT 1", (now, now)).fetchone()
            if not row:
                return None
            self.db.execute("UPDATE events SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            return dict(row)

    def finish(self, event, status, error=None):
        with self.lock, self.db:
            attempt = event['attempts'] + 1
            if status == 'retry' and attempt >= 3:
                status = 'failed'
            self.db.execute('UPDATE events SET status=?,error=?,next_at=? WHERE id=?', (status, error, time.time() + 5 * 2 ** attempt, event['id']))
