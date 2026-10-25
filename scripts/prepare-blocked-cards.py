"""Patch only the inspected live policy wiring, preserving the existing card renderer."""
import hashlib,json,pathlib,sys,subprocess
EXPECTED='70a0144354ee7a6682af6a263e3f92e21a8a1385bbd0b8e7a28ded93f23d71c4'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def patch_bundle(raw):
    assert digest(raw)==EXPECTED,'Inspect changed production bundle before patching'
    source=raw.decode('utf-8')
    changes=[('card-policy.js?v=20261024-clarity1','card-policy.js?v=20261025-blocked1'),
      ('__cardPolicy=createCardPolicy(On,Nt);','__cardPolicy=createCardPolicy(On,Nt,{preserveViewport:__radarPreserve,renderCard:c=>Dn(c,Ln(c.data.details?.legs||[],()=>null,Date.now(),c.data.details?.transferWallets||[]))});')]
    for old,new in changes:
        assert source.count(old)==1,old
        source=source.replace(old,new)
    return source.encode('utf-8')
def prepare(baseline,out):
    repo=pathlib.Path(__file__).resolve().parents[1]
    assert not out.exists(),'Use a fresh candidate directory'
    plan=json.loads((baseline/'manifest.json').read_text(encoding='utf-8'))
    for name,value in plan['hashes'].items():assert digest((baseline/name).read_bytes())==value,name
    original='performance-20261017/bot-cards-70a0144354ee.js'
    raw=patch_bundle((baseline/original).read_bytes());bundle='performance-20261017/bot-cards-'+digest(raw)[:12]+'.js'
    files={bundle:raw};sourceFiles={}
    for name in ['card-policy.js','card-policy.css','basispulse.js']:
        data=(repo/'web/robot-push'/name).read_bytes();sourceFiles['web/robot-push/'+name]=digest(data.replace(b'\r\n',b'\n'))
        if name!='basispulse.js':files['robot-push/'+name]=data
    for name in ['robot-push/index.html','pwa-index.html']:
        data=(baseline/name).read_bytes();old=('/radar/'+original).encode();assert data.count(old)==1
        files[name]=data.replace(old,('/radar/'+bundle).encode())
    for name,data in files.items():
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    report=dict(sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),sourceFiles=sourceFiles,original=original,bundle=bundle,baselineCurrent=plan['release'],baselineHashes=plan['hashes'],fallbackHash=digest((baseline/'pwa-index.html').read_bytes()),stageHashes={name:digest(raw) for name,raw in files.items()})
    (out/'deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(bundle=bundle,files=len(files))))
if __name__=='__main__':prepare(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]))
