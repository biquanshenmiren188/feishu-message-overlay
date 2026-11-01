"""Prepare an incremental patch of the inspected live BOT/PWA, preserving overlays."""
import base64,hashlib,json,pathlib,re,subprocess,sys
def sha(raw):return hashlib.sha256(raw).hexdigest()
def once(raw,old,new):
 assert raw.count(old)==1,old
 return raw.replace(old,new)
def prepare(baseline,out):
 repo=pathlib.Path(__file__).resolve().parents[1];assert not out.exists()
 inv=json.loads((baseline/'manifest.json').read_text());back=json.loads((baseline/'backends.json').read_text())
 for name,h in inv['hashes'].items():assert sha((baseline/name).read_bytes())==h,name
 files={};sources={}
 for name in ('desktop_rules.py','server.py','signals.py'):
  installed=base64.b64decode(back['files'][name]);main=subprocess.check_output(['git','show','94ce57ec84583b616d1261c698d3c05d445dd636:web/push-test/'+name],cwd=repo)
  assert installed.replace(b'\r\n',b'\n')==main.replace(b'\r\n',b'\n'),'Inspect changed backend '+name
  raw=(repo/'web/push-test'/name).read_bytes();files[name]=raw;sources['web/push-test/'+name]=sha(raw.replace(b'\r\n',b'\n'))
 names=('feed-policy.js','feed-color.js','rule-events.js','card-manager.js','notification-settings.js','blocked-pushes.js','blocked-pushes.css')
 for name in names:
  raw=(repo/'web/robot-push'/name).read_bytes();files['robot-push/'+name]=raw;sources['web/robot-push/'+name]=sha(raw.replace(b'\r\n',b'\n'))
 for name in ('card-manager.js','notification-settings.js'):
  main=subprocess.check_output(['git','show','94ce57ec84583b616d1261c698d3c05d445dd636:web/robot-push/'+name],cwd=repo)
  assert (baseline/'robot-push'/name).read_bytes().replace(b'\r\n',b'\n')==main.replace(b'\r\n',b'\n'),name
 for name in ('page.js','card-policy.js','basispulse.js'):
  sources['web/robot-push/'+name]=sha((repo/'web/robot-push'/name).read_bytes().replace(b'\r\n',b'\n'))
 policy=(baseline/'robot-push/card-policy.js').read_bytes()
 files['robot-push/card-policy.js']=once(policy,b'card-manager.js?v=20261024-clarity1',b'card-manager.js?v=20261028-feed1')
 html=(baseline/'robot-push/index.html').read_bytes();old=re.findall(rb'/radar/(performance-[^"\s]+/bot-cards-[^"\s]+\.js)',html);assert len(old)==1;old=old[0].decode()
 out.mkdir(parents=True);temp=out/'bundle.tmp.js'
 subprocess.run(['node',str(repo/'scripts/patch-feed-bundle.cjs'),str(baseline/old),str(repo/'web/robot-push/page.js'),str(temp)],check=True)
 bundle=once(temp.read_bytes(),b'card-policy.js?v=20261028-oi2',b'card-policy.js?v=20261028-feed1');temp.unlink()
 new=str(pathlib.PurePosixPath(old).parent/('bot-feed-filter-'+sha(bundle)[:16]+'.js'));files[new]=bundle
 for name in ('robot-push/index.html','pwa-index.html'):
  raw=once((baseline/name).read_bytes(),old.encode(),new.encode())
  raw=once(raw,b'notification-settings.js?v=20261026-audit-c83d888c',b'notification-settings.js?v=20261028-feed1')
  raw=once(raw,b'blocked-pushes.js?v=20261025-1',b'blocked-pushes.js?v=20261028-feed1');files[name]=raw
 name='robot-push/settings/index.html'
 files[name]=once((baseline/name).read_bytes(),b'notification-settings.js?v=20261024-binding1',b'notification-settings.js?v=20261028-feed1')
 for name,raw in files.items():
  dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 plan=dict(sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),sourceFiles=sources,baselineCurrent=inv['release'],baselineHashes=inv['hashes'],backends=back['hashes'],fallbackHash=sha((baseline/'pwa-index.html').read_bytes()),bundle=new,stageHashes={n:sha(v) for n,v in files.items()})
 (out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8');print(json.dumps(dict(bundle=new,files=len(files))))
if __name__=='__main__':prepare(*map(pathlib.Path,sys.argv[1:]))
