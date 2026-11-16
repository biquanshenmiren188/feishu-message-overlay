import {safeUrl} from './feed-color.js?v=20261028-feed1';

export function historyRows(data){
 if(!data||!Array.isArray(data.messages)||data.messages.length>5)throw Error('置顶历史格式无效');
 const seen=new Set();
 return data.messages.map(m=>{
  if(!m||typeof m.id!=='string'||typeof m.title!=='string'||m.title.length>1024||typeof m.body!=='string'||m.body.length>16000||!Number.isFinite(Date.parse(m.sentAt)))throw Error('置顶历史格式无效');
  if(seen.has(m.id))return null;seen.add(m.id);
  return {headerTone:['blue','red','green','orange','purple','indigo','turquoise','yellow','grey'].includes(m.headerTone)?m.headerTone:'grey',id:m.id,title:m.title,body:m.body,sentAt:m.sentAt,current:m.id===data.currentId,actions:(Array.isArray(m.actions)?m.actions:[]).slice(0,8).filter(a=>typeof a?.label==='string'&&safeUrl(a.url)).map(a=>({label:a.label,url:a.url}))};
 }).filter(Boolean).sort((a,b)=>Date.parse(b.sentAt)-Date.parse(a.sentAt));
}
export function historySignals(message){
 const lines=message.body.split(/\r?\n/).map(s=>s.trim()).filter(Boolean),rows=[];
 const short=name=>({GATE:'GT',BITGET:'BG',BINANCE:'BN',BYBIT:'BY',ASTER:'AS',OKX:'OK',HYPERLIQUID:'HY'})[name.toUpperCase()]||name;
 for(let i=0;i<lines.length;i++){
  const route=lines[i].match(/^(R\d+\+?)\s*[|｜]\s*(SF|FS|FF|SS)\s*[|｜]\s*买\s+(\S+).*?→\s*卖\s+(\S+)/u);
  if(!route)continue;
  const value=(lines[i+1]||'').match(/^V2收敛\s*·\s*[1-9]\d*秒\s*·\s*净均\s+([+−-]?\d+(?:\.\d+)?%)/u)?.[1];
  rows.push(`${route[1]}｜${route[2]}｜${short(route[3])}→${short(route[4])}${value?'｜'+value:''}`);
 }
 return rows.join('\n');
}
export function visiblePins(current,rows){
 const unique=new Map(rows.map(m=>[m.id,m]));if(current?.title.includes('强信号聚集'))unique.set(current.id,current);
 return [...unique.values()].sort((a,b)=>Date.parse(b.sentAt)-Date.parse(a.sentAt)).slice(0,5).reverse();
}
const token=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
export function createPinHistory({element,renderCard,onLayout=()=>{}}){
 let current=null,rows=[],identity=token(),epoch=0,controller=null,signature='',lastFetch=0,retry=null,following=true,resizing=false,lastHeight=0;
 // Two real scroll viewports: ordinary rows must never pass behind the pin.
 const board=element.parentElement;
 if(board?.id==='board')board.before(element);
 element.classList.add('pin-history-scroll');element.tabIndex=0;
 element.setAttribute('aria-label','置顶消息，向上滚动查看最近5条');
 const observe=new ResizeObserver(()=>size());
 function size(){
  const first=element.lastElementChild,style=first&&getComputedStyle(first);
  const height=first?first.getBoundingClientRect().height+(parseFloat(style.marginTop)||0)+(parseFloat(style.marginBottom)||0):0;
  if(height>0)element.style.setProperty('--pin-history-height',height+'px');else element.style.removeProperty('--pin-history-height');
  if(following)element.scrollTop=element.scrollHeight;
  if(height!==lastHeight){lastHeight=height;onLayout();}
 }
 function anchor(){if(element.scrollHeight-element.clientHeight-element.scrollTop<=2)return null;const top=element.getBoundingClientRect().top,item=[...element.children].find(n=>n.getBoundingClientRect().bottom>top+1);return item?{id:item.dataset.id,offset:item.getBoundingClientRect().top-top}:null;}
 function render(){
  const messages=visiblePins(current,rows);
  const next=JSON.stringify(messages);if(next===signature){size();return;}
  const saved=anchor();following=!saved;signature=next;observe.disconnect();
  element.replaceChildren(...messages.map((m,index)=>{
   const node=renderCard(m);if(m.id!==current?.id){const summary=node.querySelector('.summary-signals'),text=historySignals(m);if(summary&&text){summary.textContent=text;summary.title=text;}}
   return node;
  }));const detail=document.querySelector('#detail-content>.pin');if(detail&&!messages.some(m=>m.id===detail.dataset.id))document.querySelector('#message-detail')?.close();size();const latest=element.lastElementChild;if(latest)observe.observe(latest);
  if(saved){const node=[...element.children].find(n=>n.dataset.id===saved.id);if(node)element.scrollTop+=node.getBoundingClientRect().top-element.getBoundingClientRect().top-saved.offset;else element.scrollTop=element.scrollHeight;}
  else element.scrollTop=element.scrollHeight;
 }
 function clear(){epoch++;controller?.abort();controller=null;clearTimeout(retry);retry=null;rows=[];render();}
 function check(){const next=token();if(identity!==next){identity=next;current=null;clear();lastFetch=0;}return next;}
 async function refresh(){
  const auth=check();if(controller||document.hidden)return;
  clearTimeout(retry);retry=null;
  const own=++epoch;controller=new AbortController();const abort=controller;lastFetch=Date.now();
  const timer=setTimeout(()=>abort.abort(),8000);
  try{
   const response=await fetch('/radar/push-test/api/pinned-history',{headers:auth?{Authorization:'Bearer '+auth}:{},cache:'no-store',redirect:'error',signal:abort.signal});
   if(!response.ok)throw Error('history_unavailable');const data=await response.json(),result=historyRows(data);
   if(own!==epoch||token()!==auth)return;
   // This endpoint applies the account policy itself. The ordinary feed can
   // advance (or temporarily await its own policy) without invalidating history.
   rows=result;render();element.removeAttribute('data-history-error');
   element.title='向上滚动查看最近5条置顶消息（含当前）；历史不会补发或响铃';
  }catch{if(own===epoch){rows=[];render();element.dataset.historyError='true';element.title='置顶历史暂时无法读取，将自动重试；当前置顶不受影响';retry=setTimeout(()=>void refresh(),1000);}}
  finally{clearTimeout(timer);if(own===epoch)controller=null;}
 }
 element.addEventListener('scroll',()=>{if(!resizing)following=element.scrollHeight-element.clientHeight-element.scrollTop<=2;},{passive:true});
 window.addEventListener('resize',()=>{resizing=true;requestAnimationFrame(()=>{size();resizing=false;});});
 const wake=()=>{check();if(Date.now()-lastFetch>=3000)void refresh();};
 element.addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey)event.stopPropagation();},{passive:true});
 for(const name of ['touchstart','touchmove','touchend','touchcancel'])element.addEventListener(name,event=>event.stopPropagation(),{passive:true});
 element.addEventListener('keydown',event=>{if(!['ArrowUp','ArrowDown','PageUp','PageDown','Home','End'].includes(event.key))return;event.stopPropagation();if(event.target!==element)return;event.preventDefault();const steps={ArrowUp:-40,ArrowDown:40,PageUp:-element.clientHeight,PageDown:element.clientHeight};element.scrollTop=event.key==='Home'?0:event.key==='End'?element.scrollHeight:element.scrollTop+steps[event.key];});
 window.addEventListener('storage',wake);window.addEventListener('focus',wake);
 const invalidate=()=>{current=null;clear();lastFetch=0;queueMicrotask(()=>void refresh());};
 document.addEventListener('radar-profile-changing',invalidate);
 document.addEventListener('radar-rules-saved',invalidate);
 window.addEventListener('storage',event=>{if(event.key==='radar-rules-revision')invalidate();});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});
 setInterval(wake,15000);
 queueMicrotask(()=>void refresh());
 return {
  setCurrent(message){const changed=current?.id!==message?.id||current?.title!==message?.title||current?.body!==message?.body||current?.sentAt!==message?.sentAt;current=message;check();render();if(!lastFetch||(changed&&message&&!rows.some(row=>row.id===message.id&&row.title===message.title&&row.body===message.body&&row.sentAt===message.sentAt)))void refresh();},
  contains(id){return id===current?.id||rows.some(m=>m.id===id);},
  clear
 };
}
