"""Patch current HTML only; never replace live feature bundles with repository snapshots."""
from pathlib import Path
import hashlib,json,sys

VERSION='20261113-mobile2'
PAGES=('index.html','position-limits/index.html','robot-push/index.html','robot-push/settings/index.html','robot-push/alarms/index.html','robot-push/alarms/history.html')
ASSETS=('robot-push/mobile-compact.css','robot-push/settings/mobile-compact.js')
def sha(b):return hashlib.sha256(b).hexdigest()
def integrate(raw,settings=False):
    text=raw.decode('utf-8')
    assert text.count('</head>')==1 and text.count('</body>')==1
    assert 'mobile-compact.css' not in text
    text=text.replace('</head>',f'<link rel="stylesheet" href="/radar/robot-push/mobile-compact.css?v={VERSION}"></head>')
    if settings:text=text.replace('</body>',f'<script src="/radar/robot-push/settings/mobile-compact.js?v={VERSION}"></script></body>')
    return text.encode()

def prepare(baseline,out,repo,source):
    old=json.loads((baseline/'baseline.json').read_text());manifest=dict(previous=old['previous'],source=source,files={},baseline={},newFiles=list(ASSETS),fallbackBefore=old['fallback'])
    for name in PAGES+ASSETS:
        if name in PAGES:
            raw=(baseline/name).read_bytes();assert sha(raw)==old['files'][name]
            manifest['baseline'][name]=sha(raw);raw=integrate(raw,name=='robot-push/settings/index.html')
        else:raw=(repo/'web'/name).read_bytes()
        path=out/'static'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);manifest['files'][name]=sha(raw)
    raw=integrate((baseline/'fallback.html').read_bytes());(out/'fallback.html').write_bytes(raw);manifest['fallbackAfter']=sha(raw)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]),Path(__file__).resolve().parents[1],sys.argv[3])
