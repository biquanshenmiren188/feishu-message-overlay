'use strict';
const VERSION='radar-delivery-v6-20261019-startup1', KIND='radar-six-test', BASE='/radar/push-test/';
// Rendering must not depend on storage, notification enumeration or telemetry.
function bounded(promise,ms,fallback){return new Promise(resolve=>{const timer=setTimeout(()=>resolve(fallback),ms);Promise.resolve(promise).then(value=>{clearTimeout(timer);resolve(value)},()=>{clearTimeout(timer);resolve(fallback)})})}
self.addEventListener('install',event=>event.waitUntil((async()=>{await bounded(warmStartup().catch(()=>{}),3000,null);await self.skipWaiting()})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{await self.clients.claim();await report({stage:'worker-ready',version:VERSION})})()));
// Only the empty application shell and static assets belong in this cache.
// Keep this separate from notification identity, receipts and sequence state.
const STARTUP_CACHE='radar-startup-v1';
const shellPath=path=>path===BASE||path===BASE+'index.html';
function staticAsset(url){
 return url.origin===self.location.origin&&url.pathname.startsWith('/radar/')&&
  [...url.searchParams.keys()].every(key=>key==='v')&&
  !url.pathname.includes('/api/')&&!/\/(?:sw|app)\.js$/.test(url.pathname)&&
  /\.(?:css|js|svg|png|ico|webp|avif|woff2)$/.test(url.pathname);
}
const immutableAsset=url=>/-[a-f0-9]{12,64}\.(?:css|js)$/.test(url.pathname);
async function startupMatch(request){
 return bounded(Promise.resolve().then(()=>caches.open(STARTUP_CACHE)).then(cache=>cache.match(request)),80,null);
}
async function storeStartup(request,response,navigation){
 if(!response.ok||response.redirected||response.type==='opaque')return;
 const type=response.headers.get('Content-Type')||'';
 if(navigation){
  if(!type.includes('text/html'))return;
  const html=await response.clone().text();
  // Never persist a login page or HTML that already contains private messages.
  if(html.length>150000||!/<base href="\/radar\/robot-push\/">/.test(html)||
     !/<section\b[^>]*id="feed"[^>]*>\s*<\/section>/.test(html)||
     !/<section\b[^>]*id="pinned"[^>]*>\s*<\/section>/.test(html))return;
 }else{
  const path=new URL(typeof request==='string'?request:request.url,self.location.origin).pathname;
  if(path.endsWith('.js')&&!/(?:javascript|ecmascript)/.test(type))return;
  if(path.endsWith('.css')&&!type.includes('text/css'))return;
  if(!/\.(?:js|css)$/.test(path)&&!/^(?:image\/|font\/|application\/(?:font|octet-stream))/.test(type))return;
 }
 await (await caches.open(STARTUP_CACHE)).put(request,response.clone());
}
async function warmStartup(){
 const url=new URL(BASE,self.location.origin).href;
 const response=await fetch(url,{cache:'no-cache',credentials:'same-origin',signal:AbortSignal.timeout(8000)});
 await storeStartup(url,response,true);
 if(!response.ok||response.redirected)return;
 const html=await response.text(),assets=new Set();
 for(const match of html.matchAll(/\b(?:src|href)="([^"]+)"/g)){
  const asset=new URL(match[1],self.location.origin+'/radar/robot-push/');
  if(staticAsset(asset))assets.add(asset.href);
 }
 await Promise.allSettled([...assets].slice(0,24).map(async asset=>{
  const response=await fetch(asset,{cache:'no-cache',credentials:'same-origin',signal:AbortSignal.timeout(8000)});
  await storeStartup(asset,response,false);
 }));
}
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url),navigation=request.mode==='navigate'&&shellPath(url.pathname)&&!url.search;
 if(request.method!=='GET'||url.origin!==self.location.origin||(!navigation&&!staticAsset(url)))return;
 // Register background work synchronously, before returning from the event.
 const cached=startupMatch(request);
 const network=cached.then(async hit=>{
  if(hit&&!navigation&&immutableAsset(url))return hit;
  const response=await fetch(request,{cache:'no-cache',signal:AbortSignal.timeout(10000)});
  // A revoked session must not leave a reusable document behind. Static shell
  // contains no account data; APIs always go through the network/auth gateway.
  if(navigation&&(response.redirected||response.status===401||response.status===403)){
   await bounded(caches.open(STARTUP_CACHE).then(cache=>Promise.all([
    cache.delete(new URL(BASE,self.location.origin).href),
    cache.delete(new URL(BASE+'index.html',self.location.origin).href)
   ])),100,null);
  }else await bounded(storeStartup(request,response,navigation),100,null);
  return response;
 });
 event.waitUntil(network.then(()=>{},()=>{}));
 event.respondWith(cached.then(hit=>hit||network).catch(()=>Response.error()));
});
function db(){return new Promise((resolve,reject)=>{let expired=false;const timer=setTimeout(()=>{expired=true;reject(Error('database_timeout'))},2500),r=indexedDB.open(KIND,1);r.onupgradeneeded=()=>r.result.createObjectStore('state');r.onsuccess=()=>{clearTimeout(timer);if(expired)r.result.close();else resolve(r.result)};r.onerror=()=>{clearTimeout(timer);reject(r.error)}})}
async function get(key){const d=await db();try{return await new Promise((resolve,reject)=>{const r=d.transaction('state').objectStore('state').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}finally{d.close()}}
async function put(key,value){const d=await db();try{await new Promise((resolve,reject)=>{const t=d.transaction('state','readwrite'),timer=setTimeout(()=>{try{t.abort()}catch{}reject(Error('database_timeout'))},2500);t.objectStore('state').put(value,key);t.oncomplete=()=>{clearTimeout(timer);resolve()};t.onerror=t.onabort=()=>{clearTimeout(timer);reject(t.error||Error('database_aborted'))}})}finally{d.close()}}
let memoryToken='', memoryProfile='', memoryLatest=null, reportQueue=Promise.resolve();
const scoped=(key,profile)=>!profile||profile==='legacy'?key:key+':'+profile;
async function identity(){const saved=await bounded(get('identity'),150,null);return {token:memoryToken||saved?.token||await bounded(get('token'),150,''),profile:memoryProfile||saved?.profile||''}}
async function flush(){
 const {token,profile}=await identity();if(!token)return;
 const key=scoped('outbox',profile),records=await bounded(get(key),200,[]);if(!records?.length)return;
 try{const response=await fetch(BASE+'api/receipt-batch',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({records}),redirect:'error',signal:AbortSignal.timeout(3000)});if(response.ok)await bounded(put(key,[]),200,null)}catch{/* Retain records for the next foreground synchronization. */}
}
function report(record,send=true){
 record={...record,eventAt:Math.floor(Date.now()/1000)};
 reportQueue=reportQueue.catch(()=>{}).then(async()=>{
  const {profile}=await identity(),key=scoped('outbox',profile);
  const records=await bounded(get(key),200,[])||[];
  await bounded(put(scoped('lastReceipt',profile),record),200,null);
  await bounded(put(key,[...records,record].slice(-20)),200,null);
  if(send)await flush();
 });return reportQueue;
}
self.addEventListener('message',event=>{
 if(event.data?.type==='configure'&&/^[A-Za-z0-9_-]{32,100}$/.test(event.data.token||'')){
  queue=queue.catch(()=>{}).then(async()=>{
   await reportQueue.catch(()=>{});
   const previous=await identity(),profile=event.data.profile||previous.profile||'legacy';
   if(!/^(legacy|[a-f0-9]{32})$/.test(profile))throw Error('invalid_profile');
   // An old page must never move a v6 worker back to a previously bound code.
   if(!event.data.profile&&previous.token&&previous.token!==event.data.token)throw Error('stale_page');
   await put('identity',{token:event.data.token,profile});
   if(memoryProfile!==profile)memoryLatest=null;
   memoryToken=event.data.token;memoryProfile=profile;
   event.ports[0]?.postMessage({ok:true,version:VERSION});await report({stage:'foreground-sync',version:VERSION});
  });event.waitUntil(queue.catch(()=>event.ports[0]?.postMessage({ok:false})));
 }
});
async function display(payload){
 if(payload?.kind!==KIND||!Number.isSafeInteger(payload.seq)||!Array.isArray(payload.rows)||payload.rows.length<1||payload.rows.length>6||payload.rows.some(x=>typeof x!=='string'||x.length>130))throw Error('invalid_test_payload');
 const {profile}=await identity();
 // Discard old-code pushes still in the transport queue after a switch.
 if(profile&&(payload.profile||'legacy')!==profile)return;
 const received=report({seq:payload.seq,run:payload.run,stage:'push-received',version:VERSION},false);
 const latestKey=scoped('latest',profile||payload.profile);
 const persisted=await bounded(get(latestKey),150,null);
 const last=memoryLatest&&(!persisted||memoryLatest.seq>persisted.seq)?memoryLatest:persisted;
 const current=last&&last.seq>payload.seq?last:payload;
 const found=await bounded(self.registration.getNotifications(),150,null);
 const before=(found||[]).filter(n=>n.data?.kind===KIND&&(n.data?.seq!==current.seq||n.data?.profile!==current.profile));
 await self.registration.showNotification(current.title===''?'':'雷达 · 测试',{body:current.rows.join('\n'),tag:KIND+'-'+(current.profile||'legacy')+'-'+current.seq,icon:BASE+'icon-192.png',badge:BASE+'icon-192.png',silent:false,data:{kind:KIND,profile:current.profile,seq:current.seq,run:current.run,url:BASE}});
 memoryLatest=current;
 // Persist only after display succeeds; failed display must not supersede the last visible data.
 await bounded(put(latestKey,current),150,null);
 let closeCalls=0;for(const notification of before){try{notification.close();closeCalls++}catch{}}
 const afterList=await bounded(self.registration.getNotifications(),150,null);
 await received;
 await report({seq:current.seq,run:current.run,rows:current.rows.length,before:before.length,closeCalls,after:afterList?afterList.filter(n=>n.data?.kind===KIND).length:null,enumerationError:found===null,stage:'display-requested',version:VERSION});
}
let queue=Promise.resolve();
self.addEventListener('push',event=>{
 // WebKit gives mutable declarative pushes a Notification and NULL event.data.
 let p;try{p=event.notification?{...event.notification.data,title:'',rows:event.notification.body.split('\n')}:event.data.json()}catch{return}
 queue=queue.catch(()=>{}).then(()=>display(p));
 event.waitUntil(queue.catch(async error=>{await report({seq:p?.seq||0,stage:'worker-error',error:/^[A-Za-z]+Error$/.test(error?.name)?error.name:'Error',version:VERSION})}));
});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(self.clients.openWindow(BASE))});
