import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';

const source=fs.readFileSync(new URL('./notification-settings.js',import.meta.url),'utf8');
function fixture({failRoute='',savedSelection='',ios=false,android=false,installed=ios,supported=true,secure=true,permission='',subscribeError='',subscribed=false,transferFailure='',workerFailure=false,workerVersion='radar-delivery-v6',integratedAccount=false,responseHook=null}={}){
 const elements=new Map(),storage=new Map([['radar-test-token','owner-token']]),requests=[],workerTokens=[],events={},actions=[],emitted=[],windowEvents={};
 if(savedSelection)storage.set('radar-settings-token',savedSelection);
 class Element{
  constructor(){this.children=[];this.value='';this.textContent='';this.hidden=false;this.classList={toggle(){}};this.attrs={}}
  set innerHTML(value){for(const match of value.matchAll(/id="([^"]+)"/g))elements.set(match[1],new Element());elements.get('ns-switch').hidden=true}
  setAttribute(key,value){this.attrs[key]=value}
  append(...items){this.children.push(...items)}
  querySelector(selector){return selector==='.ns-body'?body:elements.get(selector.slice(1))}
  querySelectorAll(selector){const inputs=this.children.flatMap(child=>child.children||[]).filter(child=>child.type==='checkbox');return selector.includes(':checked')?inputs.filter(input=>input.checked):inputs}
  focus(){} showModal(){} close(){}
 }
 const body=new Element(),toolbar=new Element();
 const document={createElement:()=>new Element(),createTextNode:text=>({text}),querySelector:selector=>selector==='#live-mobile-account'?(integratedAccount?toolbar:null):['.site-nav','.tabs'].includes(selector)?null:toolbar,querySelectorAll:()=>[],head:new Element(),body:new Element(),addEventListener:(name,fn)=>(events[name]??=[]).push(fn),dispatchEvent:event=>{emitted.push(event);for(const fn of events[event.type]||[])fn(event);},visibilityState:'visible'};
 const plan=auth=>({profileId:auth==='owner-token'?'legacy':'a'.repeat(32),revision:auth==='owner-token'?7:2,publicKey:'AQID',subscribed:true,subscriptionFingerprint:null,source:{connected:true},settings:{notify_enabled:true,rows:auth==='owner-token'?4:1,notify_interval_seconds:60,min_percent:null,excluded_ranks:[],excluded_coins:auth==='owner-token'?['BTC']:['ETH'],excluded_modes:[],excluded_exchanges:[]}});
 const fetch=async(url,options)=>{
  const route=url.split('/').pop(),auth=options.headers.Authorization.slice(7);requests.push({route,auth,body:options.body&&JSON.parse(options.body)});
  const hooked=responseHook?.(route,auth,options);if(hooked!==undefined)return hooked;
  if(route==='switch-subscription'&&transferFailure){if(transferFailure==='network')throw Error('offline');return {status:400,ok:false,json:async()=>({error:'目标推送码已绑定另一台手机'})}}
  if(route===failRoute&&auth==='other-token')return {status:401,ok:false,json:async()=>({error:'目标码读取失败'})};
  if(route==='pair')return JSON.parse(options.body).code==='87654321'?{ok:true,status:200,json:async()=>({token:'other-token'})}:{ok:false,status:400,json:async()=>({error:'推送码不正确'})};
  return {ok:true,status:200,json:async()=>route==='status'||route==='settings'?plan(auth):route==='desktop-settings'?{revision:auth==='owner-token'?17:22,connected:true}:route==='binding'?{pushCode:auth==='owner-token'?'12345678':'87654321'}:{ok:true}};
 };
 const subscription={toJSON:()=>({endpoint:android?'https://fcm.googleapis.com/wp/synthetic':'https://fixture.push.apple.com/local',keys:{p256dh:'test',auth:'test'}})};
 const notification={permission:permission||(subscribed?'granted':'default'),requestPermission:async()=>{actions.push('permission');notification.permission=permission||'granted';return notification.permission}};
 const navigator={userAgent:ios?'iPhone':android?'Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile':'Desktop',standalone:installed,serviceWorker:{register:async()=>{actions.push('register');return {active:{postMessage:(data,ports)=>{workerTokens.push(data.token);ports[0].postMessage({ok:!(workerFailure&&data.token==='other-token'),version:typeof workerVersion==='function'?workerVersion(data.token):workerVersion})}},pushManager:{getSubscription:async()=>subscribed?subscription:null,subscribe:async()=>{actions.push('subscribe');if(subscribeError){const error=Error('fixture');error.name=subscribeError;throw error}subscribed=true;return subscription}},update:async()=>{}}},addEventListener(){}}};
 class MessageChannel{constructor(){const first=this.port1={close(){}};this.port2={postMessage:data=>queueMicrotask(()=>first.onmessage({data}))}}}
 class CustomEvent{constructor(type,options={}){this.type=type;this.detail=options.detail}}
 const context=vm.createContext({CustomEvent,document,navigator,fetch,crypto:webcrypto,TextEncoder,Uint8Array,MessageChannel,setTimeout,clearTimeout,queueMicrotask,Notification:notification,PushManager:supported?function(){}:undefined,isSecureContext:secure,atob:value=>Buffer.from(value,'base64').toString('binary'),location:{pathname:'/radar/robot-push/'},matchMedia:()=>({matches:installed}),localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
 context.AbortSignal=AbortSignal;context.window=context;context.addEventListener=(name,fn)=>windowEvents[name]=fn;
 vm.runInContext(source,context);
 const run=code=>vm.runInContext(code,context);
 return {elements,storage,requests,workerTokens,events,actions,emitted,windowEvents,run};
}
// WebCrypto completes on native workers; event-loop turns are not a time budget
// and can all finish before a loaded CI runner delivers its digest result.
async function settle(f){const deadline=Date.now()+3000;do{await new Promise(resolve=>setTimeout(resolve,5));if(!f.run('busy'))return}while(Date.now()<deadline);throw Error('operation did not settle within 3 seconds')}
async function switchCode(f,code){f.elements.get('ns-switch').hidden=false;f.elements.get('ns-switch-code').value=code;f.elements.get('ns-switch').onsubmit({preventDefault(){}});await settle(f)}

test('switch loads the target revision/settings and saves only to its token',async()=>{
 const f=fixture();await f.run('load()');await switchCode(f,'87654321');
 assert.equal(f.run('token'),'other-token');assert.equal(f.run('revision'),2);
 assert.equal(f.elements.get('ns-bound-code').textContent,'87654321');assert.equal(f.elements.get('ns-coins').value,'ETH');
 assert.equal(f.storage.get('radar-test-token'),'owner-token');assert.equal(f.storage.get('radar-settings-token'),'other-token');
 // Form controls normally stringify assigned values in browsers.
 f.elements.get('ns-ranks').value='';f.elements.get('ns-percent').value='';
 f.elements.get('ns-form').onsubmit({preventDefault(){}});await settle(f);
 const saved=f.requests.find(r=>r.route==='settings');assert.equal(saved.auth,'other-token');assert.equal(saved.body.revision,2);
 assert.equal(f.requests.filter(r=>r.route==='subscribe').length,0);
});

test('wrong code or failed target load retains original token, code, revision and draft',async()=>{
 for(const failRoute of ['', 'status', 'binding']){
  const f=fixture({failRoute});await f.run('load()');f.elements.get('ns-coins').value='UNSAVED';
  await switchCode(f,failRoute?'87654321':'00000000');
  assert.equal(f.run('token'),'owner-token');assert.equal(f.run('revision'),7);
  assert.equal(f.elements.get('ns-bound-code').textContent,'12345678');assert.equal(f.elements.get('ns-coins').value,'UNSAVED');
  assert.equal(f.storage.get('radar-test-token'),'owner-token');assert.equal(f.storage.has('radar-settings-token'),false);
  assert.equal(f.elements.get('ns-switch').hidden,false);assert.ok(f.elements.get('ns-switch-error').textContent);
 }
});

test('restored selection never configures or reports the phone under the viewed plan',async()=>{
 const f=fixture({savedSelection:'other-token',ios:true});await settle(f);await f.run('load()');
 await f.run('configureWorker()');
 assert.equal(f.run('token'),'other-token');assert.ok(f.workerTokens.length>0);
 assert.ok(f.workerTokens.every(token=>token==='owner-token'));
 assert.ok(f.requests.filter(r=>r.route==='device').every(r=>r.auth==='owner-token'));
 assert.equal(f.elements.get('ns-enable').disabled,false);
 assert.equal(f.storage.get('radar-test-token'),'owner-token');
});

test('cancelling switch leaves the form draft untouched',async()=>{
 const f=fixture();await f.run('load()');f.elements.get('ns-coins').value='UNSAVED';
 f.elements.get('ns-switch-open').onclick();f.elements.get('ns-switch-code').value='87654321';f.elements.get('ns-switch-cancel').onclick();
 assert.equal(f.elements.get('ns-switch').hidden,true);assert.equal(f.elements.get('ns-switch-code').value,'');
 assert.equal(f.elements.get('ns-coins').value,'UNSAVED');assert.equal(f.run('token'),'owner-token');
});


test('phone switch moves only its subscription then configures target worker and device',async()=>{
 const f=fixture({ios:true,subscribed:true});await settle(f);await f.run('load()');
 await switchCode(f,'87654321');
 const moved=f.requests.find(r=>r.route==='switch-subscription');assert.equal(moved.auth,'owner-token');assert.equal(moved.body.targetToken,'other-token');
 assert.equal(f.storage.get('radar-test-token'),'other-token');assert.equal(f.storage.get('radar-settings-token'),'other-token');
 assert.equal(f.workerTokens.at(-1),'other-token');assert.equal(f.requests.filter(r=>r.route==='device').at(-1).auth,'other-token');
 assert.equal(f.storage.has('radar-phone-switch'),false);assert.equal(f.elements.get('ns-coins').value,'ETH');
});

test('dated v6 cache builds can switch iPhone and Android profiles without changing protocol',async()=>{
 for(const workerVersion of ['radar-delivery-v6-20261018-treasure1','radar-delivery-v6-20261019-startup1'])for(const phone of [{ios:true},{android:true}]){
  const f=fixture({...phone,subscribed:true,workerVersion});await settle(f);await f.run('load()');await switchCode(f,'87654321');
  const moved=f.requests.filter(r=>r.route==='switch-subscription');assert.equal(moved.length,1);assert.equal(moved[0].auth,'owner-token');
  assert.equal(f.storage.get('radar-test-token'),'other-token');assert.equal(f.workerTokens.at(-1),'other-token');
  assert.equal(f.requests.filter(r=>r.route==='device').at(-1).body.version,workerVersion);
  assert.equal(f.storage.has('radar-phone-switch'),false);assert.equal(f.elements.get('ns-coins').value,'ETH');
 }
});

test('other protocols and malformed v6 versions stay blocked before transferring a subscription',async()=>{
 for(const workerVersion of ['radar-delivery-v5','radar-delivery-v7','radar-delivery-v60','radar-delivery-v5-20261019-startup1','radar-delivery-v7-20261019-startup1','radar-delivery-v6evil','radar-delivery-v6-','radar-delivery-v6-20261019-','radar-delivery-v6-startup1','radar-delivery-v6-20261019-STARTUP1','radar-delivery-v6-20261019-startup1/unknown','radar-delivery-v6-20261019-'+('x'.repeat(96)),null,6]){
  const f=fixture({ios:true,subscribed:true,workerVersion});await settle(f);await f.run('load()');await switchCode(f,'87654321');
  assert.equal(f.requests.some(r=>r.route==='switch-subscription'),false,`${workerVersion} must not transfer`);
  assert.equal(f.storage.get('radar-test-token'),'owner-token');assert.equal(f.storage.has('radar-phone-switch'),false);
  assert.match(f.elements.get('ns-message').textContent,/通知组件正在更新/);
 }
});

test('pending switch recovery accepts a dated v6 build and reuses its original transfer request',async()=>{
 let targetVersion='radar-delivery-v7';
 const f=fixture({ios:true,subscribed:true,workerVersion:auth=>auth==='owner-token'?'radar-delivery-v6':targetVersion});
 await settle(f);await f.run('load()');await switchCode(f,'87654321');
 assert.equal(f.storage.get('radar-test-token'),'other-token');assert.equal(f.storage.has('radar-phone-switch'),true);
 assert.equal(f.elements.get('ns-save').disabled,true);const first=f.requests.find(r=>r.route==='switch-subscription');
 targetVersion='radar-delivery-v6-20261019-startup1';await f.run('task(load)');
 const attempts=f.requests.filter(r=>r.route==='switch-subscription');assert.equal(attempts.length,2);assert.deepEqual(attempts[1],first);
 assert.equal(f.storage.has('radar-phone-switch'),false);assert.equal(f.elements.get('ns-save').disabled,false);
 assert.equal(f.elements.get('ns-coins').value,'ETH');assert.equal(f.workerTokens.at(-1),'other-token');
});

test('dated v6 builds also switch a phone with no existing subscription',async()=>{
 const f=fixture({ios:true,subscribed:false,workerVersion:'radar-delivery-v6-20261019-startup1'});
 await settle(f);await f.run('load()');await switchCode(f,'87654321');
 assert.equal(f.requests.some(r=>r.route==='switch-subscription'),false);
 assert.equal(f.storage.get('radar-test-token'),'other-token');assert.equal(f.workerTokens.at(-1),'other-token');
 assert.equal(f.storage.has('radar-phone-switch'),false);assert.equal(f.elements.get('ns-coins').value,'ETH');
});

test('occupied target retains original phone binding and draft',async()=>{
 const f=fixture({ios:true,subscribed:true,transferFailure:'occupied'});await settle(f);await f.run('load()');f.elements.get('ns-coins').value='DRAFT';
 await switchCode(f,'87654321');assert.equal(f.storage.get('radar-test-token'),'owner-token');assert.equal(f.workerTokens.at(-1),'owner-token');
 assert.equal(f.elements.get('ns-coins').value,'DRAFT');assert.equal(f.storage.has('radar-phone-switch'),false);
});

test('uncertain transfer retains recovery request and disables settings until retry',async()=>{
 const f=fixture({ios:true,subscribed:true,transferFailure:'network'});await settle(f);await f.run('load()');await switchCode(f,'87654321');
 assert.ok(f.storage.has('radar-phone-switch'));assert.equal(f.storage.get('radar-test-token'),'owner-token');assert.equal(f.elements.get('ns-save').disabled,true);
 const original=JSON.parse(f.storage.get('radar-phone-switch'));await assert.rejects(f.run('load()'));
 assert.equal(JSON.parse(f.storage.get('radar-phone-switch')).request.requestId,original.request.requestId);
});

test('worker configuration failure after server commit retains recoverable target binding',async()=>{
 const f=fixture({ios:true,subscribed:true,workerFailure:true});await settle(f);await f.run('load()');await switchCode(f,'87654321');
 assert.equal(f.storage.get('radar-test-token'),'other-token');assert.ok(f.storage.has('radar-phone-switch'));assert.equal(f.elements.get('ns-save').disabled,true);
 assert.ok(!f.elements.get('ns-message').textContent.includes('本机现在'));
});


test('Android browser enables notifications without requiring home-screen installation',async()=>{
 const f=fixture({android:true});await settle(f);await f.run('load()');
 assert.ok(f.actions.includes('register'));assert.equal(f.run('phoneApp'),true);assert.equal(f.run('standalone'),false);
 f.elements.get('ns-enable').onclick();await settle(f);
 assert.deepEqual(f.actions.slice(-2),['permission','subscribe']);
 const request=f.requests.find(r=>r.route==='subscribe');assert.ok(request.body.subscription.endpoint.startsWith('https://fcm.googleapis.com/wp/'));
 assert.equal(request.auth,'owner-token');assert.equal(f.elements.get('ns-enable').textContent,'通知已开启');
});

test('Android browser and installed app transfer the local subscription when switching',async()=>{
 for(const installed of [false,true]){
  const f=fixture({android:true,installed,subscribed:true});await settle(f);await f.run('load()');await switchCode(f,'87654321');
  assert.equal(f.storage.get('radar-test-token'),'other-token');assert.equal(f.workerTokens.at(-1),'other-token');
  assert.equal(f.requests.find(r=>r.route==='switch-subscription').body.targetToken,'other-token');
 }
});

test('denied Android permission and push-service failures show actionable errors without saving a subscription',async()=>{
 for(const options of [{permission:'denied'},{subscribeError:'AbortError'}]){
  const f=fixture({android:true,...options});await settle(f);await f.run('load()');f.elements.get('ns-enable').onclick();await settle(f);
  assert.equal(f.requests.some(r=>r.route==='subscribe'),false);assert.equal(f.elements.get('ns-enable').disabled,false);
  assert.match(f.elements.get('ns-message').textContent,options.permission?/安卓系统/:/推送服务/);
 }
});

test('unsupported Android, desktop and Safari tab cannot silently subscribe',async()=>{
 for(const options of [{android:true,supported:false},{android:true,secure:false},{},{ios:true,installed:false}]){
  const f=fixture(options);await settle(f);await f.run('load()');f.elements.get('ns-enable').onclick();await settle(f);
  assert.equal(f.actions.includes('register'),false);assert.equal(f.actions.includes('permission'),false);
  assert.equal(f.requests.some(r=>r.route==='subscribe'),false);assert.ok(f.elements.get('ns-message').textContent);
 }
});


const response=value=>({ok:true,status:200,json:async()=>value});
test('integrated settings accept an ordinary profile and save only its desktop scheme',async()=>{
 const f=fixture({integratedAccount:true,savedSelection:'other-token'});await settle(f);
 assert.ok(f.requests.some(r=>r.route==='desktop-settings'&&r.auth==='other-token'));
 assert.equal(f.emitted.filter(e=>e.type==='radar-desktop-loaded').at(-1).detail.revision,22);
 await f.run("window.RadarDesktopSettings.save({revision:22,channel:'desktop'})");
 const saved=f.requests.find(r=>r.route==='desktop-settings'&&r.body);
 assert.equal(saved.auth,'other-token');assert.equal(saved.body.revision,22);
 assert.equal(f.requests.some(r=>r.route==='subscribe'||r.route==='switch-subscription'),false);
});

test('late desktop response is discarded after a successful profile switch',async()=>{
 let resolveOld;const old=new Promise(resolve=>resolveOld=resolve);
 const f=fixture({integratedAccount:true,responseHook:(route,auth)=>route==='desktop-settings'&&auth==='owner-token'?old:undefined});
 await settle(f);await switchCode(f,'87654321');resolveOld(response({revision:17,connected:true}));await new Promise(r=>setTimeout(r,20));
 const loaded=f.emitted.filter(e=>e.type==='radar-desktop-loaded');assert.equal(loaded.length,1);assert.equal(loaded[0].detail.revision,22);
 assert.equal(f.emitted.filter(e=>e.type==='radar-profile-changing').length,1);
});

test('returning to the same token cannot accept an earlier request generation',async()=>{
 let hold=false,resolveRead;const pending=new Promise(resolve=>resolveRead=resolve);
 const f=fixture({integratedAccount:true,responseHook:route=>hold&&route==='desktop-settings'?pending:undefined});await settle(f);
 hold=true;const reading=f.run("window.RadarDesktopSettings.status()");const rejected=assert.rejects(reading,/推送码已切换/);
 f.run("selectIdentity('other-token');selectIdentity('owner-token')");resolveRead(response({revision:99}));await rejected;
 assert.equal(f.emitted.filter(e=>e.type==='radar-desktop-loaded').at(-1).detail.revision,17);
});

test('a failed target read keeps the current integrated identity and drafts valid',async()=>{
 const f=fixture({integratedAccount:true,failRoute:'binding'});await settle(f);const before=f.emitted.filter(e=>e.type==='radar-desktop-loaded').length;
 await switchCode(f,'87654321');assert.equal(f.run('token'),'owner-token');assert.equal(f.emitted.some(e=>e.type==='radar-profile-changing'),false);
 assert.equal(f.emitted.filter(e=>e.type==='radar-desktop-loaded').length,before);
});
