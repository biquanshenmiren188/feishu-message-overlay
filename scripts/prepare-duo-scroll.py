from pathlib import Path
import hashlib,json,re,sys
def prepare(root,out,source):
 sha=lambda b:hashlib.sha256(b).hexdigest()
 m=json.loads((root/'manifest.json').read_text());html=(root/'robot-push/index.html').read_bytes()
 old=re.search(rb'robot-push/bot-entry-layout-[a-f0-9]{16}\.css',html)[0]
 original=(root/old.decode()).read_bytes()
 css=(Path(__file__).resolve().parents[1]/'web/robot-push/bot-entry-layout.css').read_bytes()
 # This release only appends the touch-only override to the inspected live CSS.
 assert css.replace(b'\r\n',b'\n').startswith(original.replace(b'\r\n',b'\n').rstrip()+b'\n')
 name='robot-push/bot-entry-layout-'+sha(css)[:16]+'.css'
 def entry(raw):
  assert raw.count(old)==1
  return raw.replace(old,name.encode())
 files={name:css,'robot-push/index.html':entry(html)}
 fallback=(root/'fallback.html').read_bytes();newfallback=entry(fallback)
 for n,b in files.items():
  p=out/'static'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 (out/'fallback.html').write_bytes(newfallback)
 manifest=dict(previous=m['previous'],source=source,css=name,files={n:sha(b) for n,b in files.items()},newFiles=[name],baseline={'robot-push/index.html':sha(html)},fallbackBefore=sha(fallback),fallbackAfter=sha(newfallback))
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))
if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3])
