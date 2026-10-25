"""Add a standalone viewer to the inspected live BOT and PWA entries."""
import hashlib,json,pathlib,subprocess,sys
TAG=b'<script type="module" src="/radar/robot-push/blocked-pushes.js?v=20261025-1"></script>'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def patch_html(raw):
    assert b'blocked-pushes.js' not in raw and raw.count(b'</body>')==1
    return raw.replace(b'</body>',TAG+b'</body>')
def prepare(baseline,out):
    repo=pathlib.Path(__file__).resolve().parents[1]
    assert not out.exists(),'Use a fresh output directory'
    plan=json.loads((baseline/'manifest.json').read_text(encoding='utf-8'))
    for name,value in plan['hashes'].items():assert digest((baseline/name).read_bytes())==value,name
    files={};sources={}
    for name in ['blocked-pushes.js','blocked-pushes.css','index.html']:
        raw=(repo/'web/robot-push'/name).read_bytes();sources['web/robot-push/'+name]=digest(raw.replace(b'\r\n',b'\n'))
        if name!='index.html':files['robot-push/'+name]=raw
    for name in ['robot-push/index.html','pwa-index.html']:files[name]=patch_html((baseline/name).read_bytes())
    for name,raw in files.items():
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    report=dict(sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),sourceFiles=sources,baselineCurrent=plan['release'],baselineHashes=plan['hashes'],fallbackHash=digest((baseline/'pwa-index.html').read_bytes()),stageHashes={n:digest(v) for n,v in files.items()})
    (out/'deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(files=len(files),baseline=plan['release'])))
if __name__=='__main__':prepare(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]))
