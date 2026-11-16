import pathlib,json,hashlib,subprocess
P=pathlib.Path
repo=P(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def prepare(base,graph,out):
 files={};hashes={};remote='/opt/funding-radar-web/releases/20261112-alarm-continuous-1794450201712590320'
 targets={'publisher-server.py':('/opt/robot-push/server.py','web/robot-push/publisher/server.py'),'cloud_receiver.py':('/opt/robot-push/cloud_receiver.py','web/robot-push/publisher/cloud_receiver.py'),'push-server.py':('/opt/radar-webpush-test/server.py','web/push-test/server.py')}
 for name,(target,source) in targets.items():
  old=(base/name).read_bytes();previous=subprocess.check_output(['git','show','415acdd:'+source],cwd=repo)
  assert old.decode().replace('\r\n','\n')==previous.decode().replace('\r\n','\n'),source
  hashes[target]=sha(old);files['backend/'+name]=(repo/source).read_bytes()
 files['backend/pin_history.py']=(repo/'web/robot-push/publisher/pin_history.py').read_bytes()
 bundle=graph/'performance-20261017/bot-reading-8789d8b685f6e827.js';s=bundle.read_text(encoding='utf-8');hashes[remote+'/performance-20261017/'+bundle.name]=sha(bundle.read_bytes())
 def once(a,b):
  nonlocal s
  assert s.count(a)==1,a;s=s.replace(a,b)
 once('H=y("pinned"),','H=y("pinned"),pinHistory=createPinHistory({element:H,renderCard:message=>lt(message,true)}),')
 once('H.replaceChildren(...(N.pinned?[lt(N.pinned,true)]:[]));','pinHistory.setCurrent(N.pinned);')
 once('for(const node of [...H.children])if(node.dataset.id!==N.pinned?.id)node.remove();','pinHistory.setCurrent(N.pinned);')
 once('if(z&&!allowed.has(z.focus)&&N.pinned?.id!==z.focus)','if(z&&!allowed.has(z.focus)&&!pinHistory.contains(z.focus))')
 s='import {createPinHistory} from "/radar/robot-push/pin-history.js?v=20261112-history2";let pinHistory;\n'+s
 name='performance-20261017/bot-pin-history-'+sha(s.encode())[:16]+'.js';files['static/'+name]=s.encode()
 for n in ['pin-history.js','pin-history.css']:files['static/robot-push/'+n]=(repo/'web/robot-push'/n).read_bytes()
 for n,target,dest in [('index.html',remote+'/robot-push/index.html','static/robot-push/index.html'),('fallback.html','/opt/radar-webpush-test/public/index.html','fallback/index.html')]:
  raw=(base/n).read_bytes();hashes[target]=sha(raw);html=raw.decode();assert bundle.name in html
  html=html.replace('置顶最新一条独立保留','置顶最近5条独立保留').replace('performance-20261017/'+bundle.name,name).replace('</head>','<link rel="stylesheet" href="/radar/robot-push/pin-history.css?v=20261112-history2"></head>');files[dest]=html.encode()
 for n,raw in files.items():p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 (out/'plan.json').write_text(json.dumps({'baseline':{'root':remote,'hashes':hashes},'files':{n:sha(v) for n,v in files.items()},'bundle':name},indent=2))
 print(name)
if __name__=='__main__':
 import sys
 prepare(P(sys.argv[1]),P(sys.argv[2]),P(sys.argv[3]))
