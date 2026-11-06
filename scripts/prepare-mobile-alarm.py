"""Keep live HTML overlays while aligning the alarm mobile toolbar."""
import hashlib,json,sys
from pathlib import Path
baseline,out=map(Path,sys.argv[1:3]);repo=Path(__file__).resolve().parents[1]
name='robot-push/alarms/index.html';raw=(baseline/name).read_bytes()
html=raw.replace(b'href="style.css?v=20261106-1"',b'href="style.css?v=20261106-mobile1"')
html=html.replace('精准搜索币种、交易对或完整备注'.encode(),'精准搜索币种或备注'.encode())
assert html!=raw
files={name:html,'robot-push/alarms/style.css':(repo/'web/robot-push/alarms/style.css').read_bytes().replace(b'\r\n',b'\n')}
for path,data in files.items():
 p=out/'static'/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
(out/'manifest.json').write_text(json.dumps(dict(files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()},baseline={name:hashlib.sha256(raw).hexdigest()}),indent=2),encoding='utf-8')
