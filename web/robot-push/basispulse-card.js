import {percent, money, assetName, safeRadar, number} from './basispulse-model.js?v=20261005b';
import {strategyCopy} from './basispulse-card-model.js?v=20261005b';
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const clock=value=>{const d=new Date(value);return Number.isFinite(+d)?d.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—';};
const numeric=v=>money(v).toLowerCase();
const metric=(label,value)=>{const n=el('div','bp-metric');n.append(el('span','',label),el('strong','',value));return n;};
function showDetails(title,text,opener) {
  const dialog=el('dialog','bp-dialog'), head=el('header'), close=el('button','','关闭');
  close.type='button';head.append(el('h2','',title),close);dialog.append(head,el('pre','',text));
  dialog.setAttribute('aria-label',title);document.body.append(dialog);
  close.onclick=()=>dialog.close();dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  dialog.addEventListener('close',()=>{dialog.remove();opener?.focus({preventScroll:true});});dialog.showModal();
}
export function cardNode(c, matrix) {
  const d=c.data, detail=d.details || {}, legs=detail.legs || [], card=el('article','bp-card');card.dataset.id=d.id;
  const rank=d.v2Residual?.level;card.dataset.rank=number(rank)?String(Math.min(3,Math.max(0,rank))):'unknown';
  const title=el('header','bp-card-head'), name=el('div','bp-name');name.append(el('h2','',assetName(d)),el('span','bp-strategy',d.strategy || '—'));
  const status=el('div','bp-live'),age=el('span','bp-age'), window=el('button','bp-window',`· ${d.trigger==='v2_price_window'?'V2收敛':d.trigger || '窗口'} ⓘ`);
  window.type='button';window.title='查看时间与窗口';window.dataset.action='window';
  window.onclick=()=>showDetails('时间与窗口',`进入时间：${clock(d.enteredAt)}\n更新时间：${clock(d.updatedAt)}\n有效至：${clock(d.validUntil)}\n窗口：${detail.windowSeconds ?? '—'} 秒\n有效秒数：${detail.validSeconds ?? '—'}\n达标秒数：${detail.okSeconds ?? '—'}${detail.early?'\n提前信号':''}`,window);
  status.append(age,window);
  title.append(name,status,el('div','bp-level',`R${number(rank)?rank:'—'} ${percent(d.v2Residual?.bps)}`));card.append(title);
  const legGrid=el('div','bp-legs');
  for(const [i,leg]of legs.entries()) {
    const row=el('section','bp-leg'), primary=el('div','bp-leg-main'), exchange=el('h3');
    exchange.append(el('span','bp-side',i===0?'买':'卖'),el('span','',`${String(leg.exchange || '').toUpperCase()} ${leg.spot?'现货':'永续'}`));
    exchange.title=leg.symbol || '';primary.append(exchange);
    const rate=el('div','bp-rate');rate.append(el('strong',leg.spot?'bp-na':'',leg.spot?'不适用':percent(leg.rate,.01)));
    if(!leg.spot)rate.append(el('span','bp-period',number(leg.hours)?`${leg.hours}h`:'—'));
    primary.append(rate);const stats=el('div','bp-leg-stats');stats.append(metric('24H',numeric(leg.volume)));
    if(!leg.spot)stats.append(metric('OI',numeric(leg.oi)));
    row.append(primary,stats);legGrid.append(row);
  }card.append(legGrid);
  const metrics=el('div','bp-metrics');
  for(const [label,key]of [['净收益均值','netBps'],['盘口差均值','marketBps'],['盘口差 P75','p75Bps'],['指数差均值','indexBps']]) {
    const v=percent(detail[key]), m=metric(label,key==='netBps'?v.replace(/^\+/,''):v);
    if(key==='indexBps'&&detail.spotIndex)m.append(el('small','','现货价代指数'));metrics.append(m);
  }card.append(metrics);
  const transfer=el('section','bp-transfer'), heading=el('div','bp-transfer-heading');
  heading.append(el('strong','','现货充提'),el('span','','充 / 提 · ✓开 ×关 ?未知 —无数据'));
  const noSpot=matrix.rows.filter(r=>r.noSpot).map(r=>r.exchange).join(' / ');if(noSpot)heading.append(el('span','',`${noSpot} 无现货`));
  transfer.append(heading);const table=el('table','bp-transfer-table');table.setAttribute('aria-label','链与充提状态');
  const thead=el('thead'),tr=el('tr');tr.append(el('th','','链'));for(const chain of matrix.chains)tr.append(el('th','',chain));thead.append(tr);table.append(thead);
  const tbody=el('tbody'),symbols={open:'✓',closed:'×',unknown:'?',none:'—',supported:'支持',delayed:'延迟',congested:'拥堵',restricted:'受限'},labels={open:'开放',closed:'关闭',unknown:'未知',none:'无现货',supported:'仅支持，未确认开放',delayed:'延迟',congested:'拥堵',restricted:'受限'};
  for(const row of matrix.rows){const tr=el('tr'),th=el('th','',row.exchange);th.scope='row';tr.append(th);
    row.cells.forEach((pair,index)=>{const td=el('td'),group=el('div','bp-transfer-pair');pair.forEach((s,i)=>{const cell=el('span',`bp-transfer-${s}`,symbols[s]);const label=`${row.exchange} ${matrix.chains[index]} ${i?'提现':'充值'}：${labels[s]}`;cell.title=label;cell.setAttribute('aria-label',label);group.append(cell);});td.append(group);tr.append(td);});tbody.append(tr);
  }table.append(tbody);transfer.append(table);
  const source=el('button','bp-source','雷达充提 · 查看来源');source.type='button';source.dataset.action='source';
  const uncertain=matrix.rows.some(r=>r.noSpot || r.cells.some(pair=>pair.includes('unknown'))) || /缓存|补充|未知/.test(matrix.text);
  if(uncertain){source.textContent='雷达充提 · 含未知状态 · 查看来源';source.classList.add('bp-warning');}
  source.onclick=()=>showDetails('现货充提来源',matrix.text || '接口暂未返回充提信息',source);source.title=source.textContent;source.textContent='充提来源';card.append(transfer);
  const footer=el('footer','bp-card-foot'), copy=el('button','','复制');copy.type='button';copy.dataset.action='copy';copy.title='复制 ASTRO-QUICK-COPY 代码';
  const payload=strategyCopy(d);copy.disabled=!payload;if(!payload)copy.title='当前组合不能安全生成策略代码，请使用雷达核对';
  copy.onclick=async()=>{try{await navigator.clipboard.writeText(payload);copy.textContent='已复制';copy.setAttribute('aria-label','策略代码已复制');}catch{showDetails('复制策略代码',payload,copy);}};
  footer.append(copy);const radar=safeRadar(d.radarUrl);if(radar){const link=el('a','bp-radar','雷达 ↗');link.href=radar;link.target='_blank';link.rel='noopener noreferrer';link.dataset.action='radar';footer.append(link);}
  const more=el('button','bp-more','···');more.type='button';more.dataset.action='more';more.setAttribute('aria-label','更多卡片信息');more.onclick=()=>showDetails('卡片信息',`数据来源：BasisPulse\n组合：${d.strategy} · ${assetName(d)}\n${legs.map((l,i)=>`${i?'卖':'买'}：${l.market} ${l.symbol}`).join('\n')}\n更新时间：${clock(d.updatedAt)}\n窗口：${detail.windowSeconds ?? '—'} 秒\n报价单位：USDT`,more);footer.append(source,more);card.append(footer);
  return {card,age,stamp:JSON.stringify([d,matrix])};
}
