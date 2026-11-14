from pathlib import Path
import hashlib,json,sys
TARGETS=['index.html','position-limits/index.html','robot-push/index.html','push-center/index.html','robot-push/center/index.html','robot-push/alarms/history.html','robot-push/alarms/index.html','robot-push/settings/index.html']
def prepare(root,out,source,mainrepo,mainsource):
 sha=lambda b:hashlib.sha256(b).hexdigest()
 m=json.loads((root/'manifest.json').read_text())
 js=(Path(__file__).resolve().parents[1]/'web/robot-push/home-launch.js').read_bytes()
 css=(mainrepo/'public/radar-dialog-clearance.css').read_bytes()
 name='robot-push/home-launch-'+sha(js)[:16]+'.js';style='radar-dialog-clearance-'+sha(css)[:16]+'.css'
 tag=b'<script src="/radar/'+name.encode()+b'"></script>'
 def patch(raw,main=False):
  assert b'home-launch' not in raw and raw.count(b'</head>')==1
  # Install the click handler before the app; canonicalize legacy launch before rendering.
  result=raw.replace(b'<title>',tag+b'<title>',1)
  assert result!=raw
  return result.replace(b'</head>',b'<link rel="stylesheet" href="/radar/'+style.encode()+b'"></head>') if main else result
 files={name:js,style:css};before={}
 for n in TARGETS:
  raw=(root/n).read_bytes();before[n]=sha(raw);files[n]=patch(raw,n=='index.html')
 fallback=(root/'fallback.html').read_bytes()
 for n,b in files.items():
  p=out/'static'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 (out/'fallback.html').write_bytes(patch(fallback))
 manifest=dict(previous=m['previous'],source=source,mainSource=mainsource,js=name,css=style,files={n:sha(b) for n,b in files.items()},newFiles=[name,style],baseline=before,fallbackBefore=sha(fallback),fallbackAfter=sha(patch(fallback)))
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'files':len(files),'js':name,'css':style}))
if __name__=='__main__':prepare(Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4]),sys.argv[5])
