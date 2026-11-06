// Shared identity entry. Device credentials stay in the established Web Push module.
const botPage=/^\/radar\/(?:robot-push|push-test)(?:\/(?:index\.html)?)?$/.test(location.pathname);
const settingsPage=/^\/radar\/(?:robot-push|push-test)\/(?:settings|alarms|center)(?:\/|$)/.test(location.pathname);
const accountPage=settingsPage||botPage||/^\/radar\/push-center(?:\/|$)/.test(location.pathname);
if(!document.querySelector('link[href*="shared-account.css"]')){const css=document.createElement('link');css.rel='stylesheet';css.href='/radar/robot-push/shared-account.css?v=20261106-independent1';document.head.append(css);}
const alarmURL='/radar/robot-push/alarms/';
function mountNavigation(){
  const nav=document.querySelector('.site-nav')||document.querySelector('[data-radar-nav]')||[...document.querySelectorAll('[role="tablist"]')].find(n=>n.textContent.includes('全市场费率'));
  if(nav){
   for(const [href,label] of [['/radar/robot-push/settings/','消息设置'],[alarmURL,'报警设置']]){
    let link=[...nav.querySelectorAll('a')].find(a=>a.textContent.trim()===label);
    if(!link){link=document.createElement('a');link.href=href;link.textContent=label;nav.append(link);}
    if(location.pathname.includes('/alarms/')&&label==='报警设置')link.setAttribute('aria-current','page');
   }
   const hy=[...nav.children].find(n=>n.textContent.trim()==='HY限额查询'),bot=[...nav.children].find(n=>n.textContent.trim()==='BOT');
   if(hy&&bot&&[...nav.children].indexOf(hy)>[...nav.children].indexOf(bot))nav.insertBefore(hy,bot);
   nav.classList.add('radar-seven-nav');
   if(location.pathname.includes('/alarms/'))for(const a of nav.querySelectorAll('a'))if(a.textContent.trim()!=='报警设置')a.removeAttribute('aria-current');
  }
}
let navQueued=false;new MutationObserver(()=>{if(navQueued)return;navQueued=true;queueMicrotask(()=>{navQueued=false;mountNavigation();});}).observe(document.body,{childList:true,subtree:true});mountNavigation();
if (accountPage && !window.RadarAccount) {
 const entry=document.createElement('a');entry.className='radar-account-entry';
 entry.href=location.pathname.startsWith('/radar/push-test/')||matchMedia('(display-mode: standalone)').matches||navigator.standalone===true?'/radar/push-test/center/':'/radar/push-center/';
 entry.innerHTML='<span class="ra-entry-title">推送中心</span><span class="ra-entry-status" aria-live="polite"></span>';
 const entryStatus=entry.querySelector('.ra-entry-status');
 const savedConnection=!localStorage.getItem('radar-settings-signed-out')&&!!(localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token'));
 function showConnection(connected){entryStatus.textContent=connected?'已连接':'未连接';entry.classList.toggle('is-connected',connected);}
 showConnection(savedConnection);
 const modal=document.createElement('dialog');modal.id='radar-account-dialog';modal.setAttribute('aria-labelledby','radar-account-title');
 modal.innerHTML='<div class="ra-heading"><h2 id="radar-account-title">当前推送码</h2><button type="button" class="ra-close" aria-label="关闭推送码管理">×</button></div><p class="ra-intro">BOT、消息设置与报警设置共用当前推送码。</p><div id="ra-content"></div><div class="ra-footer"><a id="ra-center-link" href="/radar/push-center/">打开推送中心</a><button type="button" id="ra-exit">退出当前连接</button></div><p class="ra-footnote">退出网页连接不停止云端报警，也不解除手机绑定。</p>';
 document.body.append(modal);
 if(location.pathname.startsWith('/radar/push-test/')||matchMedia('(display-mode: standalone)').matches||navigator.standalone===true)modal.querySelector('#ra-center-link').href='/radar/push-test/center/';
 let integrated=document.getElementById('live-mobile-account');
 const old=integrated?.closest('#mobile-account');
 if(!integrated){integrated=document.createElement('div');integrated.id='live-mobile-account';}
 modal.querySelector('#ra-content').append(integrated);old?.remove();
 const hasDraft=()=>window.RadarHasUnsavedChanges?.()||window.RadarAlarmHasDraft?.();
 const guard=e=>{if(hasDraft()&&!confirm('有未保存的修改。切换推送码将放弃这些修改，是否继续？'))e.preventDefault();};
 document.addEventListener('radar-before-profile-change',guard);
 function open(mode){if(!modal.open)modal.showModal();modal.classList.toggle('ra-phone-mode',mode==='phone');if(mode==='switch')document.getElementById('ns-switch-open')?.click();}
 function close(){modal.close();entry.focus();}
 entry.onclick=e=>{if(window.RadarHasUnsavedChanges?.()&&!confirm('有未保存的修改。进入推送中心会离开当前页面，是否继续？'))e.preventDefault();};modal.querySelector('.ra-close').onclick=close;
 modal.addEventListener('click',e=>{if(e.target===modal){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close();}});
 modal.querySelector('#ra-exit').onclick=()=>{const e=new Event('radar-before-profile-change',{cancelable:true});document.dispatchEvent(e);if(e.defaultPrevented)return;localStorage.setItem('radar-settings-signed-out','1');localStorage.removeItem('radar-settings-token');location.reload();};
 function mount(){
  const header=document.querySelector('.topbar.compact-header,body>header.site-head,body>header.masthead');
  if(header&&entry.parentElement!==header){header.append(entry);header.classList.add('has-radar-account');}

 }
 let queued=false;new MutationObserver(()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;mount();});}).observe(document.body,{childList:true,subtree:true});mount();
 document.addEventListener('radar-profile-ready',()=>{showConnection(true);modal.querySelector('#ra-exit').hidden=false;});
 document.addEventListener('radar-profile-changing',()=>showConnection(!!window.RadarIdentity?.token()));
 if(localStorage.getItem('radar-settings-signed-out'))modal.querySelector('#ra-exit').hidden=true;
 window.RadarAccount={open,token:()=>window.RadarIdentity?window.RadarIdentity.token():localStorage.getItem('radar-settings-signed-out')?'':localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||''};
 await import('/radar/robot-push/notification-settings.js?v=20261106-independent1');
 const pwaLabel=document.createElement('p');pwaLabel.className='ra-footnote';pwaLabel.textContent='以下是原网页消息推送（PWA）的手机通知状态。价格报警使用 Bark。';document.querySelector('#ns-enable')?.before(pwaLabel);
 document.querySelector('#connect-owner')?.addEventListener('click',open);
}

