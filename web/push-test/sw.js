'use strict';
const VERSION='radar-delivery-v5', KIND='radar-six-test', BASE='/radar/push-test/';
const ASSETS=['','index.html','style.css','app.js','manifest.webmanifest','icon-192.png','icon-512.png'];
// Rendering must not depend on storage, notification enumeration or telemetry.
function bounded(promise,ms,fallback){return new Promise(resolve=>{const timer=setTimeout(()=>resolve(fallback),ms);Promise.resolve(promise).then(value=>{clearTimeout(timer);resolve(value)},()=>{clearTimeout(timer);resolve(fallback)})})}
self.addEventListener('install',event=>event.waitUntil((async()=>{await bounded(caches.open(VERSION).then(cache=>cache.addAll(ASSETS.map(x=>BASE+x))),3000,null);await self.skipWaiting()})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{await self.clients.claim();await report({stage:'worker-ready',version:VERSION})})()));
self.addEventListener('fetch',event=>{const u=new URL(event.request.url);if(event.request.method!=='GET'||u.origin!==self.location.origin||!u.pathname.startsWith(BASE)||u.pathname.includes('/api/'))return;event.respondWith((async()=>{try{const r=await fetch(event.request);if(r.ok&&!r.redirected)return r;throw Error('offline')}catch{return (await (await caches.open(VERSION)).match(event.request,{ignoreSearch:true}))||Response.error()}})())});
function db(){return new Promise((resolve,reject)=>{const r=indexedDB.open(KIND,1);r.onupgradeneeded=()=>r.result.createObjectStore('state');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}
async function get(key){const d=await db();try{return await new Promise((resolve,reject)=>{const r=d.transaction('state').objectStore('state').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}finally{d.close()}}
async function put(key,value){const d=await db();try{await new Promise((resolve,reject)=>{const t=d.transaction('state','readwrite');t.objectStore('state').put(value,key);t.oncomplete=resolve;t.onerror=()=>reject(t.error)})}finally{d.close()}}
let memoryToken='', memoryLatest=null, reportQueue=Promise.resolve();
async function flush(){
 const token=memoryToken||await bounded(get('token'),200,'');if(!token)return;
 const records=await bounded(get('outbox'),200,[]);if(!records?.length)return;
 try{const response=await fetch(BASE+'api/receipt-batch',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({records}),redirect:'error',signal:AbortSignal.timeout(3000)});if(response.ok)await bounded(put('outbox',[]),200,null)}catch{/* Retain records for the next foreground synchronization. */}
}
function report(record,send=true){
 record={...record,eventAt:Math.floor(Date.now()/1000)};
 reportQueue=reportQueue.catch(()=>{}).then(async()=>{
  const records=await bounded(get('outbox'),200,[])||[];
  await bounded(put('lastReceipt',record),200,null);
  await bounded(put('outbox',[...records,record].slice(-20)),200,null);
  if(send)await flush();
 });return reportQueue;
}
self.addEventListener('message',event=>{
 if(event.data?.type==='configure'&&/^[A-Za-z0-9_-]{32,100}$/.test(event.data.token||''))event.waitUntil((async()=>{
  memoryToken=event.data.token;await bounded(put('token',memoryToken),200,null);
  event.ports[0]?.postMessage({ok:true,version:VERSION});await report({stage:'foreground-sync',version:VERSION});
 })().catch(()=>event.ports[0]?.postMessage({ok:false})));
});
async function display(payload){
 if(payload?.kind!==KIND||!Number.isSafeInteger(payload.seq)||!Array.isArray(payload.rows)||payload.rows.length<1||payload.rows.length>6||payload.rows.some(x=>typeof x!=='string'||x.length>130))throw Error('invalid_test_payload');
 const received=report({seq:payload.seq,run:payload.run,stage:'push-received',version:VERSION},false);
 const persisted=await bounded(get('latest'),150,null);
 const last=memoryLatest&&(!persisted||memoryLatest.seq>persisted.seq)?memoryLatest:persisted;
 const current=last&&last.seq>payload.seq?last:payload;
 const found=await bounded(self.registration.getNotifications(),150,null);
 const before=(found||[]).filter(n=>n.data?.kind===KIND&&n.data?.seq!==current.seq);
 await self.registration.showNotification(current.title===''?'':'雷达 · 测试',{body:current.rows.join('\n'),tag:KIND+'-'+current.seq,icon:BASE+'icon-192.png',badge:BASE+'icon-192.png',silent:false,data:{kind:KIND,seq:current.seq,run:current.run,url:BASE}});
 memoryLatest=current;
 // Persist only after display succeeds; failed display must not supersede the last visible data.
 await bounded(put('latest',current),150,null);
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
