const BASE='/radar/push-test/', API=BASE+'api/';
const css=document.createElement('link');css.rel='stylesheet';css.href='/radar/robot-push/notification-settings.css?v=20261017-phone-switch1';document.head.append(css);
const mount=document.querySelector('.feed-tools')||document.querySelector('#notification-controls');
const button=document.createElement('button');button.type='button';button.id='notification-settings-open';button.textContent='推送设置';mount?.append(button);
const dialog=document.createElement('dialog');dialog.id='notification-settings';dialog.setAttribute('aria-labelledby','notification-settings-title');
dialog.innerHTML=`<div class="ns-head"><div><h2 id="notification-settings-title">手机推送设置</h2><p>消息合并显示，最新在上。</p></div><button type="button" id="ns-close" aria-label="关闭推送设置">关闭</button></div>
<div class="ns-body"><p id="ns-message" role="status" aria-live="polite"></p>
<section class="ns-notification" aria-label="通知与绑定"><div id="ns-binding" hidden><span>当前推送码</span><output id="ns-bound-code"></output></div><button type="button" id="ns-enable" aria-describedby="ns-notification-help">开启通知</button><p id="ns-notification-help">开启后可在手机锁屏接收提醒。</p></section>
<section class="ns-plans" aria-label="独立推送方案"><div class="ns-plan-buttons"><button type="button" id="ns-switch-open" aria-expanded="false" aria-controls="ns-switch">切换推送码</button><button type="button" id="ns-create-code">新建推送码</button></div><p>每个推送码的设置与通知独立，修改本码不影响其他码。</p><form id="ns-switch" hidden><label for="ns-switch-code">切换到推送码</label><input id="ns-switch-code" type="password" inputmode="numeric" maxlength="8" pattern="[0-9]{8}" required autocomplete="off" placeholder="输入其他 8 位推送码" aria-describedby="ns-switch-help ns-switch-error"><p id="ns-switch-help">切换后载入该码已保存的设置，当前未保存内容不会带过去。本机通知绑定保持不变。</p><p id="ns-switch-error" class="ns-error" role="alert"></p><div class="ns-plan-buttons"><button type="submit" id="ns-switch-submit">确认切换</button><button type="button" id="ns-switch-cancel">取消</button></div></form><div id="ns-created" hidden role="status"><span>新推送码</span><output id="ns-created-code"></output><p>可切换到此码管理设置，在另一台手机连接后开启通知。当前方案保持不变。</p></div></section>
<form id="ns-pair" hidden><label for="ns-code">推送码</label><div class="ns-inline"><input id="ns-code" type="password" inputmode="numeric" maxlength="8" autocomplete="off" placeholder="输入原来的 8 位推送码"><button>连接</button></div><p>沿用原来的推送码，不需要重新安装。</p></form>
<form id="ns-form" hidden><fieldset id="ns-fields"><label class="ns-toggle"><span>接收消息</span><input id="ns-enabled" type="checkbox"></label>
<div class="ns-grid"><label>显示条数<select id="ns-rows"><option value="1">1 条</option><option value="2">2 条</option><option value="3">3 条</option><option value="4">4 条</option></select></label><label>提醒间隔<select id="ns-interval"><option value="30">30 秒</option><option value="60">1 分钟</option><option value="180">3 分钟</option><option value="300">5 分钟</option><option value="600">10 分钟</option><option value="1800">30 分钟</option></select></label></div>
<p class="ns-help">间隔内合并提醒，无新消息不打扰。时间为 UTC+8。</p>
<label>最低 R 百分比（%）<input id="ns-percent" type="number" min="-100" max="100" step="any" placeholder="留空表示不限"></label>
<p class="ns-help">按 R 等级后的百分比筛选。</p>
<label>屏蔽等级<input id="ns-ranks" placeholder="例如 R0、R1、R5+"></label>
<p class="ns-help">留空全部接收。支持 R1000+；R5 包含 R5+，只填 R5+ 不影响 R5。</p>
<label>屏蔽币种<input id="ns-coins" placeholder="例如 BTC、ETH，逗号或空格分隔"></label>
<div class="ns-options"><strong>屏蔽类型</strong><div id="ns-modes"></div></div>
<div class="ns-options"><strong>屏蔽交易所</strong><div id="ns-exchanges"></div></div>
<p class="ns-help">只屏蔽勾选项，买卖任一侧命中即过滤。</p>
</fieldset></form></div><div class="ns-actions" id="ns-actions" hidden><button class="ns-primary" id="ns-save" type="submit" form="ns-form">保存设置</button></div>`;
document.body.append(dialog);
const $=id=>dialog.querySelector('#'+id);
for(const [id,values] of [['ns-modes',[['SF','SF'],['FS','FS'],['FF','FF']]],['ns-exchanges',[['BINANCE','BN · 币安'],['BITGET','BG · Bitget'],['BYBIT','BY · Bybit'],['OKX','OK · OKX'],['GATE','GT · Gate'],['ASTER','AS · Aster'],['HL','HY · Hyperliquid']]]]){
 for(const [value,label] of values){const el=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=value;el.append(input,document.createTextNode(label));$(id).append(el)}
}
let deviceToken=localStorage.getItem('radar-test-token')||'';
let token=localStorage.getItem('radar-settings-token')||deviceToken, revision=0, publicKey='', busy=false;
let phone=null, serverFingerprint=null, workerVersion='unknown', notificationReady=false;
const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
const ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const phoneApp=standalone&&ios;
const pendingSwitch=()=>JSON.parse(localStorage.getItem('radar-phone-switch')||'null');
$('ns-switch-help').textContent=phoneApp?'切换后，本机接收新码的推送，并载入该码已保存的设置。当前未保存内容不会带过去。':'切换后载入该码已保存的设置，不改变手机绑定。要切换手机接收的推送，请在手机主屏幕打开雷达操作。';
function message(text,error=false){$('ns-message').textContent=text;$('ns-message').classList.toggle('ns-error',error)}
async function api(route,data,auth=token,clearSession=true){const r=await fetch(API+route,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+auth},body:data===undefined?undefined:JSON.stringify(data),cache:'no-store',redirect:'error'});let body;try{body=await r.json()}catch{throw Error('网站登录已失效，请重新打开页面登录。')}if(r.status===401&&clearSession&&auth===token){token='';localStorage.removeItem('radar-settings-token');$('ns-binding').hidden=true;$('ns-bound-code').textContent='';$('ns-pair').hidden=false;$('ns-form').hidden=true;$('ns-actions').hidden=true;notificationReady=false;renderNotification()}if(!r.ok){const error=Error(body.error||'请求失败');error.status=r.status;throw error}return body}
function renderNotification(){
 const otherPlan=!!(token&&deviceToken&&token!==deviceToken);
 notificationReady=!!(!otherPlan&&token&&standalone&&ios&&phone?.permission==='granted'&&phone.subscriptionFingerprint&&phone.subscriptionFingerprint===serverFingerprint);
 $('ns-enable').textContent=otherPlan?(phoneApp?'切换本机通知到此码':'手机绑定保持不变'):notificationReady?'通知已开启':'开启通知';
 $('ns-enable').disabled=busy||notificationReady||(otherPlan&&!phoneApp);
 $('ns-notification-help').textContent=otherPlan?(phoneApp?'正在查看另一推送码。点击上方按钮，将本机通知也切换到此码。':'正在管理另一推送码的设置。电脑切换不会改变手机接收的推送。'):!token?'请先输入推送码连接，再开启通知。':!ios?'请在 iPhone 上打开雷达，添加到主屏幕后开启通知。':!standalone?'请在 Safari 中将雷达添加到主屏幕，再从主屏幕打开并开启通知。':phone?.permission==='denied'?'通知权限已关闭，请前往 iPhone 设置中允许雷达通知。':notificationReady?'本机通知已开启，消息接收由下方“接收消息”控制。':'点击后允许系统通知；如订阅已失效，会重新连接本机通知。';
}
function fill(s){revision=s.revision;publicKey=s.publicKey;serverFingerprint=s.subscriptionFingerprint??null;$('ns-pair').hidden=true;$('ns-form').hidden=false;$('ns-actions').hidden=false;const p=s.settings;
 $('ns-enabled').checked=p.notify_enabled;$('ns-rows').value=p.rows;$('ns-interval').value=p.notify_interval_seconds;$('ns-percent').value=p.min_percent??'';$('ns-ranks').value=p.excluded_ranks.join(', ');$('ns-coins').value=p.excluded_coins.join(', ');
 for(const [id,key] of [['ns-modes','excluded_modes'],['ns-exchanges','excluded_exchanges']])for(const el of $(id).querySelectorAll('input'))el.checked=p[key].includes(el.value);
 const needsRepair=token===deviceToken&&phone&&(phone.permission!=='granted'||!phone.subscriptionFingerprint||phone.subscriptionFingerprint!==serverFingerprint);
 renderNotification();
 message(!s.subscribed?'手机订阅未连接，请从 iPhone 主屏幕打开雷达并启用通知。':!p.notify_enabled?'手机推送已关闭。':s.source?.connected?'推送已开启，消息源在线。':'推送已开启，等待消息源恢复。');
 if(needsRepair)message(phone.permission==='denied'?'这台手机的通知权限已关闭，请在 iPhone 设置中允许通知。':'手机订阅未连接或与服务器不一致，请点“开启通知”重新连接。',true);
}
async function task(fn){if(busy)return;busy=true;dialog.setAttribute('aria-busy','true');$('ns-fields').disabled=true;$('ns-save').disabled=true;$('ns-enable').disabled=true;for(const id of ['ns-create-code','ns-switch-open','ns-switch-submit','ns-switch-cancel','ns-switch-code'])$(id).disabled=true;try{await fn()}catch(e){message(e.message,true);if(!$('ns-switch').hidden)$('ns-switch-error').textContent=e.message}finally{busy=false;dialog.setAttribute('aria-busy','false');$('ns-fields').disabled=!!pendingSwitch();$('ns-save').disabled=!!pendingSwitch();for(const id of ['ns-create-code','ns-switch-open','ns-switch-submit','ns-switch-cancel','ns-switch-code'])$(id).disabled=false;renderNotification()}}
async function readPlan(auth){const [status,binding]=await Promise.all([api('status',undefined,auth,false),api('binding',undefined,auth,false)]);return {status,binding}}
function showPlan(plan){fill(plan.status);$('ns-bound-code').textContent=plan.binding.pushCode;$('ns-binding').hidden=false}
async function load(){if(phoneApp&&pendingSwitch())await finishPhoneSwitch();if(!token){$('ns-binding').hidden=true;$('ns-bound-code').textContent='';$('ns-pair').hidden=false;$('ns-form').hidden=true;$('ns-actions').hidden=true;message('连接后即可修改手机推送。');renderNotification();return}const plan=await readPlan(token);await syncPhone().catch(()=>{});showPlan(plan)}
function closeSwitch(){ $('ns-switch').hidden=true;$('ns-switch-open').setAttribute('aria-expanded','false');$('ns-switch-code').value='';$('ns-switch-error').textContent='' }
async function activatePlan(result,movePhone=false){
 // Verify both responses before changing the current identity or form. A failed
 // switch must leave the original token, revision and unsaved edits intact.
 let plan=await readPlan(result.token);
 if(movePhone&&phoneApp){const moved=await switchPhone(result.token,plan);if(moved)plan=moved}
 if(!deviceToken){localStorage.setItem('radar-test-token',result.token);deviceToken=result.token}
 localStorage.setItem('radar-settings-token',result.token);token=result.token;
 showPlan(plan);closeSwitch();$('ns-created').hidden=true;
 dialog.querySelector('.ns-body').scrollTop=0;
}
button.onclick=()=>{dialog.showModal();dialog.querySelector('.ns-body').scrollTop=0;task(load)};$('ns-close').onclick=()=>dialog.close();
$('ns-pair').onsubmit=e=>{e.preventDefault();task(async()=>{const result=await api('pair',{code:$('ns-code').value.trim()},token,false);await activatePlan(result);$('ns-code').value='';if(standalone)await configureWorker()})};
$('ns-switch-open').onclick=()=>{if(busy)return;$('ns-switch').hidden=false;$('ns-switch-open').setAttribute('aria-expanded','true');$('ns-switch-error').textContent='';$('ns-switch-code').focus()};
$('ns-switch-cancel').onclick=()=>{closeSwitch();$('ns-switch-open').focus()};
$('ns-switch').onsubmit=e=>{e.preventDefault();task(async()=>{
 const code=$('ns-switch-code').value.trim();if(!/^[0-9]{8}$/.test(code))throw Error('请输入 8 位推送码。');
 $('ns-switch-error').textContent='';$('ns-switch-submit').textContent='正在切换…';
 try{const result=await api('pair',{code},token,false);await activatePlan(result,true);message(phoneApp?(phone?.permission==='granted'&&phone?.subscriptionFingerprint?'已切换，本机现在按此推送码的设置接收通知。':'已切换推送码，请点“开启通知”连接本机推送。'):'已切换推送码，当前显示该码已保存的设置。手机绑定不变。')}
 finally{$('ns-switch-submit').textContent='确认切换'}
})};
$('ns-create-code').onclick=()=>task(async()=>{
 $('ns-create-code').textContent='正在创建…';
 try{
  let requestId=sessionStorage.getItem('radar-create-code-request');
  if(!requestId){requestId=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');sessionStorage.setItem('radar-create-code-request',requestId)}
  const result=await api('create-code',{requestId});
  if(!token){
   await activatePlan(result);
   message('推送码已创建并绑定。设置只影响此码；在手机上点击“开启通知”即可连接。');
  }else{
   $('ns-created-code').textContent=result.pushCode;$('ns-created').hidden=false;
   message('新推送码已创建，当前绑定和未保存的设置保持不变。');
  }
  sessionStorage.removeItem('radar-create-code-request');
 }finally{$('ns-create-code').textContent='新建推送码'}
});
const list=id=>$(id).value.trim().split(/[\s,，、]+/).filter(Boolean).map(s=>s.toUpperCase());
const checked=id=>Array.from($(id).querySelectorAll('input:checked'),el=>el.value);
$('ns-form').onsubmit=e=>{e.preventDefault();task(async()=>{const settings={notify_enabled:$('ns-enabled').checked,rows:Number($('ns-rows').value),notify_interval_seconds:Number($('ns-interval').value),min_percent:$('ns-percent').value===''?null:Number($('ns-percent').value),excluded_ranks:list('ns-ranks'),excluded_coins:list('ns-coins'),excluded_modes:checked('ns-modes'),excluded_exchanges:checked('ns-exchanges')};fill(await api('settings',{revision,settings}));message('已保存，后续新消息按此设置推送。');dialog.querySelector('.ns-body').scrollTop=0})};
let registration;
async function workerConfigure(auth,profile){
 if(!registration?.active)throw Error('通知组件正在准备，请稍后再试。');
 await new Promise((resolve,reject)=>{const c=new MessageChannel(),timer=setTimeout(()=>reject(Error('通知组件未就绪，请重新打开页面。')),8000);c.port1.onmessage=e=>{clearTimeout(timer);c.port1.close();if(e.data?.ok){workerVersion=e.data.version||'unknown';resolve()}else reject(Error('通知配置失败，请重新打开页面。'))};registration.active.postMessage({type:'configure',token:auth,profile},[c.port2])});
}
async function configureWorker(){
 if(!registration?.active||pendingSwitch())return;
 deviceToken=localStorage.getItem('radar-test-token')||deviceToken;if(!deviceToken)return;
 const auth=deviceToken,status=await api('status',undefined,auth,false);
 if(pendingSwitch()||auth!==localStorage.getItem('radar-test-token'))return;
 await workerConfigure(auth,status.profileId);await syncPhone();
}
async function finishPhoneSwitch(){
 const operation=pendingSwitch();if(!operation)return;
 if(!registration?.active)throw Error('通知组件正在准备，请稍后重试切换。');
 try{await api('switch-subscription',operation.request,operation.sourceToken,false)}catch(error){
  if(error.status>=400&&error.status<500)localStorage.removeItem('radar-phone-switch');
  else error.message='切换结果尚未确认，请保持联网，重新打开推送设置继续。';
  throw error;
 }
 // Keep the recovery record until the server, worker and device report agree.
 localStorage.setItem('radar-test-token',operation.targetToken);
 localStorage.setItem('radar-settings-token',operation.targetToken);
 deviceToken=token=operation.targetToken;
 await workerConfigure(deviceToken,operation.profile);
 if(workerVersion!=='radar-delivery-v6')throw Error('通知组件正在更新，请重新打开雷达完成切换。');
 await syncPhone();const plan=await readPlan(operation.targetToken);showPlan(plan);localStorage.removeItem('radar-phone-switch');return plan;
}
async function switchPhone(targetToken,plan){
 if(pendingSwitch())await finishPhoneSwitch();
 if(!registration?.active)throw Error('通知组件正在准备，请稍后再试。');
 deviceToken=localStorage.getItem('radar-test-token')||deviceToken;
 if(deviceToken===targetToken){await configureWorker();return}
 const sub=await registration.pushManager.getSubscription();
 // Verify the new worker before changing any server binding.
 if(deviceToken)await configureWorker();
 if(workerVersion!=='radar-delivery-v6'){registration.update().catch(()=>{});throw Error('通知组件正在更新，请重新打开雷达后再切换。')}
 if(!sub){
  await workerConfigure(targetToken,plan.status.profileId);
  localStorage.setItem('radar-test-token',targetToken);deviceToken=targetToken;phone=null;
  return;
 }
 if(Notification.permission!=='granted')throw Error('请先在 iPhone 设置中允许雷达通知，再切换。');
 const requestId=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
 localStorage.setItem('radar-phone-switch',JSON.stringify({sourceToken:deviceToken,targetToken,profile:plan.status.profileId,request:{targetToken,subscription:sub.toJSON(),requestId}}));
 return await finishPhoneSwitch();
}
async function subscriptionFingerprint(sub){if(!sub)return null;const s=sub.toJSON();const bytes=new TextEncoder().encode(JSON.stringify([s.endpoint,s.keys.p256dh,s.keys.auth]));return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('')}
let syncing=null, syncingToken='';
async function syncPhone(){
 if(syncing){if(syncingToken===deviceToken)return syncing;await syncing.catch(()=>{});return syncPhone()}
 const pending=pendingSwitch();if(pending&&deviceToken!==pending.targetToken)return;
 if(!standalone||!ios||!registration||!deviceToken)return;
 const auth=deviceToken;
 syncingToken=auth;
 syncing=(async()=>{
  const sub=await registration.pushManager.getSubscription();
  if(auth!==localStorage.getItem('radar-test-token'))return;
  phone={permission:typeof Notification==='undefined'?'unsupported':Notification.permission,subscriptionFingerprint:await subscriptionFingerprint(sub),version:workerVersion};
  await api('device',phone,auth,false);
  renderNotification();
 })();
 try{return await syncing}finally{syncing=null}
}
$('ns-enable').onclick=()=>task(async()=>{
 if(!token){$('ns-code').focus();throw Error('请先输入推送码连接。')}
 if(deviceToken&&token!==deviceToken&&phoneApp){await activatePlan({token},true);message('本机通知已切换到当前推送码。');return}
 if(!ios||!standalone)throw Error('请在 iPhone Safari 中将雷达添加到主屏幕，再从主屏幕打开并点击“开启通知”。');
 if(!registration?.active||!publicKey)throw Error('通知组件正在准备，请稍后再点“开启通知”。');
 if(typeof Notification==='undefined'||!registration.pushManager)throw Error('当前系统不支持网页通知，请更新 iOS 后重试。');
 $('ns-enable').textContent='正在开启…';message('请允许系统通知，正在连接本机推送。');
 // Request permission directly in the click gesture, before any network/worker awaits.
 const p=await Notification.requestPermission();
 if(p!=='granted'){await syncPhone();throw Error(p==='denied'?'请在 iPhone 设置中允许雷达通知，再返回此处。':'尚未允许通知，可以再次点击“开启通知”。')}
 let sub=await registration.pushManager.getSubscription();
 if(!sub){const raw=atob(publicKey.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-publicKey.length%4)%4));sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:Uint8Array.from(raw,c=>c.charCodeAt(0))})}
 await api('subscribe',{subscription:sub.toJSON(),replaceFingerprint:serverFingerprint});await configureWorker();
 serverFingerprint=await subscriptionFingerprint(sub);await syncPhone();
 message('本机通知已开启；按“接收消息”和已保存的筛选设置接收提醒。');
});
if(location.pathname.startsWith(BASE)||standalone){
 if('serviceWorker'in navigator)navigator.serviceWorker.register(BASE+'sw.js',{scope:BASE,updateViaCache:'none'}).then(async reg=>{
  registration=reg;
  // The canonical BOT URL is outside the legacy scope: do not await page.ready.
  if(!reg.active)await new Promise((resolve,reject)=>{
   const worker=reg.installing||reg.waiting;
   if(!worker){reject(Error('通知组件未就绪'));return}
   const timer=setTimeout(()=>reject(Error('通知组件启动超时')),10000);
   const check=()=>{if(worker.state==='activated'){clearTimeout(timer);resolve()}else if(worker.state==='redundant'){clearTimeout(timer);reject(Error('通知组件启动失败'))}};
   worker.addEventListener('statechange',check);check();
  });
  if(phoneApp&&pendingSwitch())await task(load);
  await configureWorker();
  await syncPhone();
  reg.update().catch(()=>{});
 }).catch(()=>{});
}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){if(phoneApp&&pendingSwitch())task(load);else configureWorker().then(syncPhone).catch(()=>{})}});
navigator.serviceWorker?.addEventListener('controllerchange',()=>{if(phoneApp&&pendingSwitch())task(load);else configureWorker().then(syncPhone).catch(()=>{})});
