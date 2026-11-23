"""Per-push-code tBTC alerts using the existing authenticated Bark outbox."""
import json
import math
import re
import sqlite3
import time
from contextlib import closing
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from store import Conflict

SNAPSHOT = Path('/var/lib/radar-tbtc/public/quotes.json')
ROUND_HISTORY = SNAPSHOT.parent.parent / 'quote-rounds.sqlite'
RULE = 'tbtc-price'
MINT_RULE = 'tbtc-mint'
LARGE_RULE = 'tbtc-backed-mint'
DEPOSIT_RULE = 'tbtc-btc-deposit'
SALE_RULE = 'tbtc-large-sale'
SELLERS = SNAPSHOT.with_name('sellers.json')
DEPOSITS = SNAPSHOT.with_name('deposits.json')
SUPPLY = SNAPSHOT.with_name('supply.json')


def initialize(store):
    with store.lock, store.db:
        store.db.execute("BEGIN IMMEDIATE")
        store.db.execute("""CREATE TABLE IF NOT EXISTS tbtc_sale_webhooks(
            batch TEXT PRIMARY KEY, received REAL NOT NULL)""")
        store.db.execute("""CREATE TABLE IF NOT EXISTS tbtc_page_history(
            profile TEXT NOT NULL, at REAL NOT NULL, venue TEXT NOT NULL, target TEXT NOT NULL,
            price TEXT NOT NULL, PRIMARY KEY(profile,at,venue,target))""")
        store.db.execute("""CREATE TABLE IF NOT EXISTS tbtc_price_alerts(
            profile TEXT PRIMARY KEY,target TEXT,revision INTEGER NOT NULL,last_sample TEXT,
            hits INTEGER NOT NULL DEFAULT 0, fired INTEGER NOT NULL DEFAULT 0)""")
        columns={r['name'] for r in store.db.execute('PRAGMA table_info(tbtc_price_alerts)')}
        if 'sale_since' not in columns:
            store.db.execute('ALTER TABLE tbtc_price_alerts ADD COLUMN sale_since REAL')
        if 'sale_threshold' not in columns:
            store.db.execute("ALTER TABLE tbtc_price_alerts ADD COLUMN sale_threshold TEXT NOT NULL DEFAULT '5'")
        if 'round_cursor' not in columns:
            store.db.execute('ALTER TABLE tbtc_price_alerts ADD COLUMN round_cursor REAL NOT NULL DEFAULT 0')
            store.db.execute('UPDATE tbtc_price_alerts SET round_cursor=?',(time.time(),))
        store.db.execute("""CREATE TABLE IF NOT EXISTS tbtc_price_settings_history(
            profile TEXT NOT NULL, at REAL NOT NULL, target TEXT, bark INTEGER NOT NULL)""")
        for column in ('page_enabled','bark_enabled'):
            if column not in columns:
                store.db.execute(f'ALTER TABLE tbtc_price_alerts ADD COLUMN {column} INTEGER NOT NULL DEFAULT 1')
        if 'mint_since' not in columns:
            store.db.execute('ALTER TABLE tbtc_price_alerts ADD COLUMN mint_since REAL')
        if 'mint_threshold' not in columns:
            store.db.execute("ALTER TABLE tbtc_price_alerts ADD COLUMN mint_threshold TEXT NOT NULL DEFAULT '10'")
        if 'large_mint_since' not in columns:
            store.db.execute('ALTER TABLE tbtc_price_alerts ADD COLUMN large_mint_since REAL')
            store.db.execute("ALTER TABLE tbtc_price_alerts ADD COLUMN large_mint_threshold TEXT NOT NULL DEFAULT '30'")
        if 'quote_rank' not in columns:
            store.db.execute('ALTER TABLE tbtc_price_alerts ADD COLUMN quote_rank INTEGER DEFAULT 2')
            for row in store.db.execute('SELECT profile FROM tbtc_price_alerts').fetchall():
                store.cancel(row['profile'],RULE)
            store.db.execute('UPDATE tbtc_price_alerts SET hits=0,fired=0,last_sample=NULL')
        if 'deposit_since' not in columns:
            store.db.execute('ALTER TABLE tbtc_price_alerts ADD COLUMN deposit_since REAL')
            store.db.execute("ALTER TABLE tbtc_price_alerts ADD COLUMN deposit_threshold TEXT NOT NULL DEFAULT '30'")
        store.db.execute("""CREATE TABLE IF NOT EXISTS tbtc_mint_sent(
            profile TEXT NOT NULL, chain TEXT NOT NULL, tx TEXT NOT NULL,
            PRIMARY KEY(profile,chain,tx))""")
        if 'round_cursor' not in columns:
            store.db.execute("""INSERT INTO tbtc_price_settings_history
                SELECT profile,round_cursor,target,bark_enabled FROM tbtc_price_alerts""")


def sample(now):
    try:
        book = json.loads(SNAPSHOT.read_bytes())
        row = next(r for r in book['quotes'] if r['currency']=='cbBTC' and r['size']==1 and not r['reverse'])
        fallback = 'single' if row.get('venueCount')==1 else 'second'
        quote = row.get('selected') or row[fallback]
        at, raw = quote['at'], int(quote['rawOut'])
        if raw > 0 and 0 <= now-at < 9 and now<quote['validUntil'] and 0 <= now-book['time'] < 9:
            return Decimal(raw).scaleb(-18),quote['venue'],at,quote.get('mode',fallback)
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        pass
    return None


def state(store, profile):
    with store.lock:
        row = store.db.execute('SELECT * FROM tbtc_price_alerts WHERE profile=?',(profile,)).fetchone()
        return dict(target=row['target'] if row else None, revision=row['revision'] if row else 0,
                    saleEnabled=bool(row and row['sale_since'] is not None),
                    saleThreshold=row['sale_threshold'] if row else '5',
                    pageEnabled=bool(row['page_enabled']) if row else True,
                    barkEnabled=bool(row['bark_enabled']) if row else True, mintEnabled=bool(row and row['mint_since'] is not None),
                    mintThreshold=row['mint_threshold'] if row else '10',devices=len(store.device_list(profile)),
                    largeMintEnabled=bool(row and row['large_mint_since'] is not None),
                    largeMintThreshold=row['large_mint_threshold'] if row else '30',
                    depositEnabled=bool(row and row['deposit_since'] is not None),
                    depositThreshold=row['deposit_threshold'] if row else '30')


def record_page(store,profile,data):
    at,venue,raw=data.get('at'),data.get('venue'),data.get('rawOut')
    if (type(at) not in (float,int) or not math.isfinite(at) or not -10<=time.time()-at<=120
            or not isinstance(venue,str) or not 1<=len(venue)<=64 or not venue.isprintable()
            or not isinstance(raw,str) or not re.fullmatch(r'[0-9]{1,30}',raw)):
        raise ValueError('页面报警数据无效')
    price=Decimal(raw).scaleb(-18)
    with store.lock,store.db:
        config=state(store,profile)
        if config['pageEnabled'] and config['target'] and config['target']==data.get('target') and price>=Decimal(config['target']):
            store.db.execute('INSERT OR IGNORE INTO tbtc_page_history VALUES (?,?,?,?,?)',
                             (profile,at,venue,config['target'],format(price,'.4f')))
            store.db.execute('DELETE FROM tbtc_page_history WHERE profile=? AND at<?',(profile,time.time()-30*86400))
    return {'ok':True}


def history(store,profile,query):
    page=int(query.get('page',['1'])[0])
    before=float(query.get('before',[time.time()])[0])
    if not 1<=page<=100000 or not 0<before<=time.time()+60:
        raise ValueError('页码或查询时间无效')
    bounds=(profile,before-30*86400,before)
    sql="""WITH deliveries AS (
        SELECT at,rule_id,json_extract(payload,'$.title') title,json_extract(payload,'$.body') body,
               coalesce(json_extract(payload,'$.tx'),json_extract(payload,'$.outpoint'),'') ref,status,id
        FROM events WHERE profile=? AND at BETWEEN ? AND ? AND rule_id IN (?,?,?,?,?)
    ), alerts AS (
        SELECT at,rule_id,title,body,ref,json_group_array(status) statuses,json_group_array(id) ids FROM deliveries
        GROUP BY at,rule_id,title,body,ref
        UNION ALL SELECT at,'page','页面报价达标 · '||venue,'1 cbBTC ≈ '||price||' tBTC · 目标 '||target,'','[]','[]'
        FROM tbtc_page_history WHERE profile=? AND at BETWEEN ? AND ?
    ) SELECT at,rule_id,title,body,statuses,ids,COUNT(*) OVER () total FROM alerts
    ORDER BY at DESC,rule_id,title,body,ref LIMIT 6 OFFSET ?"""
    with store.lock:
        rows=store.db.execute(sql,(*bounds,RULE,MINT_RULE,LARGE_RULE,DEPOSIT_RULE,SALE_RULE,*bounds,(page-1)*6)).fetchall()
        items=[]
        for r in rows:
            item=dict(at=r['at'],kind=r['rule_id'],title=r['title'],body=r['body'],statuses=json.loads(r['statuses']))
            if r['rule_id']==SALE_RULE:
                item['sale']=sale_history(store,profile,r['ids'])
            items.append(item)
    return dict(before=before,total=rows[0]['total'] if rows else 0,pageSize=6,items=items)


def sale_history(store,profile,ids):
    devices=[]
    rows=store.db.execute("""SELECT e.payload,e.status,e.error,w.received FROM events e
        LEFT JOIN tbtc_sale_webhooks w ON w.batch=json_extract(e.payload,'$.scanBatch')
        WHERE e.profile=? AND e.id IN (SELECT value FROM json_each(?))
        ORDER BY json_extract(e.payload,'$.deviceLabel'),e.id""",(profile,ids))
    for row in rows:
        payload=json.loads(row['payload'])
        devices.append(dict(label=payload.get('deviceLabel'),status=row['status'],error=row['error'],
                            attempts=payload.get('barkAttempts',[])))
    return dict(tx=payload['tx'],seller=payload['seller'],amount=payload.get('sold'),
                tradedAt=payload.get('tradedAt'),scannedAt=payload.get('scannedAt'),
                trigger=payload.get('trigger'),webhookAt=row['received'],devices=devices)


def mint_threshold(value,label):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,8})?',value) or Decimal(value)<=0:
        raise ValueError(label+'须大于零，最多 8 位小数')
    return format(Decimal(value).normalize(),'f')

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
        mint = data.get('mintEnabled',old['mintEnabled'])
        sale = data.get('saleEnabled',old['saleEnabled'])
        sale_min=mint_threshold(data.get('saleThreshold',old['saleThreshold']),'单笔卖出阈值')
        sale_changed=(sale,sale_min)!=(old['saleEnabled'],old['saleThreshold'])
        minimum=mint_threshold(data.get('mintThreshold',old['mintThreshold']),'铸币缺口阈值')
        large=data.get('largeMintEnabled',old['largeMintEnabled'])
        large_min=mint_threshold(data.get('largeMintThreshold',old['largeMintThreshold']),'单笔正常铸币阈值')
        deposit=data.get('depositEnabled',old['depositEnabled'])
        deposit_min=mint_threshold(data.get('depositThreshold',old['depositThreshold']),'单笔 BTC 入金阈值')
        deposit_changed=(deposit,deposit_min)!=(old['depositEnabled'],old['depositThreshold'])
        if not all(type(x) is bool for x in (page,bark,mint,large,deposit,sale)):
            raise ValueError('提醒方式无效')
        large_changed=(large,large_min)!=(old['largeMintEnabled'],old['largeMintThreshold'])
        if not sale_changed and not deposit_changed and not large_changed and (target,page,bark,mint,minimum)==(old['target'],old['pageEnabled'],old['barkEnabled'],old['mintEnabled'],old['mintThreshold']):
            return old
        store.db.execute("""INSERT INTO tbtc_price_alerts(profile,target,revision,page_enabled,bark_enabled)
                            VALUES(?,?,?,?,?) ON CONFLICT(profile) DO UPDATE SET target=excluded.target,
                            revision=excluded.revision,page_enabled=excluded.page_enabled,bark_enabled=excluded.bark_enabled""",
                         (profile,target,old['revision']+1,page,bark))
        if sale_changed:
            store.db.execute('UPDATE tbtc_price_alerts SET sale_threshold=?,sale_since=? WHERE profile=?',
                             (sale_min,time.time() if sale else None,profile))
            store.cancel(profile,SALE_RULE)
        if target != old['target'] or bark != old['barkEnabled']:
            store.cancel(profile,RULE)
            changed=time.time()
            store.db.execute('UPDATE tbtc_price_alerts SET hits=0,fired=0,last_sample=NULL,round_cursor=? WHERE profile=?',(changed,profile))
            store.db.execute('INSERT INTO tbtc_price_settings_history VALUES(?,?,?,?)',(profile,changed,target,bark))
        if mint!=old['mintEnabled'] or minimum!=old['mintThreshold']:
            store.db.execute('UPDATE tbtc_price_alerts SET mint_threshold=? WHERE profile=?',(minimum,profile))
            store.db.execute('UPDATE tbtc_price_alerts SET mint_since=? WHERE profile=?',(time.time() if mint else None,profile))
            if not mint:store.cancel(profile,MINT_RULE)
        if large_changed:
            store.db.execute('UPDATE tbtc_price_alerts SET large_mint_threshold=?,large_mint_since=? WHERE profile=?',
                             (large_min,time.time() if large else None,profile))
            store.cancel(profile,LARGE_RULE)
        if deposit_changed:
            store.db.execute('UPDATE tbtc_price_alerts SET deposit_threshold=?,deposit_since=? WHERE profile=?',
                             (deposit_min,time.time() if deposit else None,profile))
            store.cancel(profile,DEPOSIT_RULE)
        return state(store,profile)


@lru_cache(maxsize=1)
def read_mints(path, inode, mtime):
    book=json.loads(path.read_bytes())
    ready={}
    flagged={}
    for chain in book['chains']:
        name=chain['name']
        if not chain['ok'] or chain.get('asset','tBTC')!='tBTC':continue
        ready[name]=chain['stamp']
        for r in chain.get('history',[]):
            key=r.get('tx') or r.get('eventId')
            eligible=r.get('kind')=='review' or (r.get('kind')=='matched' and r.get('tx'))
            if eligible and key and int(r['raw'])>0:
                flagged[name,key]=(r,chain['decimals'])
    return book['time'],ready,flagged


def mint_data(now):
    try:
        stat=SUPPLY.stat()
        stamp,ready,flagged=read_mints(SUPPLY,stat.st_ino,stat.st_mtime_ns)
        if 0<=now-stamp<180:return ready,flagged
    except (OSError,TypeError,ValueError,KeyError):
        pass
    return {},{}


def enqueue_mints(store,now):
    rules=store.db.execute('SELECT * FROM tbtc_price_alerts WHERE mint_since IS NOT NULL OR large_mint_since IS NOT NULL').fetchall()
    if not rules:return
    ready,flagged=mint_data(now)
    for (chain,tx),(record,decimals) in flagged.items():
        if not 0<=now-ready[chain]<180:continue
        detected=record.get('flaggedAt',record['time'])
        for rule in rules:
            profile=rule['profile']
            large=record['kind']=='matched'
            since=rule['large_mint_since'] if large else rule['mint_since']
            if since is None or detected<since or not eligible_amount(record,decimals,rule):continue
            key='backed:'+tx if large else tx
            inserted=store.db.execute('INSERT OR IGNORE INTO tbtc_mint_sent VALUES(?,?,?)',(profile,chain,key))
            if not inserted.rowcount:continue
            digits=str(int(record['raw'])).zfill(decimals+1)
            amount=(digits[:-decimals]+'.'+digits[-decimals:]).rstrip('0').rstrip('.') if decimals else digits
            clock=time.strftime('%m/%d %H:%M:%S',time.gmtime(record['time']+8*3600))
            detail=f"本笔铸币 {amount} tBTC" if record.get('tx') else f"链上总供应 {amount} tBTC"
            if str(record.get('eventId','')).startswith('unlogged-mint:'):detail=f"未匹配铸币日志的供应增量 {amount} tBTC"
            if not large and 'unbackedRaw' in record and record.get('tx') and not record.get('supplyLimit'):
                missing=Decimal(record['unbackedRaw']).scaleb(-decimals)
                detail+=f" · 入金缺口 {format(missing.normalize(),'f')} tBTC"
            reference="\n"+record['tx'] if record.get('tx') else ""
            label='单笔大额铸币' if large else '疑似异常铸币'
            payload=dict(title=chain+' '+label,body=f"{detail} · {clock}（北京）\n{record['reason']}{reference}",
                         group=('tBTC 大额铸币' if large else 'tBTC 异常铸币'),level='critical',url='https://leida.shenmiren.work/radar/tbtc/',
                         chain=chain,tx=tx)
            devices=store.db.execute('SELECT * FROM devices WHERE profile=?',(profile,)).fetchall()
            if not large:payload['url']+='#issuance'
            for device in devices or [None]:store.event(profile,LARGE_RULE if large else MINT_RULE,payload,device,now)


def meets_mint_threshold(record,decimals,minimum):
    raw=int(record.get('unbackedRaw',record['raw']))
    return raw>=int(Decimal(minimum)*10**decimals)

def eligible_amount(record,decimals,rule):
    if record['kind']=='matched':
        return int(record['raw'])>int(Decimal(rule['large_mint_threshold'])*10**decimals)
    return meets_mint_threshold(record,decimals,rule['mint_threshold'])

def mint_delivery(store,profile,payload,now,rule_id=MINT_RULE):
    subscribed=store.db.execute('SELECT * FROM tbtc_price_alerts WHERE profile=?',(profile,)).fetchone()
    large=rule_id==LARGE_RULE
    if not subscribed or subscribed['large_mint_since' if large else 'mint_since'] is None:return False
    ready,flagged=mint_data(now)
    if payload['chain'] not in ready or not 0<=now-ready[payload['chain']]<180:return None
    item=flagged.get((payload['chain'],payload['tx']))
    return bool(item and (item[0]['kind']=='matched')==large and eligible_amount(*item,subscribed))


@lru_cache(maxsize=1)
def read_deposits(path, inode, mtime):
    data=json.loads(path.read_bytes())
    return data['time'],{f"{r['txid']}:{r['vout']}":r for r in data['deposits']}


def deposit_data(now):
    try:
        stat=DEPOSITS.stat()
        stamp,rows=read_deposits(DEPOSITS,stat.st_ino,stat.st_mtime_ns)
        if 0<=now-stamp<180:return rows
    except (OSError,ValueError,TypeError,KeyError):
        pass
    return None


def qualifies_deposit(row,rule):
    return (row['status'] in ('confirmed','mempool') and row.get('verifiedAt',0)>=rule['deposit_since']
            and row['sats']>int(Decimal(rule['deposit_threshold'])*10**8))


def enqueue_deposits(store,now):
    rules=store.db.execute('SELECT profile,deposit_since,deposit_threshold FROM tbtc_price_alerts WHERE deposit_since IS NOT NULL').fetchall()
    if not rules:return
    for key,row in (deposit_data(now) or {}).items():
        for rule in rules:
            if not qualifies_deposit(row,rule):continue
            profile=rule['profile']
            inserted=store.db.execute("INSERT OR IGNORE INTO tbtc_mint_sent VALUES(?,'Bitcoin',?)",(profile,key))
            if not inserted.rowcount:continue
            amount=format(Decimal(row['sats']).scaleb(-8).normalize(),'f')
            status='BTC 已确认' if row['status']=='confirmed' else 'BTC 已广播，待打包'
            payload=dict(title=f'tBTC 入金 {amount} BTC',body=f"{status} · 单笔超过 {rule['deposit_threshold']} BTC\n存款人 {row['depositor']}",
                         group='tBTC 大额入金',level='critical',outpoint=key,
                         url=f"https://mempool.space/tx/{row['txid']}#vout={row['vout']}")
            devices=store.db.execute('SELECT * FROM devices WHERE profile=?',(profile,)).fetchall()
            for device in devices or [None]:store.event(profile,DEPOSIT_RULE,payload,device,now)


def deposit_delivery(store,profile,payload,now):
    rule=store.db.execute('SELECT deposit_since,deposit_threshold FROM tbtc_price_alerts WHERE profile=? AND deposit_since IS NOT NULL',(profile,)).fetchone()
    if not rule:return False
    rows=deposit_data(now)
    if rows is None:return None
    row=rows.get(payload['outpoint'])
    if row and row['status']=='unverified':return None
    return bool(row and qualifies_deposit(row,rule))


@lru_cache(maxsize=1)
def read_sales(path,inode,mtime):
    data=json.loads(path.read_bytes())
    return data['time'],{(r['tx'],r['address']):r for r in data['largeSales']}

def sale_data(now):
    try:
        stat=SELLERS.stat()
        stamp,rows=read_sales(SELLERS,stat.st_ino,stat.st_mtime_ns)
        if 0<=now-stamp<180:return rows
    except (OSError,ValueError,KeyError,TypeError):
        pass

def qualifies_sale(rule,row):
    return bool(rule and rule['sale_since'] is not None and row['time']>=rule['sale_since']
                and int(row['soldRaw'])>int(Decimal(rule['sale_threshold']).scaleb(18)))

def enqueue_sales(store,now,batch=None):
    rows=sale_data(now) or {}
    if batch and any(r.get('scanBatch')==batch for r in rows.values()):
        store.db.execute('INSERT OR IGNORE INTO tbtc_sale_webhooks VALUES(?,?)',(batch,now))
        store.db.execute('DELETE FROM tbtc_sale_webhooks WHERE received<?',(now-31*86400,))
    rules=store.db.execute('SELECT * FROM tbtc_price_alerts WHERE sale_since IS NOT NULL').fetchall()
    if not rules:return
    for (tx,seller),row in rows.items():
        for rule in rules:
            if not qualifies_sale(rule,row):continue
            profile=rule['profile']
            exists=store.db.execute("INSERT OR IGNORE INTO tbtc_mint_sent VALUES(?,?,?)",(profile,SALE_RULE,tx+seller))
            if not exists.rowcount:continue
            sold=format(Decimal(row['soldRaw']).scaleb(-18).normalize(),'f')
            clock=time.strftime('%H:%M:%S',time.gmtime(row['time']+28800))
            position='Aave 仓位' if row.get('source')=='aave' else '卖家'
            payload=dict(title=f'ETH 链上卖出 {sold} tBTC',body=f'{position} {seller} · {clock}（北京）',
                         tx=tx,seller=seller,sold=sold,tradedAt=row['time'],scannedAt=row.get('scannedAt'),
                         scanBatch=row.get('scanBatch'),trigger='webhook' if batch and row.get('scanBatch')==batch else 'poll',
                         group='tBTC 大额卖出',level='critical',url='https://etherscan.io/tx/'+tx)
            devices=store.db.execute('SELECT * FROM devices WHERE profile=?',(profile,)).fetchall()
            for device in devices or [None]:store.event(profile,SALE_RULE,payload,device,now)

def sale_delivery(store,profile,payload,now):
    rule=store.db.execute('SELECT sale_since,sale_threshold FROM tbtc_price_alerts WHERE profile=?',(profile,)).fetchone()
    if not rule or rule['sale_since'] is None:return False
    rows=sale_data(now)
    if rows is None:return None
    row=rows.get((payload['tx'],payload['seller']))
    return bool(row and qualifies_sale(rule,row))

def tick_chain(store):
    now = time.time()
    with store.lock, store.db:
        enqueue_sales(store,now)
        enqueue_deposits(store,now)
        enqueue_mints(store,now)


def price_rounds(reader, after, through):
    # Old rounds keep the policy in effect when they were collected. An empty
    # selection in a new round means the collector had no valid quote.
    legacy="""SELECT captured,CASE WHEN venues=1 THEN best_raw ELSE second_raw END AS raw,
              venue,quoted_at,CASE WHEN venues=1 THEN 'single' ELSE 'second' END AS mode
              FROM quote_rounds WHERE captured>? AND captured<=?"""
    bounds=(after,through)
    if reader.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quote_selection'").fetchone():
        legacy+=" AND NOT EXISTS (SELECT 1 FROM quote_selection s WHERE s.captured=quote_rounds.captured)"
        query="SELECT captured,raw,venue,quoted_at,mode FROM quote_selection WHERE captured>? AND captured<=? UNION ALL "+legacy
        bounds+=bounds
    else:
        query=legacy
    return reader.execute(query+" ORDER BY captured LIMIT 256",bounds).fetchall()


def tick_prices(store):
    now = time.time()
    with store.lock, store.db:
        rules = store.db.execute('SELECT * FROM tbtc_price_alerts WHERE target IS NOT NULL AND bark_enabled=1').fetchall()
        if not rules: return
        if ROUND_HISTORY.is_file():
            with closing(sqlite3.connect(ROUND_HISTORY.as_uri()+'?mode=ro',uri=True)) as reader:
                rounds=price_rounds(reader,min(r['round_cursor'] for r in rules),now)
            if not rounds:return
            samples=[(captured,Decimal(raw).scaleb(-18),venue,at,mode)
                     for captured,raw,venue,at,mode in rounds if raw is not None and venue and at is not None]
            through=rounds[-1][0]
        else:
            # Keep reading the live snapshot when running with the previous collector.
            quote=sample(now)
            if not quote:return
            samples=[(now,*quote)]
            through=now
        for rule in rules:
            if through<=rule['round_cursor']:continue
            fired=bool(rule['fired'])
            last=rule['last_sample']
            for captured,price,venue,at,mode in samples:
                if captured<=rule['round_cursor']:continue
                reached=price>=Decimal(rule['target'])
                if reached==fired:continue
                fired=reached
                last=f'{venue}:{at}'
                if reached:
                    clock=time.strftime('%H:%M:%S',time.gmtime(at+8*3600))
                    label={'okx':'OKX 优先报价','single':'单源最优价','second':'次优报价'}[mode]
                    payload=dict(title='tBTC '+label+'已达 '+rule['target'],
                                 body=f'触发时 1 cbBTC ≈ {price:.4f} tBTC · {venue} · {clock}（北京）',
                                 target=rule['target'],quoteAt=at,quotePrice=str(price),venue=venue,quoteMode=mode,
                                 group='tBTC 价格报警',level='critical',url='https://leida.shenmiren.work/radar/tbtc/')
                    devices=store.db.execute('SELECT * FROM devices WHERE profile=?',(rule['profile'],)).fetchall()
                    for device in devices or [None]:
                        store.event(rule['profile'],RULE,payload,device,now)
            store.db.execute('UPDATE tbtc_price_alerts SET last_sample=?,hits=?,fired=?,round_cursor=? WHERE profile=?',
                             (last,int(fired),int(fired),through,rule['profile']))


def tick(store):
    tick_prices(store)
    tick_chain(store)


def valid_delivery(store, profile, payload):
    row=store.db.execute('SELECT target FROM tbtc_price_alerts WHERE profile=? AND bark_enabled=1',(profile,)).fetchone()
    return bool(row and row['target'] and row['target']==payload.get('target'))
