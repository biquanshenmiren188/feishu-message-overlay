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
const token=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
export function createPinHistory({element,renderCard}){
 let current=null,rows=[],identity=token(),epoch=0,controller=null,signature='',lastFetch=0,ready=true,following=true,resizing=false;
 element.classList.add('pin-history-scroll');element.tabIndex=0;
 element.setAttribute('aria-label','置顶消息，向上滚动查看最近5条');
 const observe=new ResizeObserver(()=>size());
 function size(){
  const first=[...element.children].find(n=>n.dataset.id===current?.id);if(!first){element.style.removeProperty('--pin-history-height');return;}
  const style=getComputedStyle(first),height=first.getBoundingClientRect().height+(parseFloat(style.marginTop)||0)+(parseFloat(style.marginBottom)||0);
  if(height>0)element.style.setProperty('--pin-history-height',height+'px');if(following)element.scrollTop=element.scrollHeight;
 }
 function anchor(){if(element.scrollHeight-element.clientHeight-element.scrollTop<=2)return null;const top=element.getBoundingClientRect().top,item=[...element.children].find(n=>n.getBoundingClientRect().bottom>top+1);return item?{id:item.dataset.id,offset:item.getBoundingClientRect().top-top}:null;}
 function render(){
  const messages=current?[...rows.filter(m=>m.id!==current.id).slice(0,4).sort((a,b)=>Date.parse(a.sentAt)-Date.parse(b.sentAt)),current]:[];
  const next=JSON.stringify(messages);if(next===signature){size();return;}
  const saved=anchor();following=!saved;signature=next;observe.disconnect();
  element.replaceChildren(...messages.map((m,index)=>{
   const node=renderCard(m);if(m.id!==current.id){const summary=node.querySelector('.summary-signals'),text=historySignals(m);if(summary&&text){summary.textContent=text;summary.title=text;}}
   return node;
  }));const detail=document.querySelector('#detail-content>.pin');if(detail&&!messages.some(m=>m.id===detail.dataset.id))document.querySelector('#message-detail')?.close();size();const latest=[...element.children].find(n=>n.dataset.id===current?.id);if(latest)observe.observe(latest);
  if(saved){const node=[...element.children].find(n=>n.dataset.id===saved.id);if(node)element.scrollTop+=node.getBoundingClientRect().top-element.getBoundingClientRect().top-saved.offset;else element.scrollTop=element.scrollHeight;}
  else element.scrollTop=element.scrollHeight;
 }
 function clear(){epoch++;controller?.abort();controller=null;rows=[];render();}
 function check(){const next=token();if(identity!==next){identity=next;clear();lastFetch=0;}return next;}
 async function refresh(){
  const auth=check();if(!current||controller||!ready||document.hidden)return;
  const own=++epoch,active=current.id;controller=new AbortController();const abort=controller;lastFetch=Date.now();
  const timer=setTimeout(()=>abort.abort(),8000);
  try{
   const response=await fetch('/radar/push-test/api/pinned-history',{headers:auth?{Authorization:'Bearer '+auth}:{},cache:'no-store',redirect:'error',signal:abort.signal});
   if(!response.ok)throw Error('history_unavailable');const data=await response.json(),result=historyRows(data);
   if(own!==epoch||token()!==auth||current?.id!==active)return;
   // Only attach an archive that belongs to the same current source snapshot.
   if(data.currentId!==active){rows=[];render();return;}
   rows=result;render();element.removeAttribute('data-history-error');
   element.title='向上滚动查看最近5条置顶消息（含当前）；历史不会补发或响铃';
  }catch{if(own===epoch){rows=[];render();element.dataset.historyError='true';element.title='置顶历史暂时无法读取，将自动重试；当前置顶不受影响';}}
  finally{clearTimeout(timer);if(own===epoch)controller=null;}
 }
 element.addEventListener('scroll',()=>{if(!resizing)following=element.scrollHeight-element.clientHeight-element.scrollTop<=2;},{passive:true});
 window.addEventListener('resize',()=>{resizing=true;requestAnimationFrame(()=>{size();resizing=false;});});
 const wake=()=>{check();if(current&&Date.now()-lastFetch>=3000)void refresh();};
 element.addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey)event.stopPropagation();},{passive:true});
 for(const name of ['touchstart','touchmove','touchend','touchcancel'])element.addEventListener(name,event=>event.stopPropagation(),{passive:true});
 element.addEventListener('keydown',event=>{if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End'].includes(event.key))event.stopPropagation();});
 window.addEventListener('storage',wake);window.addEventListener('focus',wake);
 document.addEventListener('radar-profile-changing',()=>{clear();ready=false;});
 document.addEventListener('radar-rules-saved',()=>{clear();lastFetch=0;});
 document.addEventListener('radar-feed-policy-snapshot',event=>{
  const next=!event.detail?.bound||event.detail?.ready===true;
  if(!next&&ready)clear();const changed=next!==ready;ready=next;if(changed&&next)wake();
 });
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});
 setInterval(wake,15000);
 return {
  setCurrent(message){const changed=JSON.stringify(current)!==JSON.stringify(message);if(changed){epoch++;controller?.abort();controller=null;}current=message;check();render();if(changed&&current)void refresh();},
  contains(id){return !!current&&(id===current.id||rows.some(m=>m.id===id));},
  clear
 };
}
