"""Prepare incremental filtered-pin history fix from verified production code."""
import pathlib,json,hashlib,base64,subprocess,sys
P=pathlib.Path
repo=P(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def prepare(snapshot,out):
 data=json.loads(snapshot.read_text(encoding='utf-8'));root=data['root'];files={};hashes={};targets={}
 for path,encoded in data['files'].items():
  if encoded is None:hashes[path]=None;continue
  hashes[path]=sha(base64.b64decode(encoded))
 for folder,names in [('publisher',['server.py','pin_history.py','desktop_binding.py','state_delta.py']),('push-test',['server.py','desktop_binding.py','desktop_rules.py','signals.py','pinned_history.py'])]:
  for name in names:
   source=('web/robot-push/publisher/' if folder=='publisher' else 'web/push-test/')+name
   target=('/opt/robot-push/' if folder=='publisher' else '/opt/radar-webpush-test/')+name
   prior=data['files'][target]
   if prior is not None:
    expected=subprocess.check_output(['git','show','2d2836a:'+source],cwd=repo).decode().replace('\r\n','\n')
    assert base64.b64decode(prior).decode().replace('\r\n','\n')==expected,target
   staged='backend/'+folder+'-'+name;files[staged]=(repo/source).read_bytes();targets[staged]=target
 oldbundle='performance-20261017/bot-pin-history-2997cdc8b79ad276.js'
 s=base64.b64decode(data['files'][root+'/'+oldbundle]).decode()
 assert s.count('180秒')==1
 s=s.replace('180秒',r'[1-9]\d{0,5}秒').replace('pin-history.js?v=20261112-history2','pin-history.js?v=20261112-history3')
 bundle='performance-20261017/bot-pin-history-'+sha(s.encode())[:16]+'.js';files['static/'+bundle]=s.encode()
 files['static/robot-push/pin-history.js']=(repo/'web/robot-push/pin-history.js').read_bytes()
 files['static/robot-push/pin-history.css']=(repo/'web/robot-push/pin-history.css').read_bytes()
 for target,key in [(root+'/robot-push/index.html','static/robot-push/index.html'),('/opt/radar-webpush-test/public/index.html','fallback/index.html')]:
  html=base64.b64decode(data['files'][target]).decode();assert oldbundle in html
  files[key]=html.replace(oldbundle,bundle).replace('pin-history.css?v=20261112-history2','pin-history.css?v=20261112-history3').encode()
  if key.startswith('fallback'):targets[key]=target
 for n,raw in files.items():p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 (out/'plan.json').write_text(json.dumps(dict(baseline=dict(root=root,hashes=hashes),targets=targets,files={n:sha(v) for n,v in files.items()},bundle=bundle),indent=2))
 print(bundle)
if __name__=='__main__':prepare(P(sys.argv[1]),P(sys.argv[2]))
