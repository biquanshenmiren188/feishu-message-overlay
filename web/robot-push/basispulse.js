import {subscribePush} from './push-subscription.js';
import {mobileScrollGate,preserveCardViewport} from './mobile-scroll.js';
import {createCardPolicy} from './card-policy.js?v=20261028-oi1';
import { Opportunities, assetName, opportunityState } from './basispulse-model.js?v=20261025-retention1';
import { cardNode } from './basispulse-card.js?v=20261010gc1';
import { radarMatrix } from './basispulse-transfers.js?v=push-traffic-20261009';
document.body.classList.add('basis-mode');
const main = document.querySelector('#basis-pane') || document.querySelector('main');
const el = (tag, cls, text) => { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; };
const tools = el('div','bp-tools'), heading=el('h1',''), count=el('span','bp-count','0 ACTIVE');
const headingLink=el('a','bp-heading-link','卡片推送'); headingLink.href='https://basispulse.yielding.pro/trader#sent-history'; headingLink.target='_blank'; headingLink.rel='noopener noreferrer'; heading.append(headingLink,count); tools.append(heading);
const board=el('section','bp-board'); board.setAttribute('aria-label','BasisPulse 机会列表');
const empty=el('p','bp-empty','正在读取机会…');
main.append(tools,board,empty);
const model=new Opportunities(), nodes=new Map(); let envelope=null, failed=false;
// Commit ordinary card value changes together; connection recovery is immediate.
// Transfer evidence comes with the push; do not start per-coin API polling.
const DISPLAY_REFRESH_MS=10_000;
let lastValuesAt=-Infinity;
const time = value => { const d = new Date(value); return Number.isFinite(+d) ? d.toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : '—'; };
function duration(value, now) { const n=Math.max(0,Math.floor((now-Date.parse(value))/1000)); return Number.isFinite(n) ? n>=3600?`${Math.floor(n/3600)}h ${Math.floor(n%3600/60)}m`:n>=60?`${Math.floor(n/60)}m ${n%60}s`:`${n}s` : '—'; }
function render() {
  const deferStructure=mobileScrollGate.defer(render);
  return preserveCardViewport(board,()=>renderCards(deferStructure));
}
function renderCards(deferStructure) {
  const now=Date.now(), rows=model.tick(now),commitValues=now-lastValuesAt>=DISPLAY_REFRESH_MS;
  if(commitValues&&!deferStructure)lastValuesAt=now;
  const healthy=!failed && envelope?.status==='connected' && now-Date.parse(envelope.receivedAt)<20_000 && now-Date.parse(envelope.snapshot?.sampledAt)<20_000 && Date.parse(envelope.receivedAt)<=now+30000 && Date.parse(envelope.snapshot?.sampledAt)<=now+30000;
  const text=healthy ? `同步中 · 源时间 ${time(envelope.snapshot.sampledAt)} · UTC+8${envelope.snapshot.complete?'':' · 数据暂不完整'}` : envelope?.status==='auth_required' ? '接口授权失效 · 后台正在重试' : '正在自动重连 · 旧数据不计入活跃机会';
  count.title=text; count.setAttribute('aria-label',text);
  count.dataset.connected=String(healthy);
  const keep=new Set(); let active=0, shown=0;
  for(const c of rows) {
    if(!cardPolicy.visible(c.data)){nodes.get(c.data.id)?.card.remove();nodes.delete(c.data.id);continue;}
    const id=c.data.id, state=opportunityState(c,healthy,now), live=state==='active';
    if(live)active++;
    shown++; keep.add(id); let node=nodes.get(id);
    const matrix=radarMatrix(c.data.details?.legs || [],()=>null,now,c.data.details?.transferWallets || []);
    const matrixStamp=JSON.stringify(matrix);
    if(!deferStructure && (!node || node.matrixStamp!==matrixStamp || commitValues&&node.stamp!==JSON.stringify([c.data,matrix]))) {
      const focus=node?.card.contains(document.activeElement)?document.activeElement.dataset.action:null;
      const next=cardNode(c,matrix); next.card.dataset.pair=c.data.pair||''; cardPolicy.decorate(next.card,c.data); if(node)node.card.replaceWith(next.card); node=next;node.matrixStamp=matrixStamp; nodes.set(id,node);
      if(focus)node.card.querySelector(`[data-action="${focus}"]`)?.focus({preventScroll:true});
    }
    if(!node)continue;
    node.card.classList.toggle('bp-expired',!live); node.card.dataset.state=state; const ageText=live?`ACTIVE ${duration(c.data.enteredAt,now)}`:state==='expired'?'已失效':state==='pending'?'待确认':'待恢复';if(node.age.textContent!==ageText)node.age.textContent=ageText;
    const desired=board.children[shown-1]; if(!deferStructure && desired!==node.card)board.insertBefore(node.card,desired || null);
  }
  for(const [id,node]of nodes)if(!keep.has(id)){
    // The shared expiry deadline also applies while the user is scrolling.
    node.card.remove();nodes.delete(id);
  }
  count.textContent=`${active} ACTIVE`; if(!deferStructure)empty.hidden=shown>0;
  empty.textContent=healthy?'当前没有活跃机会':'正在连接数据源，恢复后自动显示';
  cardPolicy.summary(rows);
}
const cardPolicy=createCardPolicy(tools,render);
subscribePush('basispulse',{
  data(next){
    envelope=next;failed=false;model.ingest(envelope);
    render();
  },
  error(){failed=true;render();}
});
setInterval(()=>{if(!document.hidden)render()},1000);
