// Read existing per-code interception history. Never evaluate, resend, or change rules.
export function blockedRecords(data,channel){
 const rows=channel==='desktop'?data?.history:data?.blockedHistory;
 if(!Array.isArray(rows))throw Error('屏蔽记录暂时无法读取');
 const seen=new Set();return rows.filter(r=>r&&typeof r.id==='string'&&Array.isArray(r.reasons)&&(channel!=='desktop'||r.channel==='desktop'&&r.action==='hide')).filter(r=>{if(seen.has(r.id))return false;seen.add(r.id);return true;}).slice(0,200).sort((a,b)=>(Number(b.at)||0)-(Number(a.at)||0));
}
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const token=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
const clock=value=>Number.isFinite(value)&&value>0?new Date(value*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'时间未记录';
export function createBlockedPushes(toolbar){
 const style=el('link');style.rel='stylesheet';style.href='/radar/robot-push/blocked-pushes.css?v=20261025-1';document.head.append(style);
 const button=el('button','rp-blocked-entry','已屏蔽推送');button.type='button';button.setAttribute('aria-haspopup','dialog');toolbar.append(button);
 let identity='',epoch=0,controller=null,loading=false,cache=null,received=0,error='',dialog=null,active='desktop',request=0;
 function identityCheck(){const next=token();if(next!==identity){identity=next;epoch++;controller?.abort();controller=null;request++;loading=false;cache=null;received=0;error='';if(dialog){dialog.list.replaceChildren();dialog.root.close();}}return next;}
 // An open viewer is a dated snapshot; it stays still until the user refreshes.
 function fresh(){return cache&&(dialog||Date.now()-received<45000);}
 function paint(){
  button.disabled=!identity;button.textContent=fresh()?`已屏蔽 ${cache.desktop.length+cache.mobile.length} 条`:'已屏蔽推送';button.title=!identity?'连接自己的推送码后查看':error||'查看本推送码的电脑和手机屏蔽记录';
  if(!dialog)return;
  for(const [channel,b]of Object.entries(dialog.tabs)){b.setAttribute('aria-pressed',String(channel===active));b.textContent=(channel==='desktop'?'电脑推送':'手机推送')+(fresh()?` ${cache[channel].length}`:'');}
  dialog.refresh.disabled=loading;dialog.status.textContent=!identity?'请先连接自己的推送码':error||(!fresh()?'正在读取屏蔽记录…':`已读取 ${clock(received/1000)} · UTC+8`);
  if(!fresh()){dialog.list.replaceChildren();dialog.signature='';return;}
  const rows=cache[active],signature=active+'|'+JSON.stringify(rows);if(signature===dialog.signature)return;dialog.signature=signature;
  const content=rows.map(r=>{
   const article=el('article','rp-blocked-message'),head=el('header'),title=[r.rank,r.value,r.coin,r.mode,[r.buy,r.sell].filter(Boolean).join(' → ')].filter(Boolean).join(' | ');
   head.append(el('strong','',title||'未识别的推送'),el('time','',clock(r.messageAt||r.at)));article.append(head);
   article.append(el('p','rp-blocked-reasons',r.reasons.filter(x=>typeof x==='string').join('；')||'已被当时的规则屏蔽'));
   article.append(el('small','',`屏蔽时间 ${clock(r.at)}${Number.isInteger(r.revision)?' · 规则版本 '+r.revision:''}`));return article;
  });
  if(!content.length)content.push(el('p','rp-blocked-empty','当前没有此渠道的屏蔽记录。'));dialog.list.replaceChildren(...content);dialog.list.scrollTop=0;
 }
 async function refresh(){
  const auth=identityCheck();if(!auth||document.hidden||loading){paint();return;}const identityEpoch=epoch,id=++request;loading=true;error='';controller=new AbortController();const abort=controller;const timeout=setTimeout(()=>abort.abort(),8000);paint();
  try{
   const results=await Promise.all(['desktop-settings','status'].map(async route=>{const response=await fetch('/radar/push-test/api/'+route,{headers:{Authorization:'Bearer '+auth},cache:'no-store',redirect:'error',signal:abort.signal});if(!response.ok)throw Error(response.status===401||response.status===403?'连接已失效，请重新连接自己的推送码':'屏蔽记录读取失败，请重试');return response.json();}));
   if(id!==request||epoch!==identityEpoch||token()!==auth)return;
   cache={desktop:blockedRecords(results[0],'desktop'),mobile:blockedRecords(results[1],'mobile')};received=Date.now();
  }catch(e){if(id===request&&epoch===identityEpoch&&token()===auth){cache=null;received=0;error=e.name==='AbortError'?'读取超时，请重试':e.message||'屏蔽记录读取失败，请重试';}}
  finally{clearTimeout(timeout);if(id===request){loading=false;paint();}}
 }
 button.onclick=()=>{
  identityCheck();if(!identity||dialog){paint();return;}
  const root=el('dialog','rp-blocked-dialog'),head=el('header','rp-blocked-head'),close=el('button','','关闭'),title=el('h2','','已屏蔽推送');root.setAttribute('aria-label','已屏蔽推送');close.type='button';close.setAttribute('aria-label','关闭已屏蔽推送');head.append(title,close);
  const controls=el('div','rp-blocked-controls'),tabs={desktop:el('button','','电脑推送'),mobile:el('button','','手机推送')},reload=el('button','','刷新'),status=el('p','rp-blocked-status'),list=el('section','rp-blocked-list');status.setAttribute('role','status');list.setAttribute('aria-label','推送屏蔽记录');list.tabIndex=0;
  for(const [channel,b]of Object.entries(tabs)){b.type='button';b.onclick=()=>{active=channel;paint();};controls.append(b);}reload.type='button';reload.onclick=refresh;controls.append(reload);
  root.append(head,el('p','rp-blocked-help','仅查看，不解除屏蔽、不补发通知。按电脑和手机分别计数；每个渠道展示最近保留的记录。'),controls,status,list,el('p','rp-blocked-help','记录展示当时的信号摘要和屏蔽原因；修改规则后，旧记录仍会保留。仅静音不计入。'));
  document.body.append(root);dialog={root,tabs,refresh:reload,status,list,signature:''};close.onclick=()=>root.close();root.addEventListener('close',()=>{root.remove();dialog=null;button.focus({preventScroll:true});});paint();root.showModal();close.focus({preventScroll:true});void refresh();
 };
 const wake=()=>{identityCheck();paint();void refresh();};window.addEventListener('storage',wake);window.addEventListener('focus',wake);document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});document.addEventListener('radar-profile-changing',()=>{request++;loading=false;cache=null;received=0;controller?.abort();if(dialog){dialog.list.replaceChildren();dialog.root.close();}paint();});
 setInterval(()=>{identityCheck();if(!document.hidden)paint();},1000);
 // Open records stay still for reading; the explicit refresh button fetches updates.
 setInterval(()=>{if(!dialog)void refresh();},30000);wake();return {refresh};
}
if(typeof document!=='undefined'){const toolbar=document.querySelector('.feed-tools');if(toolbar)createBlockedPushes(toolbar);}
