"""Assemble only intended files from a captured live baseline, never rebuild old bundles."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('baseline',type=Path);parser.add_argument('radar',type=Path);parser.add_argument('out',type=Path)
    args=parser.parse_args();repo=Path(__file__).resolve().parents[1]
    files={}
    for name in ['shared-account.js','shared-account.css','notification-settings.js','settings-layout.js','settings/app.js','alarms/index.html','alarms/style.css','alarms/app.js']:
        files['robot-push/'+name]=(repo/'web/robot-push'/name).read_bytes().replace(b'\r\n',b'\n')
    files['radar-nav-b428fb6ffd4f.js']=(args.radar/'public/radar-nav-b428fb6ffd4f.js').read_bytes().replace(b'\r\n',b'\n')
    for source,destination in [('index.html','index.html'),('bot.html','robot-push/index.html'),('settings.html','robot-push/settings/index.html'),('hy.html','position-limits/index.html')]:
        raw=(args.baseline/source).read_text(encoding='utf-8')
        raw=re.sub(r'<script[^>]+src="[^"\n]*notification-settings\.js[^"\n]*"[^>]*></script>','',raw)
        raw=re.sub(r'<details class="mobile-account" id="mobile-account">.*?</details>','',raw)
        raw=raw.replace('</body>','<script type="module" src="/radar/robot-push/shared-account.js?v=20261106-2"></script></body>')
        raw=re.sub(r'(position-limits-nav\.js|settings-layout\.js|app\.js)\?v=[^"\s]+',r'\1?v=20261106-alarms1',raw) if source!='bot.html' else raw.replace('settings-layout.js?v=20261017-compact1','settings-layout.js?v=20261106-alarms1').replace('position-limits-nav.js?v=20261023-messages1','position-limits-nav.js?v=20261106-alarms1')
        raw=re.sub(r'/radar/position-limits-nav\.js(?:\?[^"]+)?', '/radar/radar-nav-b428fb6ffd4f.js', raw)
        files[destination]=raw.encode()
    for name,raw in files.items():
        p=args.out/'static'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    for p in (repo/'web/alarms').glob('*'):
        if p.suffix=='.py' or p.name.endswith('.service'):
            target=args.out/'backend'/p.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
    manifest={'files':{k:digest(v) for k,v in files.items()},'baseline':{k:digest((args.baseline/v).read_bytes()) for k,v in [('index.html','index.html'),('robot-push/index.html','bot.html'),('robot-push/settings/index.html','settings.html'),('position-limits/index.html','hy.html')]}}
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'staticFiles':len(files),'out':str(args.out)}))


if __name__=='__main__':main()
