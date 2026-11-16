// View the current webpage's hidden messages and existing per-code history.
// Never evaluate rules, resend messages, or change rules from this viewer.
export function blockedRecords(data,channel){
 const rows=channel==='desktop'?data?.history:data?.blockedHistory;
 if(!Array.isArray(rows))throw Error('屏蔽记录暂时无法读取');
 const seen=new Set();return rows.filter(r=>r&&typeof r.id==='string'&&Array.isArray(r.reasons)&&(channel!=='desktop'||r.channel==='desktop'&&r.action==='hide')).filter(r=>{if(seen.has(r.id))return false;seen.add(r.id);return true;}).slice(0,200).sort((a,b)=>(Number(b.at)||0)-(Number(a.at)||0));
}
export function webpageRecords(snapshot){
 if(snapshot?.bound!==true||snapshot.ready!==true||!Array.isArray(snapshot.blocked))return null;
 const seen=new Set();return snapshot.blocked.filter(r=>r&&typeof r.id==='string'&&r.id.length<=256&&typeof r.title==='string'&&r.title.length<=1024&&typeof r.body==='string'&&r.body.length<=16000&&Number.isFinite(Date.parse(r.sentAt))).filter(r=>{if(seen.has(r.id))return false;seen.add(r.id);return true;}).slice(0,101).map(({id,title,body,sentAt})=>({id,title,body,sentAt})).sort((a,b)=>Date.parse(b.sentAt)-Date.parse(a.sentAt));
}
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const token=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
const clock=value=>Number.isFinite(value)&&value>0?new Date(value*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'时间未记录';
export function createBlockedPushes(toolbar){
 const style=el('link');style.rel='stylesheet';style.href='/radar/robot-push/blocked-pushes.css?v=20261028-1';document.head.append(style);
 const button=el('button','rp-blocked-entry','已屏蔽推送');button.type='button';button.setAttribute('aria-haspopup','dialog');toolbar.append(button);
 let identity='',epoch=0,controller=null,loading=false,cache=null,received=0,error='',dialog=null,active='web',request=0,webLive=null,webFrozen=null,webAt=0,waitingWeb=false;
 function closeDialog(){if(!dialog)return;const current=dialog;dialog=null;current.list.replaceChildren();current.root.close();current.root.remove();}
 function clear(){request++;loading=false;cache=null;received=0;error='';webLive=null;webFrozen=null;webAt=0;waitingWeb=false;controller?.abort();controller=null;closeDialog();}
 function identityCheck(){const next=token();if(next!==identity){identity=next;epoch++;clear();}return next;}
 function requestWeb(){waitingWeb=!!dialog;webFrozen=null;document.dispatchEvent(new Event('radar-feed-policy-request'));}
 document.addEventListener('radar-feed-policy-snapshot',event=>{
  identityCheck();webLive=identity?webpageRecords(event.detail):null;
  // Invalid/changed identity and expired authorization never retain private UI.
  if(webLive===null){webFrozen=null;waitingWeb=!!dialog;}
  else if(dialog&&waitingWeb){webFrozen=webLive.map(r=>({...r}));webAt=Date.now();waitingWeb=false;}
  paint();
 });
 // An open viewer is a dated snapshot; it stays still until the user refreshes.
 function fresh(){return cache&&(dialog||Date.now()-received<45000);}
 function paint(){
  button.disabled=!identity;button.textContent=webLive?`已屏蔽 ${webLive.length} 条`:'已屏蔽推送';button.title=!identity?'连接自己的推送码后查看':'查看当前网页已屏蔽消息，以及电脑和手机历史记录';
  if(!dialog)return;
  for(const [channel,b]of Object.entries(dialog.tabs)){b.setAttribute('aria-pressed',String(channel===active));b.textContent=({web:'网页当前',desktop:'电脑历史',mobile:'手机历史'})[channel]+(channel==='web'?(webFrozen?` ${webFrozen.length}`:''):(fresh()?` ${cache[channel].length}`:''));}
  const ready=active==='web'?webFrozen!==null:fresh();
  dialog.refresh.disabled=loading;dialog.status.textContent=!identity?'请先连接自己的推送码':active==='web'?(ready?`当前网页筛选快照 · 已读取 ${clock(webAt/1000)} · UTC+8`:'等待当前网页规则校验…'):error||(!ready?'正在读取历史记录…':`历史拦截记录 · 已读取 ${clock(received/1000)} · UTC+8`);
  if(!ready){dialog.list.replaceChildren();dialog.signature='';return;}
  const rows=active==='web'?webFrozen:cache[active],signature=active+'|'+JSON.stringify(rows);if(signature===dialog.signature)return;dialog.signature=signature;
  const content=rows.map(r=>{
   if(active==='web'){
    const article=el('article','rp-blocked-message'),head=el('header');article.dataset.messageId=r.id;
    head.append(el('strong','',r.title||'机器人消息'),el('time','',clock(Date.parse(r.sentAt)/1000)));article.append(head,el('p','rp-blocked-reasons','当前网页规则已屏蔽'),el('p','rp-blocked-body',r.body));return article;
   }
   const article=el('article','rp-blocked-message'),head=el('header'),title=[r.rank,r.value,r.coin,r.mode,[r.buy,r.sell].filter(Boolean).join(' → ')].filter(Boolean).join(' | ');
   head.append(el('strong','',title||'未识别的推送'),el('time','',clock(r.messageAt||r.at)));article.append(head);
   article.append(el('p','rp-blocked-reasons',r.reasons.filter(x=>typeof x==='string').join('；')||'已被当时的规则屏蔽'));
   article.append(el('small','',`屏蔽时间 ${clock(r.at)}${Number.isInteger(r.revision)?' · 规则版本 '+r.revision:''}`));return article;
  });
  if(!content.length)content.push(el('p','rp-blocked-empty',active==='web'?'当前网页没有已屏蔽消息。':'当前没有此渠道的历史屏蔽记录。'));dialog.list.replaceChildren(...content);dialog.list.scrollTop=0;
 }
 async function refresh(){
  const auth=identityCheck();if(!dialog||!auth||document.hidden||loading){paint();return;}const identityEpoch=epoch,id=++request;loading=true;error='';controller=new AbortController();const abort=controller;const timeout=setTimeout(()=>abort.abort(),8000);paint();
  try{
   const results=await Promise.all(['desktop-settings','status'].map(async route=>{const response=await fetch('/radar/push-test/api/'+route,{headers:{Authorization:'Bearer '+auth},cache:'no-store',redirect:'error',signal:abort.signal});if(!response.ok){const failure=Error(response.status===401||response.status===403?'连接已失效，请重新连接自己的推送码':'屏蔽记录读取失败，请重试');failure.status=response.status;throw failure;}return response.json();}));
   if(id!==request||epoch!==identityEpoch||token()!==auth)return;
   cache={desktop:blockedRecords(results[0],'desktop'),mobile:blockedRecords(results[1],'mobile')};received=Date.now();
  }catch(e){if(id===request&&epoch===identityEpoch&&token()===auth){cache=null;received=0;error=e.name==='AbortError'?'读取超时，请重试':e.message||'屏蔽记录读取失败，请重试';if(e.status===401||e.status===403){webLive=null;webFrozen=null;waitingWeb=true;}}}
  finally{clearTimeout(timeout);if(id===request){loading=false;paint();}}
 }
 button.onclick=()=>{
  identityCheck();if(!identity||dialog){paint();return;}
  const root=el('dialog','rp-blocked-dialog'),head=el('header','rp-blocked-head'),close=el('button','','关闭'),title=el('h2','','已屏蔽推送');root.setAttribute('aria-label','已屏蔽推送');close.type='button';close.setAttribute('aria-label','关闭已屏蔽推送');head.append(title,close);
  active='web';const controls=el('div','rp-blocked-controls'),tabs={web:el('button','','网页当前'),desktop:el('button','','电脑历史'),mobile:el('button','','手机历史')},reload=el('button','','刷新'),status=el('p','rp-blocked-status'),list=el('section','rp-blocked-list');status.setAttribute('role','status');list.setAttribute('aria-label','推送屏蔽记录');list.tabIndex=0;
  for(const [channel,b]of Object.entries(tabs)){b.type='button';b.onclick=()=>{active=channel;paint();};controls.append(b);}reload.type='button';reload.onclick=()=>{requestWeb();paint();void refresh();};controls.append(reload);
  root.append(head,el('p','rp-blocked-help','仅查看，不解除屏蔽、不补发通知。网页当前展示本页已过滤的消息；电脑和手机历史分别保留当时的拦截记录。'),controls,status,list,el('p','rp-blocked-help','打开后保持当前快照，点击刷新查看最新结果。历史记录不会因解除屏蔽而删除；仅静音不计入网页已屏蔽数量。'));
  document.body.append(root);dialog={root,tabs,refresh:reload,status,list,signature:''};close.onclick=()=>root.close();root.addEventListener('close',()=>{root.remove();if(dialog?.root===root){dialog=null;request++;controller?.abort();controller=null;loading=false;}button.focus({preventScroll:true});});requestWeb();paint();root.showModal();close.focus({preventScroll:true});void refresh();
 };
 const wake=()=>{identityCheck();paint();if(!dialog)document.dispatchEvent(new Event('radar-feed-policy-request'));};window.addEventListener('storage',wake);window.addEventListener('focus',wake);document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});document.addEventListener('radar-profile-changing',()=>{clear();paint();queueMicrotask(wake);});
 setInterval(()=>{identityCheck();if(!document.hidden)paint();},1000);
 // The badge uses the feed policy snapshot, not desktop/mobile history. Fetch
 // history only when this viewer opens or its refresh button is pressed.
 // Open records stay still for reading; no idle/focus/background history polls.
 wake();return {refresh};
}
if(typeof document!=='undefined'){const toolbar=document.querySelector('.feed-tools');if(toolbar)createBlockedPushes(toolbar);}
