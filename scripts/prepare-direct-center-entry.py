"""Patch the four captured live headers, leaving all page content and overlays intact."""
import hashlib
import json
from pathlib import Path
import re
import sys

baseline,out=map(Path,sys.argv[1:3]);repo=Path(__file__).resolve().parents[1]
files={};before={}
for name in ['robot-push/index.html','robot-push/settings/index.html','robot-push/alarms/index.html','robot-push/center/index.html']:
    raw=(baseline/name).read_bytes();before[name]=hashlib.sha256(raw).hexdigest()
    patched=re.sub(r'(shared-account\.(?:js|css))\?v=[^"\s]+',r'\1?v=20261106-entry1',raw.decode()).encode()
    files[name]=patched
for name in ['shared-account.js','shared-account.css']:
    files['robot-push/'+name]=(repo/'web/robot-push'/name).read_bytes().replace(b'\r\n',b'\n')
for name,raw in files.items():
    p=out/'static'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
(out/'manifest.json').write_text(json.dumps(dict(files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},baseline=before),indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files))))
