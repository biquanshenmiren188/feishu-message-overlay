"""Patch the inspected deployed reader, preserving other production modules."""
from pathlib import Path
import json,re,hashlib,sys
repo=Path(__file__).resolve().parents[1]
sha=lambda b:hashlib.sha256(b).hexdigest()
def prepare(root,out,source):
 m=json.loads((root/'manifest.json').read_text());html=(root/'robot-push/index.html').read_text(encoding='utf8')
 old=re.search(r'performance-20261017/bot-feed-six-[a-f0-9]+\.js',html)[0]
 raw=(root/old).read_bytes();assert sha(raw)==m['files'][old]
 code=raw.decode();assert sha(raw)=='1e23bfcf51429fa36c89f8899276f4f21e974d7c565cc6e694cb605a4ba410dc'
 def one(a,b):
  nonlocal code
  assert code.count(a)==1,a;code=code.replace(a,b)
 one('const initialJump=dt&&d.ids.length>0;\n if(initialJump){dt=false;d.show(d.ids.at(-1));d.focus(d.window()[0],Date.now());}\n cn+=added.length;q();\n if(initialJump){const token=++ut;requestAnimationFrame(()=>requestAnimationFrame(()=>{if(token!==ut||d.paused||O||j)return;qe();G();o.scrollTop=o.scrollHeight;oe();ge();}));}', 'cn+=added.length;q();\n __entryPosition.update();')
 one('function ke(id=R()){dt=false;ut++;','function ke(id=R()){__entryPosition.cancel();')
 one('!ht&&Math.abs(e)>.5&&(ke(R()),','!ht&&Math.abs(e)>.5&&(O||j||ee)&&(ke(R()),')
 one('button.hidden=false;button.textContent=', '__entryPosition?.setAtTail(reached);button.hidden=false;button.textContent=')
 one('qe(layoutChanged);Ke();oe();ge();','qe(layoutChanged);Ke();oe();ge();__entryPosition?.update();')
 one('const height=matchMedia("(max-width:900px)").matches?ordinaryViewportHeight','const height=matchMedia("(max-width:1199px)").matches?ordinaryViewportHeight')
 one('o.title="";ge()});}function q(', 'o.title="";if(pane)document.querySelector("main").style.setProperty("--bot-feed-pane-height",pane.getBoundingClientRect().height+"px");ge()});}function q(')
 # Initialize only once all reader/gesture variables and DOM handles exist.
 init='__entryPosition=createEntryPosition({board:o,feed:Y,busy:()=>O||j||z||__radarScroll.active,prepare:()=>{d.configure(d.enabled,d.seconds,Date.now());d.show(d.ids.at(-1));d.focus(d.ids.at(-1),Date.now());qe(true);G();},settled:()=>{te=o.scrollTop;cn=0;Ke();oe();ge();L();}});'
 one('__webFeedPolicy=createFeedPolicy(fn,{publicOnly:Jn});',init+'__webFeedPolicy=createFeedPolicy(fn,{publicOnly:Jn});')
 helper=(repo/'web/robot-push/entry-position.js').read_bytes();css=(repo/'web/robot-push/bot-entry-layout.css').read_bytes()
 helpername='robot-push/entry-position-'+sha(helper)[:16]+'.js';cssname='robot-push/bot-entry-layout-'+sha(css)[:16]+'.css'
 code='import {createEntryPosition} from "/radar/'+helpername+'";let __entryPosition;\n'+code
 bundle='performance-20261017/bot-entry-'+sha(code.encode())[:16]+'.js'
 def entry(text):
  assert text.count(old)==1
  return text.replace(old,bundle).replace('</head>','<link rel="stylesheet" href="/radar/'+cssname+'"></head>').encode()
 files={bundle:code.encode(),helpername:helper,cssname:css,'robot-push/index.html':entry(html)}
 fallback=(root/'fallback.html').read_bytes();newfallback=entry(fallback.decode())
 for n,b in files.items():p=out/'static'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 (out/'fallback.html').write_bytes(newfallback)
 manifest=dict(previous=m['previous'],source=source,bundle=bundle,files={n:sha(b) for n,b in files.items()},baseline={'robot-push/index.html':m['files']['robot-push/index.html']},newFiles=[n for n in files if n!='robot-push/index.html'],fallbackBefore=sha(fallback),fallbackAfter=sha(newfallback))
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(dict(bundle=bundle,files=len(files))))
if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
