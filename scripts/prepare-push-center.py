"""Patch a captured current release; preserve unrelated live overlays."""
import argparse
import hashlib
import json
from pathlib import Path
import re

VERSION='20261106-independent1'
LINKS=[('全市场费率','/radar/?tab=market'),('机会筛选','/radar/?tab=FF&amp;mode=FF'),('充提查询','/radar/?panel=transfer'),('HY限额查询','/radar/position-limits/'),('BOT','/radar/robot-push/'),('消息设置','/radar/robot-push/settings/'),('报警设置','/radar/robot-push/alarms/')]

def patch(raw, page):
    if page in ('main','HY限额查询'):
        raw=re.sub(r'<script[^>]+src="[^"\n]*shared-account\.js[^"\n]*"[^>]*></script>','',raw)
    pattern=r'<nav(?=[ >])[^>]*(?:class="site-nav"|aria-label="主导航")[^>]*>.*?</nav>'
    def nav(match):
        old=match.group();head=old[:old.index('>')+1];links=[]
        for i,(name,url) in enumerate(LINKS):
            attr=' aria-current="page"' if page in ('BOT','消息设置','报警设置','HY限额查询') and name==page else ''
            if '主导航' in head and i<3:attr+=' data-tab="'+['market','FF','transfer'][i]+'"'
            if page=='HY限额查询' and i==1:attr+=' id="opportunities"'
            links.append(f'<a href="{url}"{attr}>{name}</a>')
        return head+''.join(links)+'</nav>'
    raw=re.sub(pattern,nav,raw,flags=re.S)
    for name in ['position-limits-nav.js','shared-account.js','notification-settings.js']:
        raw=re.sub(re.escape(name)+r'(?:\?v=[^"\s]+)?',name+'?v='+VERSION,raw)
    for href in ['/radar/robot-push/shared-account.css','/radar/navigation-stable.css']:
        if href not in raw:raw=raw.replace('</head>',f'<link rel="stylesheet" href="{href}?v={'20261106-center2' if 'navigation-stable' in href else VERSION}"></head>')
    return raw

def sha(raw):return hashlib.sha256(raw).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('baseline',type=Path);ap.add_argument('radar',type=Path);ap.add_argument('out',type=Path);ap.add_argument('--source',action='store_true');args=ap.parse_args()
    repo=Path(__file__).resolve().parents[1];files={};baseline={}
    for local,remote,page in [('index.html','index.html','main'),('bot.html','robot-push/index.html','BOT'),('settings.html','robot-push/settings/index.html','消息设置'),('alarms.html','robot-push/alarms/index.html','报警设置'),('limits.html','position-limits/index.html','HY限额查询')]:
        raw=(args.baseline/local).read_bytes();baseline[remote]=sha(raw);files[remote]=patch(raw.decode(),page).encode()
    for name in ['shared-account.js','shared-account.css','notification-settings.js',]:
        files['robot-push/'+name]=(repo/'web/robot-push'/name).read_bytes().replace(b'\r\n',b'\n')
    for name in ['index.html','style.css','app.js']:
        files['push-center/'+name]=(repo/'web/push-center/public'/name).read_bytes().replace(b'\r\n',b'\n')
    for name in ['navigation-stable.css','position-limits-nav.js']:
        files[name]=(args.radar/'public'/name).read_bytes().replace(b'\r\n',b'\n')
    for name,raw in files.items():
        target=args.out/'static'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    backend={}
    for p in (repo/'web/push-center').glob('*'):
        if p.suffix not in ('.py','.service'):continue
        target=args.out/'backend'/p.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'));backend[p.name]=sha(target.read_bytes())
    manifest=dict(files={name:sha(raw) for name,raw in files.items()},baseline=baseline,backend=backend)
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if args.source:
        for path,page in [(repo/'web/robot-push/index.html','BOT'),(repo/'web/robot-push/settings/index.html','消息设置'),(repo/'web/robot-push/alarms/index.html','报警设置'),(args.radar/'public/position-limits/index.html','HY限额查询'),(args.radar/'standalone/index.html','main'),(args.radar/'standalone/startup-shell.html','main')]:
            path.write_text(patch(path.read_text(encoding='utf-8'),page),encoding='utf-8')
    print(json.dumps(dict(staticFiles=len(files),backendFiles=len(backend))))

if __name__=='__main__':main()
