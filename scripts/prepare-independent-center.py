"""Promote the center UI to its own public root, preserving captured live pages."""
import hashlib
import json
from pathlib import Path
import re
import sys

baseline,radar,out=map(Path,sys.argv[1:4]);repo=Path(__file__).resolve().parents[1]
files={};before={}
for name in ['index.html','position-limits/index.html','robot-push/index.html','robot-push/settings/index.html','robot-push/alarms/index.html']:
    raw=(baseline/name).read_bytes();before[name]=hashlib.sha256(raw).hexdigest()
    html=re.sub(r'/radar/position-limits-nav\.js(?:\?[^"]+)?', '/radar/radar-nav-b428fb6ffd4f.js', raw.decode())
    files[name]=re.sub(r'((?:shared-account\.(?:js|css)|position-limits-nav\.js))\?v=[^"\s]+',r'\1?v=20261106-independent1',html).encode()
for name in ['shared-account.js','notification-settings.js']:
    files['robot-push/'+name]=(repo/'web/robot-push'/name).read_bytes().replace(b'\r\n',b'\n')
for name in ['index.html','style.css','app.js']:
    files['push-center/'+name]=(repo/'web/push-center/public'/name).read_bytes().replace(b'\r\n',b'\n')
files['radar-nav-b428fb6ffd4f.js']=(radar/'public/radar-nav-b428fb6ffd4f.js').read_bytes().replace(b'\r\n',b'\n')
for name,raw in files.items():
    p=out/'static'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
(out/'manifest.json').write_text(json.dumps(dict(files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},baseline=before),indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files))))
