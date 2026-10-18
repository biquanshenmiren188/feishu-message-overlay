"""Patch only radar action placement against an inspected production bundle."""
import argparse,pathlib,json,re,hashlib,shutil
p=argparse.ArgumentParser()
p.add_argument('--baseline',type=pathlib.Path,required=True)
p.add_argument('--candidate',type=pathlib.Path,required=True)
p.add_argument('--preview',type=pathlib.Path,required=True)
a=p.parse_args();base=a.baseline;out=a.candidate;preview=a.preview/'radar'
repo=pathlib.Path(__file__).resolve().parents[2]
read=lambda p:p.read_text(encoding='utf-8')
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
baseline=json.loads(read(base/'manifest.json'));html=read(base/'robot-push/index.html')
old=re.search(r'src="/radar/([^" ]+/bot-[^" ]+\.js)"',html).group(1)
js=read(base/old);assert sha(js)==baseline['files'][old]['sha256']
before='i.append(l)}return i}function an(e,t)'
assert js.count(before)==1
js=js.replace(before,'i.append(l)}placeRadarAction(i);return i}function an(e,t)')
js=read(repo/'web/robot-push/place-radar-action.mjs').replace('export function','function')+'\n'+js
name='performance-20261017/bot-summary-'+sha(js)[:12]+'.js'
oldcss=re.search(r'/radar/(performance-20261017/summary-risk-[^" ]+\.css)',html).group(1)
extra=read(repo/'web/robot-push/summary-risk.css').split('/* Radar action shares the spread row;')[1]
css=read(base/oldcss)+'\n/* Radar action shares the spread row;'+extra
cssname='performance-20261017/summary-risk-'+sha(css)[:12]+'.css'
files={name:js,cssname:css,'robot-push/index.html':html.replace('/radar/'+old,'/radar/'+name).replace('/radar/'+oldcss,'/radar/'+cssname)}
for n,s in files.items():
 dest=out/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(s.encode())
(out/'manifest.json').write_text(json.dumps(dict(sourceRelease=baseline['release'],sourceHashes={},files={n:dict(sha256=sha(s),bytes=len(s.encode())) for n,s in files.items()})),encoding='utf-8')
shutil.copytree(base,preview,dirs_exist_ok=True)
for n,s in files.items():(preview/n).write_bytes(s.encode())
# Fictional replay is isolated from candidate manifest files.
actions=[dict(label='查看组合',url='https://example.invalid/radar/?combo=fixture'),dict(label='查看雷达',url='https://example.invalid/radar/?q=fixture')]
samples=[('SAND｜FF｜OK→BG｜R5+ +0.65%','盘口差 +0.263%'),('APR｜SF｜BG→OK｜R1 +0.50%','盘口差 +0.409%'),('TOKEN｜FF｜BN→AS｜P3','盘口差 +0.3759% · 质量：样本少\n警告：成本结算更频繁：1h / 收入4h')]
messages=[dict(id='fixture-'+str(i),groupId='demo',senderType='bot',title=t,body=b,actions=actions) for i,(t,b) in enumerate(samples)]
pinned=dict(id='fixture-pin',groupId='pin',senderType='bot',headerTone='red',title='强信号｜SAND｜2组',body='R1｜FF｜买 BINANCE → 卖 BYBIT\n净均 +0.70%\nR0｜FF｜买 BITGET → 卖 BYBIT\n净均 +0.61%',actions=actions)
start=js.index('function Zt(');end=js.index('var en=M(',start)
fixture='function Zt(){const d='+json.dumps(dict(messages=messages,pinned=pinned),ensure_ascii=False)+';[d.pinned,...d.messages].forEach((m,i)=>m.sentAt=new Date(Date.now()-(4-i)*60000).toISOString());return d}'
(preview/name).write_text(js[:start]+fixture+js[end:],encoding='utf-8')
print(json.dumps(dict(candidate=str(out),bundle=name,css=cssname)))
