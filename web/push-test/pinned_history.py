"""Filter source history before taking five; read-only and shared by web/desktop."""
import json,time
import urllib.request

def visible_history(policy=None):
    with urllib.request.urlopen('http://127.0.0.1:18883/pinned-history',timeout=5) as response:
        raw=response.read(16*1024*1024+1)
    if len(raw)>16*1024*1024:raise ValueError('history_size')
    source=json.loads(raw);rows=source['messages']
    if not isinstance(rows,list) or len(rows)>200:raise ValueError('history_count')
    visible=[];hidden=0;actions={}
    def select():
        nonlocal hidden
        now=time.time()
        for row in rows:
            action=(policy.decision('desktop',row['id'],policy.rows(row,now),now,record=False) or 'allow') if policy else 'allow'
            if action=='hide':hidden+=1;continue
            visible.append(row)
            if action=='mute':actions[row['id']]='mute'
            if len(visible)==5:break
    if policy:
        with policy.lock:select()
    else:select()
    return dict(messages=visible,currentId=visible[0]['id'] if visible else None,sourceCurrentId=source.get('currentId'),limit=5,hiddenCount=hidden,actions=actions)
