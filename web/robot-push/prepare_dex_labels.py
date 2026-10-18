"""Patch only the DEX route regex; preserve all current presentation overlays."""
import argparse,pathlib,re,json,hashlib,shutil
p=argparse.ArgumentParser()
p.add_argument('--baseline',type=pathlib.Path,required=True)
p.add_argument('--candidate',type=pathlib.Path,required=True)
p.add_argument('--preview',type=pathlib.Path,required=True)
a=p.parse_args();base=a.baseline;out=a.candidate;preview=a.preview/'radar'
repo=pathlib.Path(__file__).resolve().parents[2]
read=lambda p:p.read_text(encoding='utf-8')
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
manifest=json.loads(read(base/'manifest.json'));html=read(base/'robot-push/index.html')
old=re.search(r'src="/radar/([^" ]+/bot-[^" ]+\.js)"',html).group(1)
js=read(base/old);assert sha(js)==manifest['files'][old]['sha256']
before=r'多\s+(\S+)\s*[/／]\s*空\s+(\S+)\s*$'
after=r'多\s+(\S+)(?:\s+(?:现货|合约|永续))?\s*[/／]\s*空\s+(\S+)(?:\s+(?:现货|合约|永续))?\s*$'
assert js.count(before)==1;assert after in read(repo/'web/robot-push/summary.js')
js=js.replace(before,after)
name='performance-20261017/bot-summary-'+sha(js)[:12]+'.js'
files={name:js,'robot-push/index.html':html.replace('/radar/'+old,'/radar/'+name)}
for n,s in files.items():
 dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(s.encode())
(out/'manifest.json').write_text(json.dumps(dict(sourceRelease=manifest['release'],sourceHashes={},files={n:dict(sha256=sha(s),bytes=len(s.encode())) for n,s in files.items()})),encoding='utf-8')
shutil.copytree(base,preview,dirs_exist_ok=True)
for n,s in files.items():(preview/n).write_bytes(s.encode())
fixtures=json.loads(read(repo/'tests/Overlay.Core.Tests/summary-fixtures.json'))
sample=next(f['input'] for f in fixtures if f['name']=='DEX instrument labels on exchange legs still produce a compact summary')
message=dict(sample,id='fixture-dex',groupId='demo',senderType='bot',actions=[])
start=js.index('function Zt(');end=js.index('var en=M(',start)
fixture='function Zt(){const m='+json.dumps(message,ensure_ascii=False)+';m.sentAt=new Date().toISOString();return {messages:[m],pinned:null}}'
(preview/name).write_text(js[:start]+fixture+js[end:],encoding='utf-8')
print(json.dumps(dict(candidate=str(out),bundle=name)))
