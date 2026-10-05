import { Opportunities, assetName, opportunityState } from './basispulse-model.js?v=20261005fill1';
import { cardNode } from './basispulse-card.js?v=20261006copy1';
import { radarMatrix, createRadarTransfers } from './basispulse-transfers.js?v=20261005fill1';
document.body.classList.add('basis-mode');
const main = document.querySelector('#basis-pane') || document.querySelector('main');
const el = (tag, cls, text) => { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; };
const tools = el('div','bp-tools'), heading=el('h1',''), count=el('span','bp-count','0 ACTIVE');
const headingLink=el('a','bp-heading-link','卡片推送'); headingLink.href='https://basispulse.yielding.pro/trader#sent-history'; headingLink.target='_blank'; headingLink.rel='noopener noreferrer'; heading.append(headingLink,count); tools.append(heading);
const board=el('section','bp-board'); board.setAttribute('aria-label','BasisPulse 机会列表');
const empty=el('p','bp-empty','正在读取机会…');
main.append(tools,board,empty);
const model=new Opportunities(), nodes=new Map(); let envelope=null, failed=false, failures=0, timer;
// Collect transfer updates silently; commit all visible card changes together.
const transfers=createRadarTransfers(()=>{});
const DISPLAY_REFRESH_MS=10_000;
let hasRendered=false;
const time = value => { const d = new Date(value); return Number.isFinite(+d) ? d.toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : '—'; };
function duration(value, now) { const n=Math.max(0,Math.floor((now-Date.parse(value))/1000)); return Number.isFinite(n) ? n>=3600?`${Math.floor(n/3600)}h ${Math.floor(n%3600/60)}m`:n>=60?`${Math.floor(n/60)}m ${n%60}s`:`${n}s` : '—'; }
function render() {
  const now=Date.now(), rows=model.tick(now);
  const healthy=!failed && envelope?.status==='connected' && now-Date.parse(envelope.receivedAt)<20_000 && now-Date.parse(envelope.snapshot?.sampledAt)<20_000;
  const text=healthy ? `同步中 · 源时间 ${time(envelope.snapshot.sampledAt)} · UTC+8${envelope.snapshot.complete?'':' · 数据暂不完整'}` : envelope?.status==='auth_required' ? '接口授权失效 · 后台正在重试' : '正在自动重连 · 旧数据不计入活跃机会';
  count.title=text; count.setAttribute('aria-label',text);
  count.dataset.connected=String(healthy);
  const keep=new Set(); let active=0, shown=0;
  for(const c of rows) {
    const id=c.data.id, state=opportunityState(c,healthy,now), live=state==='active';
    if(live)active++;
    shown++; keep.add(id); let node=nodes.get(id);
    const matrix=radarMatrix(c.data.details?.legs || [],transfers.get,now,c.data.details?.transferWallets || []);
    if(!node || node.stamp!==JSON.stringify([c.data,matrix])) {
      const focus=node?.card.contains(document.activeElement)?document.activeElement.dataset.action:null;
      const next=cardNode(c,matrix); if(node)node.card.replaceWith(next.card); node=next; nodes.set(id,node);
      if(focus)node.card.querySelector(`[data-action="${focus}"]`)?.focus({preventScroll:true});
    }
    node.card.classList.toggle('bp-expired',!live); node.card.dataset.state=state; node.age.textContent=live?`ACTIVE ${duration(c.data.enteredAt,now)}`:state==='expired'?'已失效':state==='pending'?'待确认':'待恢复';
    const desired=board.children[shown-1]; if(desired!==node.card)board.insertBefore(node.card,desired || null);
  }
  for(const [id,node]of nodes)if(!keep.has(id)){node.card.remove();nodes.delete(id);}
  count.textContent=`${active} ACTIVE`; empty.hidden=shown>0;
  empty.textContent=healthy?'当前没有活跃机会':'正在连接数据源，恢复后自动显示';
}
async function poll() {
  clearTimeout(timer);
  try {
    const r=await fetch('./basispulse.json',{credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(10_000)});
    if(!r.ok)throw new Error('fetch'); const next=await r.json();
    if(!next || !['connected','connecting','reconnecting','auth_required'].includes(next.status))throw new Error('schema');
    envelope=next; failed=false; failures=0; model.ingest(envelope);
  } catch { failed=true; failures++; }
  // Read the shared local cache often enough for the source's short validUntil.
  // This never increases upstream polling, which is owned by the single worker.
  if(!hasRendered){render();hasRendered=true;}
  timer=setTimeout(poll,failures ? Math.min(30_000,5000*2**Math.min(failures-1,3)) : 1000);
}
setInterval(render,DISPLAY_REFRESH_MS);
setInterval(()=>{void transfers.refresh(model.tick().flatMap(c=>c.data.details?.legs || []));},1000); poll();
