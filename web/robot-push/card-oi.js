// OI shown under an active threshold comes from the same response as the decision.
const number=v=>typeof v==='number'&&Number.isFinite(v);
const money=v=>!number(v)?'—':v>=1e9?(v/1e9).toFixed(2)+'b':v>=1e6?(v/1e6).toFixed(2)+'m':v>=1e3?(v/1e3).toFixed(2)+'k':v.toFixed(2);
export function oiPresentation(evidence,{bound,fresh,now,exchange,spot,raw}){
  const unavailable={label:'OI',value:'—',title:'双边 OI 暂不可用'};
  if(!fresh||!evidence||evidence.exchange!==exchange||evidence.market!==(spot?'spot':'perp'))return unavailable;
  if(evidence.threshold!==null&&(!number(evidence.threshold)||evidence.threshold<0))return unavailable;
  const threshold=evidence.threshold===null?(bound?'本方案未设 OI 门槛':'公共双边 OI'):`门槛 ${evidence.threshold} 万 USDT`;
  if(evidence.status!=='ok'||evidence.basis!=='double-v1'||!number(evidence.value)||evidence.value<0||!number(evidence.time)||!number(evidence.expiresAt)||!number(evidence.checkedAt)||now>evidence.expiresAt||now-evidence.checkedAt>=10000||now<evidence.checkedAt-30000)return {...unavailable,title:`${threshold}；筛选 OI 缺失或过期`};
  return {label:'OI',value:money(evidence.value),title:`双边 OI ${evidence.value.toLocaleString('zh-CN',{maximumFractionDigits:2})} USDT · ${threshold} · 数据时间 ${new Date(evidence.time).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})} UTC+8`};
}
export function paintCardOI(card,data,state,now){
  const evidence=state.data?.oi?.[data.pair||data.id],fresh=!!state.data&&now-state.receivedAt<10000;
  const legs=data.details?.legs||[];
  card.querySelectorAll('.bp-leg').forEach((node,index)=>{
    const leg=legs[index];if(!leg||leg.spot)return;
    const metric=[...node.querySelectorAll('.bp-metric')].find(n=>/^(源 )?OI$/.test(n.querySelector('span')?.textContent||''));
    if(!metric)return;
    const label=metric.querySelector('span'),value=metric.querySelector('strong');if(!label||!value)return;
    const ex=String(leg.exchange||'').toLowerCase(),view=oiPresentation(evidence?.[index===0?'left':'right'],{bound:!!state.token,fresh,now,exchange:ex==='hl'||ex==='hy'?'hyperliquid':ex,spot:!!leg.spot});
    if(label.textContent!==view.label)label.textContent=view.label;
    if(value.textContent!==view.value)value.textContent=view.value;
    metric.title=view.title;metric.setAttribute('aria-label',view.title);
  });
}
