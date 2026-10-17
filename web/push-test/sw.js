'use strict';
const VERSION='radar-six-test-v3', KIND='radar-six-test', BASE='/radar/push-test/';
const ASSETS=['','index.html','style.css','app.js','manifest.webmanifest','icon-192.png','icon-512.png'];
self.addEventListener('install',event=>event.waitUntil((async()=>{const cache=await caches.open(VERSION);await cache.addAll(ASSETS.map(x=>BASE+x));await self.skipWaiting()})()));
self.addEventListener('activate',event=>event.waitUntil((async()=>{await self.clients.claim();if(await self.registration.pushManager.getSubscription())await report({stage:'worker-ready',version:VERSION})})()));
self.addEventListener('fetch',event=>{const u=new URL(event.request.url);if(event.request.method!=='GET'||u.origin!==self.location.origin||!u.pathname.startsWith(BASE)||u.pathname.includes('/api/'))return;event.respondWith((async()=>{try{const r=await fetch(event.request);if(r.ok&&!r.redirected)return r;throw Error('offline')}catch{return (await (await caches.open(VERSION)).match(event.request,{ignoreSearch:true}))||Response.error()}})())});
function db(){return new Promise((resolve,reject)=>{const r=indexedDB.open(KIND,1);r.onupgradeneeded=()=>r.result.createObjectStore('state');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}
async function get(key){const d=await db();try{return await new Promise((resolve,reject)=>{const r=d.transaction('state').objectStore('state').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)})}finally{d.close()}}
async function put(key,value){const d=await db();try{await new Promise((resolve,reject)=>{const t=d.transaction('state','readwrite');t.objectStore('state').put(value,key);t.oncomplete=resolve;t.onerror=()=>reject(t.error)})}finally{d.close()}}
self.addEventListener('message',event=>{if(event.data?.type==='configure'&&/^[A-Za-z0-9_-]{32,100}$/.test(event.data.token||''))event.waitUntil((async()=>{await put('token',event.data.token);event.ports[0]?.postMessage({ok:true});const pending=await get('lastReceipt');if(pending)await report(pending)})().catch(()=>event.ports[0]?.postMessage({ok:false})));});
async function report(record){await put('lastReceipt',record);const token=await get('token');if(!token)return;try{await fetch(BASE+'api/receipt',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(record),redirect:'error'})}catch{/* The local receipt survives a failed network request. */}}
async function display(payload){
  if(payload?.kind!==KIND||!Number.isSafeInteger(payload.seq)||!Array.isArray(payload.rows)||payload.rows.length<1||payload.rows.length>6||payload.rows.some(x=>typeof x!=='string'||x.length>130))throw Error('invalid_test_payload');
  const last=await get('latest');const current=last&&last.seq>payload.seq?last:payload;
  await put('latest',current);
  let before=[],enumerationError=false;try{before=(await self.registration.getNotifications()).filter(n=>n.data?.kind===KIND)}catch{enumerationError=true}
  // Show first. A failed display must not destroy the last visible notification.
  // Unique tags avoid the known WebKit same-tag notification bookkeeping defect.
  await self.registration.showNotification(current.title===''?'':'雷达 · 测试',{body:current.rows.join('\n'),tag:KIND+'-'+current.seq,icon:BASE+'icon-192.png',badge:BASE+'icon-192.png',silent:false,data:{kind:KIND,seq:current.seq,run:current.run,url:BASE}});
  let closeCalls=0;for(const notification of before){try{notification.close();closeCalls++}catch{}}
  let after=null;try{after=(await self.registration.getNotifications()).filter(n=>n.data?.kind===KIND).length}catch{}
  await report({seq:current.seq,run:current.run,rows:current.rows.length,before:before.length,closeCalls,after,enumerationError,stage:'display-requested',version:VERSION});
}
let queue=Promise.resolve();
self.addEventListener('push',event=>{let p;try{p=event.data.json()}catch{return}queue=queue.catch(()=>{}).then(()=>display(p));event.waitUntil(queue.catch(async()=>{await report({seq:p?.seq||0,stage:'worker-error',version:VERSION})}));});
self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(self.clients.openWindow(BASE))});
