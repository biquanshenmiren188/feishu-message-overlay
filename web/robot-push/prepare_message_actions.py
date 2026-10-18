import pathlib,json,re,hashlib,shutil
import argparse
parser=argparse.ArgumentParser(description='Prepare rank-first titles and bottom-right actions against an inspected production bundle.')
parser.add_argument('--baseline',type=pathlib.Path,required=True)
parser.add_argument('--candidate',type=pathlib.Path,required=True)
parser.add_argument('--preview',type=pathlib.Path,required=True)
args=parser.parse_args()
repo=pathlib.Path(__file__).resolve().parents[2]
base=args.baseline;out=args.candidate;preview=args.preview/'radar'
read=lambda p:p.read_text(encoding='utf-8')
sha=lambda s:hashlib.sha256(s.encode()).hexdigest()
baseline=json.loads(read(base/'manifest.json'));html=read(base/'robot-push/index.html')
old=re.search(r'src="/radar/([^" ]+/bot-[^" ]+\.js)"',html).group(1)
js=read(base/old);assert sha(js)==baseline['files'][old]['sha256']
helper=read(repo/'web/robot-push/display-title.mjs').replace('export function','function')
patches={
 'r.textContent=Xt(e).title||e.title||':'r.textContent=rankFirstTitle(Xt(e).title||e.title)||',
 'r.textContent=l.title||r.textContent':'r.textContent=rankFirstTitle(l.title||r.textContent)',
 'let p=document.createElement("span");p.className="detail-hint",p.textContent="\\u5168\\u6587 \\u203A",s.append(p),i.append(f)':'i.append(f)',
 'i.addEventListener("click",()=>an(e,t))':'i.addEventListener("click",h=>{if(h.target.closest("a,button"))return;an(e,t)})',
 'i.addEventListener("keydown",h=>{(h.key===':'i.addEventListener("keydown",h=>{if(h.target!==i)return;(h.key===',
}
for before,after in patches.items():
 assert js.count(before)==1,before
 js=js.replace(before,after)
js=helper+'\n'+js
name='performance-20261017/bot-summary-'+sha(js)[:12]+'.js'
files={name:js,'robot-push/index.html':html.replace('/radar/'+old,'/radar/'+name)}
oldcss=re.search(r'/radar/(performance-20261017/summary-risk-[^" ]+\.css)',html).group(1)
css=read(base/oldcss)+'\n/* All message actions, including expanded originals, align bottom-right. */\n.message>.actions{display:flex;justify-content:flex-end;flex-wrap:wrap;gap:4px;margin:3px 0 0;}\n'
cssname='performance-20261017/summary-risk-'+sha(css)[:12]+'.css'
files[cssname]=css
files['robot-push/index.html']=files['robot-push/index.html'].replace('/radar/'+oldcss,'/radar/'+cssname)
for n,s in files.items():
 p=out/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(s.encode())
(out/'manifest.json').write_text(json.dumps(dict(sourceRelease=baseline['release'],sourceHashes={},files={n:dict(sha256=sha(s),bytes=len(s.encode())) for n,s in files.items()})),encoding='utf-8')
shutil.copytree(base,preview,dirs_exist_ok=True)
for n,s in files.items():(preview/n).write_bytes(s.encode())
# Demo data is confined to the preview, never the publishable candidate.
samples=[('SAND｜FF｜OK→BG｜R5+ +0.65%','盘口差 +0.263%'),('APR｜SF｜BG→OK｜R1 +0.50%','盘口差 +0.409%'),('SAND｜FF｜BN→BY｜R0 +0.38%','盘口差 +0.505%\n警告：BY 1h 成本：资金费计算方式不同'),('ARC｜SF｜GT→BG｜R0 +0.48%','盘口差 +0.223%\n注意：BG：充关/提开 SOL'),('BEAT｜FF｜BG→BY｜R0 +0.39%','盘口差 +0.265%'),('TOKEN｜FF｜OK→BN｜R12+ -0.12%','盘口差 -0.025%')]
actions=[dict(label='查看组合',url='https://example.invalid/radar/?combo=fixture'),dict(label='查看雷达',url='https://example.invalid/radar/?q=fixture')]
messages=[dict(id='preview-'+str(i),groupId='demo',senderType='bot',title=t,body=b,actions=actions) for i,(t,b) in enumerate(samples)]
pinned=dict(id='preview-pin',groupId='demo-pin',senderType='bot',headerTone='red',title='强信号｜SAND｜3组',body='R1｜FF｜买 BINANCE → 卖 BYBIT\n净均 +0.70%\nR1｜FF｜买 BITGET → 卖 BYBIT\n净均 +0.61%\nR1｜FF｜买 GATE → 卖 BYBIT\n净均 +0.51%',actions=actions)
start=js.index('function Zt(');end=js.index('var en=M(',start)
fixture='function Zt(){const d='+json.dumps(dict(messages=messages,pinned=pinned),ensure_ascii=False)+';[d.pinned,...d.messages].forEach((m,i)=>m.sentAt=new Date(Date.now()-(7-i)*60000).toISOString());return d}'
(preview/name).write_text(js[:start]+fixture+js[end:],encoding='utf-8')
print(json.dumps(dict(preview=str(preview.parent),candidate=str(out),bundle=name)))
