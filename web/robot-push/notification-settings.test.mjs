import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';

const source=fs.readFileSync(new URL('./notification-settings.js',import.meta.url),'utf8');
function fixture({failRoute='',savedSelection='',ios=false,subscribed=false,transferFailure='',workerFailure=false}={}){
 const elements=new Map(),storage=new Map([['radar-test-token','owner-token']]),requests=[],workerTokens=[],events={};
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
 const document={createElement:()=>new Element(),createTextNode:text=>({text}),querySelector:()=>toolbar,head:new Element(),body:new Element(),addEventListener:(name,fn)=>events[name]=fn,visibilityState:'visible'};
 const plan=auth=>({profileId:auth==='owner-token'?'legacy':'a'.repeat(32),revision:auth==='owner-token'?7:2,publicKey:'AQID',subscribed:true,subscriptionFingerprint:null,source:{connected:true},settings:{notify_enabled:true,rows:auth==='owner-token'?4:1,notify_interval_seconds:60,min_percent:null,excluded_ranks:[],excluded_coins:auth==='owner-token'?['BTC']:['ETH'],excluded_modes:[],excluded_exchanges:[]}});
 const fetch=async(url,options)=>{
  const route=url.split('/').pop(),auth=options.headers.Authorization.slice(7);requests.push({route,auth,body:options.body&&JSON.parse(options.body)});
  if(route==='switch-subscription'&&transferFailure){if(transferFailure==='network')throw Error('offline');return {status:400,ok:false,json:async()=>({error:'目标推送码已绑定另一台手机'})}}
  if(route===failRoute&&auth==='other-token')return {status:401,ok:false,json:async()=>({error:'目标码读取失败'})};
  if(route==='pair')return JSON.parse(options.body).code==='87654321'?{ok:true,status:200,json:async()=>({token:'other-token'})}:{ok:false,status:400,json:async()=>({error:'推送码不正确'})};
  return {ok:true,status:200,json:async()=>route==='status'||route==='settings'?plan(auth):route==='binding'?{pushCode:auth==='owner-token'?'12345678':'87654321'}:{ok:true}};
 };
 const navigator={userAgent:ios?'iPhone':'Desktop',standalone:ios,serviceWorker:{register:async()=>({active:{postMessage:(data,ports)=>{workerTokens.push(data.token);ports[0].postMessage({ok:!(workerFailure&&data.token==='other-token'),version:'radar-delivery-v6'})}},pushManager:{getSubscription:async()=>subscribed?{toJSON:()=>({endpoint:'https://fixture.push.apple.com/local',keys:{p256dh:'test',auth:'test'}})}:null},update:async()=>{}}),addEventListener(){}}};
 class MessageChannel{constructor(){const first=this.port1={close(){}};this.port2={postMessage:data=>queueMicrotask(()=>first.onmessage({data}))}}}
 const context=vm.createContext({document,navigator,fetch,crypto:webcrypto,TextEncoder,Uint8Array,MessageChannel,setTimeout,clearTimeout,queueMicrotask,Notification:{permission:subscribed?'granted':'default'},location:{pathname:'/radar/robot-push/'},matchMedia:()=>({matches:ios}),localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}});
 vm.runInContext(source,context);
 const run=code=>vm.runInContext(code,context);
 return {elements,storage,requests,workerTokens,events,run};
}
async function settle(f){for(let i=0;i<30;i++){await new Promise(resolve=>setImmediate(resolve));if(!f.run('busy'))return}throw Error('operation did not settle')}
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
