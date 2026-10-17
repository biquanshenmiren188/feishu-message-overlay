const BASE='/radar/push-test/', API=BASE+'api/';
const css=document.createElement('link');css.rel='stylesheet';css.href='/radar/robot-push/notification-settings.css?v=20261017-mobile1';document.head.append(css);
const mount=document.querySelector('.feed-tools')||document.querySelector('#notification-controls');
const button=document.createElement('button');button.type='button';button.id='notification-settings-open';button.textContent='推送设置';mount?.append(button);
const dialog=document.createElement('dialog');dialog.id='notification-settings';dialog.setAttribute('aria-labelledby','notification-settings-title');
dialog.innerHTML=`<div class="ns-head"><div><h2 id="notification-settings-title">手机推送设置</h2><p>消息合并显示，最新在上。</p></div><button type="button" id="ns-close" aria-label="关闭推送设置">关闭</button></div>
<div class="ns-body"><p id="ns-message" role="status" aria-live="polite"></p>
<form id="ns-pair" hidden><label for="ns-code">连接码</label><div class="ns-inline"><input id="ns-code" type="password" inputmode="numeric" maxlength="8" autocomplete="off" placeholder="输入原来的 8 位连接码"><button>连接</button></div><p>原测试通知已沿用，不需要重新安装。</p></form>
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
</fieldset></form></div><div class="ns-actions" id="ns-actions" hidden><button type="button" id="ns-enable" hidden>在这台 iPhone 启用通知</button><button class="ns-primary" id="ns-save" type="submit" form="ns-form">保存设置</button></div>`;
document.body.append(dialog);
const $=id=>dialog.querySelector('#'+id);
for(const [id,values] of [['ns-modes',[['SF','SF'],['FS','FS'],['FF','FF']]],['ns-exchanges',[['BINANCE','BN · 币安'],['BITGET','BG · Bitget'],['BYBIT','BY · Bybit'],['OKX','OK · OKX'],['GATE','GT · Gate'],['ASTER','AS · Aster'],['HL','HY · Hyperliquid']]]]){
 for(const [value,label] of values){const el=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=value;el.append(input,document.createTextNode(label));$(id).append(el)}
}
let token=localStorage.getItem('radar-test-token')||'', revision=0, publicKey='', busy=false;
let phone=null, serverFingerprint=null, workerVersion='unknown';
const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
const ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
function message(text,error=false){$('ns-message').textContent=text;$('ns-message').classList.toggle('ns-error',error)}
async function api(route,data){const r=await fetch(API+route,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:data===undefined?undefined:JSON.stringify(data),cache:'no-store',redirect:'error'});let body;try{body=await r.json()}catch{throw Error('网站登录已失效，请重新打开页面登录。')}if(r.status===401){$('ns-pair').hidden=false;$('ns-form').hidden=true;$('ns-actions').hidden=true}if(!r.ok)throw Error(body.error||'请求失败');return body}
function fill(s){revision=s.revision;publicKey=s.publicKey;serverFingerprint=s.subscriptionFingerprint??null;$('ns-pair').hidden=true;$('ns-form').hidden=false;$('ns-actions').hidden=false;const p=s.settings;
 $('ns-enabled').checked=p.notify_enabled;$('ns-rows').value=p.rows;$('ns-interval').value=p.notify_interval_seconds;$('ns-percent').value=p.min_percent??'';$('ns-ranks').value=p.excluded_ranks.join(', ');$('ns-coins').value=p.excluded_coins.join(', ');
 for(const [id,key] of [['ns-modes','excluded_modes'],['ns-exchanges','excluded_exchanges']])for(const el of $(id).querySelectorAll('input'))el.checked=p[key].includes(el.value);
 const needsRepair=phone&&(phone.permission!=='granted'||!phone.subscriptionFingerprint||phone.subscriptionFingerprint!==serverFingerprint);
 $('ns-enable').hidden=!standalone||!ios||(!needsRepair&&s.subscribed);
 $('ns-enable').textContent=s.subscribed?'修复这台 iPhone 的通知':'在这台 iPhone 启用通知';
 message(!s.subscribed?'手机订阅未连接，请从 iPhone 主屏幕打开雷达并启用通知。':!p.notify_enabled?'手机推送已关闭。':s.source?.connected?'推送已开启，消息源在线。':'推送已开启，等待消息源恢复。');
 if(needsRepair)message(phone.permission==='denied'?'这台手机的通知权限已关闭，请在 iPhone 设置中允许通知。':'手机订阅未连接或与服务器不一致，请点下方修复通知。',true);
}
async function task(fn){if(busy)return;busy=true;$('ns-fields').disabled=true;$('ns-save').disabled=true;$('ns-enable').disabled=true;try{await fn()}catch(e){message(e.message,true)}finally{busy=false;$('ns-fields').disabled=false;$('ns-save').disabled=false;$('ns-enable').disabled=false}}
async function load(){if(!token){$('ns-pair').hidden=false;$('ns-form').hidden=true;$('ns-actions').hidden=true;message('连接后即可修改手机推送。');return}await syncPhone();fill(await api('status'))}
button.onclick=()=>{dialog.showModal();dialog.querySelector('.ns-body').scrollTop=0;task(load)};$('ns-close').onclick=()=>dialog.close();
$('ns-pair').onsubmit=e=>{e.preventDefault();task(async()=>{const result=await api('pair',{code:$('ns-code').value.trim()});token=result.token;localStorage.setItem('radar-test-token',token);$('ns-code').value='';await load();if(standalone)await configureWorker()})};
const list=id=>$(id).value.trim().split(/[\s,，、]+/).filter(Boolean).map(s=>s.toUpperCase());
const checked=id=>Array.from($(id).querySelectorAll('input:checked'),el=>el.value);
$('ns-form').onsubmit=e=>{e.preventDefault();task(async()=>{const settings={notify_enabled:$('ns-enabled').checked,rows:Number($('ns-rows').value),notify_interval_seconds:Number($('ns-interval').value),min_percent:$('ns-percent').value===''?null:Number($('ns-percent').value),excluded_ranks:list('ns-ranks'),excluded_coins:list('ns-coins'),excluded_modes:checked('ns-modes'),excluded_exchanges:checked('ns-exchanges')};fill(await api('settings',{revision,settings}));message('已保存，后续新消息按此设置推送。');dialog.querySelector('.ns-body').scrollTop=0})};
let registration;
async function configureWorker(){if(!registration?.active||!token)return;await new Promise((resolve,reject)=>{const c=new MessageChannel(),timer=setTimeout(()=>reject(Error('通知组件未就绪，请重新打开页面。')),8000);c.port1.onmessage=e=>{clearTimeout(timer);c.port1.close();if(e.data?.ok){workerVersion=e.data.version||'unknown';resolve()}else reject(Error('通知配置失败'))};registration.active.postMessage({type:'configure',token},[c.port2])})}
async function subscriptionFingerprint(sub){if(!sub)return null;const s=sub.toJSON();const bytes=new TextEncoder().encode(JSON.stringify([s.endpoint,s.keys.p256dh,s.keys.auth]));return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('')}
let syncing=false;
async function syncPhone(){
 if(syncing||!standalone||!ios||!registration||!token)return;
 syncing=true;
 try{
  const sub=await registration.pushManager.getSubscription();
  phone={permission:typeof Notification==='undefined'?'unsupported':Notification.permission,subscriptionFingerprint:await subscriptionFingerprint(sub),version:workerVersion};
  await api('device',phone);
 }finally{syncing=false}
}
$('ns-enable').onclick=()=>task(async()=>{if(!registration)throw Error('请从 iPhone 主屏幕打开雷达通知页面。');const p=await Notification.requestPermission();if(p!=='granted')throw Error('请在 iPhone 设置中允许雷达通知。');let sub=await registration.pushManager.getSubscription();if(!sub){const raw=atob(publicKey.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-publicKey.length%4)%4));sub=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:Uint8Array.from(raw,c=>c.charCodeAt(0))})}await configureWorker();await api('subscribe',{subscription:sub.toJSON(),replaceFingerprint:serverFingerprint});await load()});
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
  await configureWorker();
  await syncPhone();
  reg.update().catch(()=>{});
 }).catch(()=>{});
}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')configureWorker().then(syncPhone).catch(()=>{})});
navigator.serviceWorker?.addEventListener('controllerchange',()=>{configureWorker().then(syncPhone).catch(()=>{})});
