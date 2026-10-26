"""Isolated live-cache check; never load credentials, send, or mutate real rules."""
import copy
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(sys.argv[1]).resolve()))
from advanced_rules import OISnapshot,DEFAULT,reasons
from desktop_rules import DesktopRules

now=time.time()
rows=[dict(coin='BULLA',buy='ASTER',sell=ex,mode='FF',rank='R1',value='0.8%') for ex in ('BINANCE','GATE')]
rule=dict(copy.deepcopy(DEFAULT),globalOI=50)
snap=OISnapshot();snap.enrich(rows,rule,now)
assert all(not reasons(row,rule) for row in rows),[(r['sell'],reasons(r,rule)) for r in rows]
report={'rows':[{'sell':r['sell'],'reasons':reasons(r,rule),'oi':r['oi']} for r in rows]}
with tempfile.TemporaryDirectory(prefix='aster-oi-validation-') as td:
    root=Path(td);feed=root/'feed.json';feed.write_text('{"messages":[]}')
    cards=[]
    for row in rows:
        cards.append(dict(id=row['sell'],pair='BULLA-'+row['sell'],asset='BULLA',strategy='FF',
                          validUntil=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
                          v2Residual=dict(level=1,bps=80),details=dict(legs=[dict(exchange='aster'),dict(exchange=row['sell'].lower())])))
    cardfile=root/'cards.json';cardfile.write_text(json.dumps(dict(snapshot=dict(complete=True,active=cards))))
    app=DesktopRules(root,feed,cardfile);state=app.status();settings=state['cards']['settings'];settings['advanced']=rule
    app.configure(dict(revision=state['revision'],channel='cards',settings=settings,action='hide'))
    app.oi.cache=copy.deepcopy(snap.cache);app.oi.at=copy.deepcopy(snap.at)
    web=app.web_cards();desktop=app.evaluate()
    assert set(web['decisions'].values())=={'allow'},web
    assert not desktop['cards'],desktop
    # Regression: a stale source must still block, and fresh recovery must allow.
    original=copy.deepcopy(app.oi.cache['aster'])
    app.oi.cache['aster']['aster:BULLAUSDT']['time']=(now-301)*1000
    assert set(app.web_cards()['decisions'].values())=={'hide'}
    app.oi.cache['aster']=original
    assert set(app.web_cards()['decisions'].values())=={'allow'}
    report.update(webDecisions=web['decisions'],desktopBlocked=desktop['cards'],staleAndRecoveryPassed=True)
report['candidateHash']=hashlib.sha256((Path(sys.argv[1])/'advanced_rules.py').read_bytes()).hexdigest()
print(json.dumps(report))
