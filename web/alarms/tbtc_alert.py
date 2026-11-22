"""Per-push-code tBTC alerts using the existing authenticated Bark outbox."""
import json
import re
import time
from decimal import Decimal
from pathlib import Path
from store import Conflict

SNAPSHOT = Path('/var/lib/radar-tbtc/public/quotes.json')
RULE = 'tbtc-price'


def initialize(store):
    with store.lock, store.db:
        store.db.execute("BEGIN IMMEDIATE")
        store.db.execute("""CREATE TABLE IF NOT EXISTS tbtc_price_alerts(
            profile TEXT PRIMARY KEY,target TEXT,revision INTEGER NOT NULL,last_sample TEXT,
            hits INTEGER NOT NULL DEFAULT 0, fired INTEGER NOT NULL DEFAULT 0)""")
        columns={r['name'] for r in store.db.execute('PRAGMA table_info(tbtc_price_alerts)')}
        for column in ('page_enabled','bark_enabled'):
            if column not in columns:
                store.db.execute(f'ALTER TABLE tbtc_price_alerts ADD COLUMN {column} INTEGER NOT NULL DEFAULT 1')


def sample(now):
    try:
        book = json.loads(SNAPSHOT.read_bytes())
        row = next(r for r in book['quotes'] if r['currency']=='cbBTC' and r['size']==1 and not r['reverse'])
        at, raw = row['at'], int(row['rawOut'])
        if raw > 0 and 0 <= now-at <= 9 and 0 <= now-book['time'] <= 9:
            return str(row['route'])+':'+str(at), Decimal(raw).scaleb(-18)
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        pass
    return None


def state(store, profile):
    with store.lock:
        row = store.db.execute('SELECT target,revision,page_enabled,bark_enabled FROM tbtc_price_alerts WHERE profile=?',(profile,)).fetchone()
        return dict(target=row['target'] if row else None, revision=row['revision'] if row else 0,
                    pageEnabled=bool(row['page_enabled']) if row else True,
                    barkEnabled=bool(row['bark_enabled']) if row else True, devices=len(store.device_list(profile)))


def configure(store, profile, data):
    target = data.get('target')
    if 'target' not in data or (target is not None and
            (not isinstance(target,str) or not re.fullmatch(r'[0-9]{1,8}(?:\.[0-9]{1,4})?',target) or Decimal(target)<=0)):
        raise ValueError('请输入大于零的目标兑换价，最多四位小数')
    with store.lock, store.db:
        old = state(store,profile)
        if type(data.get('revision')) is not int or data['revision'] != old['revision']:
            raise Conflict('设置已更新，请重新打开铃铛')
        page = data.get('pageEnabled',old['pageEnabled'])
        bark = data.get('barkEnabled',old['barkEnabled'])
        if type(page) is not bool or type(bark) is not bool:
            raise ValueError('提醒方式无效')
        if target != old['target'] or bark != old['barkEnabled']:
            store.cancel(profile,RULE)
            store.db.execute('INSERT OR REPLACE INTO tbtc_price_alerts(profile,target,revision,page_enabled,bark_enabled) VALUES(?,?,?,?,?)',
                             (profile,target,old['revision']+1,page,bark))
        elif page != old['pageEnabled']:
            store.db.execute("""INSERT INTO tbtc_price_alerts(profile,target,revision,page_enabled,bark_enabled) VALUES(?,?,?,?,?)
                                ON CONFLICT(profile) DO UPDATE SET revision=excluded.revision,page_enabled=excluded.page_enabled""",
                             (profile,target,old['revision']+1,page,bark))
        return state(store,profile)


def tick(store):
    now = time.time()
    with store.lock, store.db:
        rules = store.db.execute('SELECT * FROM tbtc_price_alerts WHERE target IS NOT NULL AND bark_enabled=1').fetchall()
        if not rules: return
        quote = sample(now)
        for r in rules:
            if not quote:
                if r['hits']:
                    store.db.execute('UPDATE tbtc_price_alerts SET hits=0,last_sample=NULL WHERE profile=?',(r['profile'],))
                continue
            stamp,price = quote
            if r['last_sample']==stamp: continue
            hits = min(2,r['hits']+1) if price>=Decimal(r['target']) else 0
            fired = bool(hits and r['fired'])
            if hits==2 and not fired:
                devices=store.db.execute('SELECT * FROM devices WHERE profile=?',(r['profile'],)).fetchall()
                payload=dict(title='tBTC 兑换价已达 '+r['target'],body=f'1 cbBTC ≈ {price:.4f} tBTC',
                             group='tBTC 价格报警',level='critical',url='https://leida.shenmiren.work/radar/tbtc/')
                for device in devices or [None]:
                    store.event(r['profile'],RULE,payload,device,now)
                fired=True
            if not hits and r['fired']: store.cancel(r['profile'],RULE)
            store.db.execute('UPDATE tbtc_price_alerts SET last_sample=?,hits=?,fired=? WHERE profile=?',
                             (stamp,hits,int(fired),r['profile']))


def valid_delivery(store, profile, now):
    row=store.db.execute('SELECT target,fired FROM tbtc_price_alerts WHERE profile=? AND bark_enabled=1',(profile,)).fetchone()
    quote=sample(now)
    return bool(row and row['target'] and row['fired'] and quote and quote[1]>=Decimal(row['target']))
