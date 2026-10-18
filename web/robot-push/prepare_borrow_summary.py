"""Patch the inspected live summary only; retain all unrelated production overlays."""
import argparse,hashlib,json,pathlib,re,subprocess
p=argparse.ArgumentParser()
p.add_argument('--baseline',type=pathlib.Path,required=True)
p.add_argument('--candidate',type=pathlib.Path,required=True)
a=p.parse_args();base=a.baseline;out=a.candidate
sha=lambda data:hashlib.sha256(data).hexdigest()
manifest=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
html=(base/'robot-push/index.html').read_text(encoding='utf-8')
asset=re.search(r'src="/radar/([^" ]+/bot-[^" ]+\.js)"',html).group(1)
data=(base/asset).read_bytes();assert sha(data)==manifest['files'][asset]['sha256']
js=data.decode('utf-8')
replacements={
 r'\s*[/／]\s*空\s+(\S+)':r'\s*[/／]\s*(?:空|借卖)\s+(\S+)',
 'const block=lines.slice(entry.index+1,dex[i+1]?.index??lines.length),observed=':r'const next=lines.findIndex((line,index)=>index>entry.index&&/^\d+[.、)]/u.test(line));const block=lines.slice(entry.index+1,next<0?lines.length:next),observed='
}
for before,after in replacements.items():
 assert js.count(before)==1,'Changed production fragment; inspect again'
 js=js.replace(before,after)
name='performance-20261017/bot-summary-'+sha(js.encode())[:12]+'.js'
files={name:js,'robot-push/index.html':html.replace('/radar/'+asset,'/radar/'+name)}
for n,s in files.items():
 dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(s.encode())
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=pathlib.Path(__file__).resolve().parents[2],text=True).strip()
(out/'manifest.json').write_text(json.dumps(dict(sourceCommit=commit,sourceRelease=manifest['release'],sourceHashes={},files={n:dict(sha256=sha(s.encode()),bytes=len(s.encode())) for n,s in files.items()}),indent=2),encoding='utf-8')
print(json.dumps(dict(candidate=str(out),bundle=name,sourceCommit=commit)))
