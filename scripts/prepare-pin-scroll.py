"""Patch the observed live bundle, preserving every unrelated production asset."""
import pathlib,json,base64,hashlib,re,sys
P=pathlib.Path
repo=P(__file__).resolve().parents[1]
data=json.loads(P(sys.argv[1]).read_text(encoding='utf-8'));out=P(sys.argv[2]);root=data['root']
raw={p:base64.b64decode(b) for p,b in data['files'].items() if b is not None}
sha=lambda b:hashlib.sha256(b).hexdigest()
html=raw[root+'/robot-push/index.html'].decode()
old=re.search(r'performance-20261017/bot-pin-history-[a-f0-9]+\.js',html)[0]
s=raw[root+'/'+old].decode()
changes={
 'pin-history.js?v=20261112-history4':'pin-history.js?v=20261112-history5',
 'createPinHistory({element:H,renderCard:message=>lt(message,true)})':'createPinHistory({element:H,renderCard:message=>lt(message,true),onLayout:()=>{const atEnd=o.scrollHeight-o.clientHeight-o.scrollTop<=2;ct="";qe(true);if(atEnd){G();o.scrollTop=o.scrollHeight;}oe();ge();}})',
 'const required=Y.offsetHeight+H.offsetHeight':'const required=Y.offsetHeight;const available=o.clientHeight-(parseFloat(getComputedStyle(o).paddingTop)||0),end=Y.lastElementChild?.getBoundingClientRect().bottom;const first=[...Y.children].find(el=>end-el.getBoundingClientRect().top<=available);o.style.paddingBottom=required>available&&first?Math.max(0,available-(end-first.getBoundingClientRect().top))+"px":"0px"',
 'k.style.height=o.clientHeight+"px";':'k.style.top=o.offsetTop+"px";k.style.height=o.clientHeight+"px";'
}
for before,after in changes.items():
 assert s.count(before)==1,before
 s=s.replace(before,after)
bundle='performance-20261017/bot-pin-history-'+sha(s.encode())[:16]+'.js'
files={'static/'+bundle:s.encode()};targets={}
for name in ['pin-history.js','pin-history.css']:files['static/robot-push/'+name]=(repo/'web/robot-push'/name).read_bytes()
for target,name in [(root+'/robot-push/index.html','static/robot-push/index.html'),('/opt/radar-webpush-test/public/index.html','fallback/index.html')]:
 t=raw[target].decode();assert old in t
 assert 'pin-history.css?v=20261112-history3' in t
 files[name]=t.replace(old,bundle).replace('pin-history.css?v=20261112-history3','pin-history.css?v=20261112-history5').encode()
 if name.startswith('fallback'):targets[name]=target
for name,b in files.items():
 p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
(out/'plan.json').write_text(json.dumps({'baseline':{'root':root,'hashes':{p:sha(b) for p,b in raw.items()}},'targets':targets,'files':{n:sha(b) for n,b in files.items()},'bundle':bundle},indent=2))
print(bundle)
