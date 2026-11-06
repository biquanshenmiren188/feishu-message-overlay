"""Patch captured current HTML and exact source assets; never replace the main bundle."""
import hashlib,json,re,sys
from pathlib import Path

baseline,out=map(Path,sys.argv[1:3]);repo=Path(__file__).resolve().parents[1]
files={};before={}
for name in ['push-center/index.html','robot-push/alarms/index.html','robot-push/settings/index.html']:
    raw=(baseline/name).read_bytes();before[name]=hashlib.sha256(raw).hexdigest();text=raw.decode()
    if name=='robot-push/settings/index.html':
        text=re.sub(r'coin-list\.js\?v=[^"\s]+','coin-list.js?v=20261106-exact1',text)
        text=text.replace('placeholder="搜索币种"','placeholder="精准搜索完整币种"')
    else:
        source=repo/'web'/('push-center/public/index.html' if name.startswith('push-center/') else name)
        version=re.search(r'app\.js\?v=([^"\s]+)',source.read_text(encoding='utf-8')).group(1)
        text=re.sub(r'(app\.js)\?v=[^"\s]+',lambda m:m[1]+'?v='+version,text)
        text=text.replace('placeholder="搜索，例如 BTC"','placeholder="精准搜索，例如 BTC"').replace('placeholder="搜索币种或备注"','placeholder="精准搜索币种、交易对或完整备注"')
    files[name]=text.encode()
for dest,src in [('push-center/app.js','push-center/public/app.js'),('robot-push/alarms/app.js','robot-push/alarms/app.js'),('robot-push/alarms/search.js','robot-push/alarms/search.js'),('robot-push/settings/coin-list.js','robot-push/settings/coin-list.js')]:
    files[dest]=(repo/'web'/src).read_bytes().replace(b'\r\n',b'\n')
for name,data in files.items():
    p=out/'static'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
(out/'manifest.json').write_text(json.dumps(dict(files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},baseline=before),indent=2),encoding='utf-8')
print(json.dumps(dict(files=len(files))))
