import json,hashlib,pathlib,re
repo=pathlib.Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def prepare(base,out):
 inv=json.loads((base/'manifest.json').read_text());out.mkdir(parents=True,exist_ok=True);files={}
 for name,remote in [('signals.py','/opt/radar-webpush-test/signals.py'),('desktop_rules.py','/opt/radar-webpush-test/desktop_rules.py'),('cloud_receiver.py','/opt/robot-push/cloud_receiver.py')]:
  source=repo/('web/robot-push/publisher/' if name=='cloud_receiver.py' else 'web/push-test/')/name
  original=(base/'backend'/remote.replace('/','_')).read_text(encoding='utf-8')
  # Require the live backend to match the checked-in baseline before replacing it.
  import subprocess
  previous=subprocess.check_output(['git','show','HEAD:'+str(source.relative_to(repo)).replace('\\','/')],cwd=repo).decode()
  assert original.replace('\r\n','\n')==previous.replace('\r\n','\n'),name
  files['backend/'+name]=source.read_bytes()
 bundle=next((base/'performance-20261017').glob('*.js'));s=bundle.read_text(encoding='utf-8')
 def once(a,b):
  nonlocal s
  assert s.count(a)==1,a;s=s.replace(a,b)
 once('function lt(e,t=!1,n=!1){','function lt(e,t=!1,n=!1){const cluster=clusterCard(e,t,n,an);if(cluster)return cluster;')
 once('c.groupId!==this.pinned.groupId','(c.id!==this.pinned.id&&(c.groupId!==this.pinned.groupId||c.title.includes("强信号聚集")))')
 s=s.replace('180秒',r'[1-9]\d{0,5}秒')
 s=s.replace('feed-policy.js?v=20261028-1','feed-policy.js?v=20261112-cluster')
 s='import {clusterCard} from "/radar/robot-push/cluster-card.js?v=20261112";\n'+s
 name='performance-20261017/bot-cluster-'+sha(s.encode())[:16]+'.js';files['static/'+name]=s.encode()
 for n in ['feed-policy.js','feed-color.js','cluster-card.js','cluster-card.css']:
  raw=(repo/'web/robot-push'/n).read_text(encoding='utf-8').replace('feed-color.js?v=20261028-feed1','feed-color.js?v=20261112-cluster').encode();files['static/robot-push/'+n]=raw
 for source,target in [(base/'robot-push/index.html','static/robot-push/index.html'),(base/'backend/_opt_radar-webpush-test_public_index.html','fallback/index.html')]:
  html=source.read_text(encoding='utf-8');assert bundle.name in html
  html=html.replace('performance-20261017/'+bundle.name,name).replace('</head>','<link rel="stylesheet" href="/radar/robot-push/cluster-card.css?v=20261112b"></head>');files[target]=html.encode()
 for n,v in files.items():
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
 (out/'plan.json').write_text(json.dumps({'baseline':inv,'files':{n:sha(v) for n,v in files.items()},'bundle':name},indent=2))
 print(name)
if __name__=='__main__':
 import sys
 prepare(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]))
