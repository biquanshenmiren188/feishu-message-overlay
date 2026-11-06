// Shared identity entry. Device credentials stay in the established Web Push module.
const accountPage=/^\/radar\/(?:robot-push|push-test)\/(?:settings|alarms)(?:\/|$)/.test(location.pathname);
 const css=document.createElement('link');css.rel='stylesheet';css.href='/radar/robot-push/shared-account.css?v=20261106-1';document.head.append(css);
const alarmURL='/radar/robot-push/alarms/';
function mountNavigation(){
  const nav=document.querySelector('.site-nav')||document.querySelector('[data-radar-nav]')||[...document.querySelectorAll('[role="tablist"]')].find(n=>n.textContent.includes('全市场费率'));
  if(nav){
   for(const [href,label] of [['/radar/robot-push/settings/','消息设置'],[alarmURL,'报警设置']]){
    let link=[...nav.querySelectorAll('a')].find(a=>a.textContent.trim()===label);
    if(!link){link=document.createElement('a');link.href=href;link.textContent=label;nav.append(link);}
    if(location.pathname.includes('/alarms/')&&label==='报警设置')link.setAttribute('aria-current','page');
   }
   nav.classList.add('radar-seven-nav');
   if(location.pathname.includes('/alarms/'))for(const a of nav.querySelectorAll('a'))if(a.textContent.trim()!=='报警设置')a.removeAttribute('aria-current');
  }
}
let navQueued=false;new MutationObserver(()=>{if(navQueued)return;navQueued=true;queueMicrotask(()=>{navQueued=false;mountNavigation();});}).observe(document.body,{childList:true,subtree:true});mountNavigation();
if (accountPage && !window.RadarAccount) {
 const entry=document.createElement('button');entry.type='button';entry.className='radar-account-entry';entry.textContent='连接推送码';entry.setAttribute('aria-haspopup','dialog');
 const modal=document.createElement('dialog');modal.id='radar-account-dialog';modal.setAttribute('aria-labelledby','radar-account-title');
 modal.innerHTML='<div class="ra-heading"><h2 id="radar-account-title">推送码与设备</h2><button type="button" class="ra-close" aria-label="关闭推送码管理">×</button></div><p class="ra-intro">消息设置与报警设置共用当前推送码，各自独立保存。</p><div id="ra-content"></div><div class="ra-footer"><a href="/radar/robot-push/alarms/?binding=1">管理 Bark 报警设备</a><button type="button" id="ra-exit">退出当前连接</button></div><p class="ra-footnote">退出网页连接不停止云端报警，也不解除手机绑定。</p>';
 document.body.append(modal);
 let integrated=document.getElementById('live-mobile-account');
 const old=integrated?.closest('#mobile-account');
 if(!integrated){integrated=document.createElement('div');integrated.id='live-mobile-account';}
 modal.querySelector('#ra-content').append(integrated);old?.remove();
 const hasDraft=()=>window.RadarHasUnsavedChanges?.()||window.RadarAlarmHasDraft?.();
 const guard=e=>{if(hasDraft()&&!confirm('有未保存的修改。切换推送码将放弃这些修改，是否继续？'))e.preventDefault();};
 document.addEventListener('radar-before-profile-change',guard);
 function open(){if(!modal.open)modal.showModal();}
 function close(){modal.close();entry.focus();}
 entry.onclick=open;modal.querySelector('.ra-close').onclick=close;
 modal.addEventListener('click',e=>{if(e.target===modal){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close();}});
 modal.querySelector('#ra-exit').onclick=()=>{const e=new Event('radar-before-profile-change',{cancelable:true});document.dispatchEvent(e);if(e.defaultPrevented)return;localStorage.setItem('radar-settings-signed-out','1');localStorage.removeItem('radar-settings-token');location.reload();};
 function mount(){
  const header=document.querySelector('.topbar.compact-header,body>header.site-head,body>header.masthead');
  if(header&&entry.parentElement!==header){header.append(entry);header.classList.add('has-radar-account');}

 }
 let queued=false;new MutationObserver(()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;mount();});}).observe(document.body,{childList:true,subtree:true});mount();
 document.addEventListener('radar-profile-ready',e=>{entry.textContent='推送码已绑定';modal.querySelector('#ra-exit').hidden=false;});
 document.addEventListener('radar-profile-changing',()=>{entry.textContent='正在连接…';});
 if(localStorage.getItem('radar-settings-signed-out'))modal.querySelector('#ra-exit').hidden=true;
 window.RadarAccount={open,token:()=>localStorage.getItem('radar-settings-signed-out')?'':localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||''};
 await import('/radar/robot-push/notification-settings.js?v=20261106-account2');
 const pwaLabel=document.createElement('p');pwaLabel.className='ra-footnote';pwaLabel.textContent='以下是原网页消息推送（PWA）的手机通知状态。价格报警使用 Bark。';document.querySelector('#ns-enable')?.before(pwaLabel);
 document.querySelector('#connect-owner')?.addEventListener('click',open);
}

// Keep the original BOT/PWA notification controls outside the two settings pages.
if(!accountPage && /^\/radar\/(?:robot-push|push-test)(?:\/(?:index\.html)?)?$/.test(location.pathname)){
 await import('/radar/robot-push/notification-settings.js?v=20261106-account2');
}
