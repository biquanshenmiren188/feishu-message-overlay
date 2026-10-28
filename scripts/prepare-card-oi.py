"""Patch current production policy in place, preserving unmerged card preview UI."""
import base64,hashlib,json,pathlib,re,subprocess,sys
def digest(raw):return hashlib.sha256(raw).hexdigest()
def prepare(baseline,backend,out):
 repo=pathlib.Path(__file__).resolve().parents[1];assert not out.exists()
 plan=json.loads((baseline/'manifest.json').read_text(encoding='utf-8'));back=json.loads(backend.read_text(encoding='utf-8-sig'))
 files={};sources={}
 for name in ('advanced_rules.py','desktop_rules.py','server.py'):
  original=base64.b64decode(back['files'][name]);head=subprocess.check_output(['git','show','5401921f9622c411f9392335b7023cf67529491c:web/push-test/'+name],cwd=repo)
  assert original.replace(b'\r\n',b'\n')==head.replace(b'\r\n',b'\n'),'Inspect changed installed backend '+name
  raw=(repo/'web/push-test'/name).read_bytes();files[name]=raw;sources['web/push-test/'+name]=digest(raw.replace(b'\r\n',b'\n'))
 for name in ('card-policy.js','card-oi.js','basispulse.js'):
  raw=(repo/'web/robot-push'/name).read_bytes();sources['web/robot-push/'+name]=digest(raw.replace(b'\r\n',b'\n'))
  if name=='card-oi.js':files['robot-push/'+name]=raw
 policy=(baseline/'robot-push/card-policy.js').read_bytes()
 source=(repo/'web/robot-push/card-policy.js').read_text(encoding='utf-8')
 additions=[('import {openCardManager}',"import {paintCardOI} from './card-oi.js?v=20261028-1';\n"),('    for(const b of document.querySelectorAll(\'.bp-manage-rules\'))',source[source.index('    const byId='):source.index("    for(const b of document.querySelectorAll('.bp-manage-rules'))")]),('    if(card.querySelector(\'[data-action="manage-rules"]\'))return;', '    paintCardOI(card,data,state,Date.now());\n')]
 assert b"import {paintCardOI}" in policy
 replacements=[("card-oi.js?v=20261028-1","card-oi.js?v=20261028-2"),("if(busy||document.hidden||!auth)return;","if(busy||document.hidden)return;"),("fetch('/radar/push-test/api/card-decisions',{headers:{Authorization:'Bearer '+auth}","fetch('/radar/push-test/api/'+(auth?'card-decisions':'card-oi'),{headers:auth?{Authorization:'Bearer '+auth}:{}"),("state.accept(data,Date.now());","state.accept(auth?data:{revision:0,cardsEnabled:true,decisions:{},oi:data.oi},Date.now());")]
 for old,new in replacements:
  assert policy.count(old.encode())==1,old;policy=policy.replace(old.encode(),new.encode())
 files['robot-push/card-policy.js']=policy
 html=(baseline/'robot-push/index.html').read_bytes();old=re.findall(rb'/radar/(performance-[^"\s]+/bot-cards-[^"\s]+\.js)',html);assert len(old)==1
 old=old[0].decode();bundle=(baseline/old).read_bytes();needle=b'card-policy.js?v=20261028-oi1';assert bundle.count(needle)==1
 bundle=bundle.replace(needle,b'card-policy.js?v=20261028-oi2');new=str(pathlib.PurePosixPath(old).parent/('bot-cards-oi-'+digest(bundle)[:16]+'.js'));files[new]=bundle
 for name in ('robot-push/index.html','pwa-index.html'):
  raw=(baseline/name).read_bytes();assert raw.count(old.encode())==1;files[name]=raw.replace(old.encode(),new.encode())
 for name,raw in files.items():
  dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 report=dict(sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),sourceFiles=sources,baselineCurrent=plan['release'],baselineHashes=plan['hashes'],backends=back['hashes'],fallbackHash=digest((baseline/'pwa-index.html').read_bytes()),bundle=new,stageHashes={n:digest(v) for n,v in files.items()})
 (out/'plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(bundle=new,files=len(files))))
if __name__=='__main__':prepare(*map(pathlib.Path,sys.argv[1:]))
