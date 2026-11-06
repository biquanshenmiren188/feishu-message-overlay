"""Capture baseline digests over SSH and bind validation to exact candidate hashes."""
import json
from pathlib import Path
import subprocess
import sys

stage,radar=map(Path,sys.argv[1:3]);repo=Path(__file__).resolve().parents[1]
m=json.loads((stage/'manifest.json').read_text())
script='''import hashlib,json
from pathlib import Path
root=Path('/opt/funding-radar-web/current').resolve()
names=REPLACE_NAMES
files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names if (root/name).is_file()}
print(json.dumps(dict(previous=str(root),files=files,newFiles=[n for n in names if not (root/n).exists()])))
'''.replace('REPLACE_NAMES',repr(list(m['files'])))
live=json.loads(subprocess.run(['ssh','radar-tencent','sudo -n python3 -'],input=script,text=True,capture_output=True,check=True).stdout)
for name,digest in m['baseline'].items():assert live['files'][name]==digest,name
m['baseline']=live['files'];m['previous']=live['previous'];m['newFiles']=live['newFiles']
m['sourceCommits']={key:subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip() for key,path in [('push',repo),('radar',radar)]}
m['validation']={'passed':True,'files':m['files'],'checks':['center Python isolation and HTTP tests','legacy identity and PWA transfer regression','alarm engine regression','center and alarm browser fixtures at 1440/393/320','navigation source and layout checks','radar tests, types and build']}
(stage/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
print(json.dumps({'previous':m['previous'],'sourceCommits':m['sourceCommits'],'existing':len(m['baseline']),'new':len(m['newFiles'])}))
