"""Fan out new ordinary BOT messages using the existing per-plan decisions and Bark outbox."""
import hashlib
import json
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import site_tasks


def candidates(feed, since, now):
    if feed.get('sourceConnected') is not True:
        return []
    pinned = (feed.get('pinned') or {}).get('id')
    result = []
    for row in feed.get('messages', [])[:1000]:
        if row.get('senderType') != 'bot' or row.get('id') == pinned:
            continue
        fields = [row.get(k) for k in ('id','title','body','sentAt')]
        if not all(isinstance(v, str) for v in fields) or not fields[0]:
            continue
        try:
            stamp = datetime.fromisoformat(fields[3].replace('Z','+00:00')).timestamp()
        except (ValueError, OverflowError):
            continue
        if max(since,now-120) <= stamp <= now:
            digest = hashlib.sha256(json.dumps(fields,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            result.append((row,digest,stamp))
    return result


def enqueue(store, profile, rows, policy, now):
    if not policy.get('desktopEnabled'):
        return
    with store.lock, store.db:
        devices = store.db.execute('SELECT id, label, fingerprint FROM devices WHERE profile=?',(profile,)).fetchall()
        since = site_tasks.enabled_since('bot-bark')
        for row,digest,stamp in rows:
            decision = policy.get('decisions',{}).get(row['id'],{})
            if stamp < since or decision.get('action') != 'allow' or decision.get('fingerprint') != digest:
                continue
            for device in devices:
                inserted = store.db.execute('INSERT OR IGNORE INTO bot_bark_seen VALUES (?,?,?,?)',
                    (profile,device['fingerprint'],row['id'],stamp)).rowcount
                if inserted:
                    payload = dict(title=row['title'][:160] or 'BOT 消息',body=row['body'][:1000],
                                   group='BOT 普通消息',level='active',url='https://leida.shenmiren.work/radar/robot-push/')
                    store.event(profile,'bot-bark',payload,device,now)
        store.db.execute('DELETE FROM bot_bark_seen WHERE at<?',(now-86400,))


def setup(store):
    with store.lock,store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS bot_bark_seen (profile TEXT, device TEXT, message TEXT, at REAL, PRIMARY KEY(profile,device,message))')


def watch(store):
    setup(store)
    done = {}
    while True:
        try:
            now = time.time()
            since = site_tasks.enabled_since('bot-bark')
            if since <= now:
                with store.lock:
                    profiles = [r[0] for r in store.db.execute('SELECT DISTINCT profile FROM devices')]
                for profile in profiles:
                    prev_since, revision = done.get(profile,(None,''))
                    headers = {'If-None-Match':revision} if prev_since == since else {}
                    try:
                        req = Request('http://127.0.0.1:18885/internal/bot-bark/'+profile,headers=headers)
                        with urlopen(req,timeout=3) as response:
                            batch = json.loads(response.read(4000000))
                        rows = candidates(batch['feed'],since,time.time())
                        enqueue(store,profile,rows,batch['policy'],now)
                        done[profile] = since, batch['revision']
                    except HTTPError as exc:
                        if exc.code != 304:
                            print('bot bark policy:',exc.code,flush=True)
                        exc.close()
                    except (OSError, ValueError):
                        continue
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print('bot bark reader:',type(exc).__name__,flush=True)
        time.sleep(2)
