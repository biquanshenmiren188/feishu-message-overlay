"""Patch the observed live bundle without replacing unrelated production modules."""
from pathlib import Path
import hashlib,json,re,sys
repo=Path(__file__).resolve().parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def prepare(root,out,source):
    m=json.loads((root/'manifest.json').read_text());html=(root/'index.html').read_text(encoding='utf-8')
    old=re.search(r'performance-20261017/bot-pin-history-[a-f0-9]+\.js',html)[0]
    script=(root/'bundle.js').read_text(encoding='utf-8')
    before='const height=Math.max(120,bottom-o.getBoundingClientRect().top-footerHeight-safeBottom-4);'
    after='const height=matchMedia("(max-width:900px)").matches?ordinaryViewportHeight([...Y.children].map(el=>el.getBoundingClientRect()),parseFloat(getComputedStyle(o).paddingTop)||0):Math.max(120,bottom-o.getBoundingClientRect().top-footerHeight-safeBottom-4);'
    assert script.count(before)==1
    script='import {ordinaryViewportHeight} from "/radar/robot-push/feed-viewport.js?v=20261113-six1";\n'+script.replace(before,after)
    bundle='performance-20261017/bot-feed-six-'+sha(script.encode())[:16]+'.js'
    files={bundle:script.encode()}
    def patch(text):
        assert old in text and 'feed-viewport.css' not in text
        return text.replace(old,bundle).replace('</head>','<link rel="stylesheet" href="/radar/robot-push/feed-viewport.css?v=20261113-six1"></head>').encode()
    files['robot-push/index.html']=patch(html)
    for n in ('feed-viewport.js','feed-viewport.css'):files['robot-push/'+n]=(repo/'web/robot-push'/n).read_bytes()
    fallback=(root/'fallback.html').read_bytes();newfallback=patch(fallback.decode())
    for n,b in files.items():p=out/'static'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    (out/'fallback.html').write_bytes(newfallback)
    result=dict(previous=m['previous'],source=source,bundle=bundle,files={n:sha(b) for n,b in files.items()},baseline={'robot-push/index.html':m['files']['robot-push/index.html']},newFiles=[n for n in files if n!='robot-push/index.html'],fallbackBefore=sha(fallback),fallbackAfter=sha(newfallback))
    (out/'manifest.json').write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
