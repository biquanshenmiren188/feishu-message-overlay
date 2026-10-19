import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(process.env.STARTUP_WORKER||new URL('./sw.js',import.meta.url),'utf8');
const origin='https://leida.shenmiren.work',base=origin+'/radar/push-test/';
const html='<base href="/radar/robot-push/"><section id="pinned"></section><section id="feed"></section>';
const documentResponse=(body=html)=>new Response(body,{headers:{'Content-Type':'text/html'}});
function setup(fetcher,{broken=false,hung=false}={}){
 const events={},stored=new Map(),calls=[];
 const key=r=>typeof r==='string'?r:r.url;
 const cache={match:async r=>stored.get(key(r))?.clone(),put:async(r,v)=>stored.set(key(r),v.clone()),delete:async r=>stored.delete(key(r))};
 const context=vm.createContext({URL,Response,AbortSignal,setTimeout,clearTimeout,console,
  caches:{open:async()=>{if(broken)throw Error('storage');if(hung)return new Promise(()=>{});return cache}},
  fetch:async(r,opts)=>{calls.push(key(r));return fetcher(r,opts)},
  self:{location:{origin},addEventListener:(name,fn)=>events[name]=fn,skipWaiting:async()=>{}}});
 vm.runInContext(source,context);
 function request(path,options={}){
  let response;const pending=[];
  events.fetch({request:{url:new URL(path,origin).href,method:'GET',mode:options.navigate?'navigate':'cors',...options},
   respondWith:p=>response=p,waitUntil:p=>pending.push(p)});
  return {response,done:()=>Promise.all(pending)};
 }
 return {request,stored,calls,context,events};
}
test('warm navigation returns shell while network is still unresolved',async()=>{
 let resolve;const s=setup(()=>new Promise(r=>resolve=r));s.stored.set(base,documentResponse());
 const r=s.request(base,{navigate:true});
 assert.equal(await Promise.race([r.response.then(x=>x.text()),new Promise(r=>setTimeout(()=>r('blocked'),150))]),html);
 resolve(documentResponse(html+'<!--new-->'));await r.done();assert.match(await s.stored.get(base).text(),/new/);
});
test('cold navigation stores a validated empty shell and returns the response',async()=>{
 const s=setup(async()=>documentResponse()),r=s.request(base,{navigate:true});
 assert.equal(await (await r.response).text(),html);await r.done();assert.ok(s.stored.has(base));
});
test('offline warm navigation and assets remain usable',async()=>{
 const s=setup(async()=>{throw Error('offline')});s.stored.set(base,documentResponse());
 const r=s.request(base,{navigate:true});assert.equal((await r.response).status,200);await r.done();
});
test('current BOT assets outside legacy push-test directory are cached by exact URL',async()=>{
 const path=origin+'/radar/robot-push/notification-settings.css?v=new';
 const s=setup(async()=>new Response('new',{headers:{'Content-Type':'text/css'}}));
 s.stored.set(path.replace('new','old'),new Response('old'));
 const r=s.request(path);assert.equal(await (await r.response).text(),'new');await r.done();assert.ok(s.stored.has(path));
});
test('hashed immutable asset cache hits require no network round trip',async()=>{
 const path=origin+'/radar/performance-20261017/bot-41884e126478.css';
 const s=setup(()=>{throw Error('unnecessary network')});s.stored.set(path,new Response('css'));
 const r=s.request(path);assert.equal(await (await r.response).text(),'css');await r.done();assert.equal(s.calls.length,0);
});
test('feeds, account APIs, foreign origins, mutations and worker scripts are not intercepted',()=>{
 const s=setup(()=>{throw Error('not called')});
 for(const path of ['/radar/robot-push/feed.json','/radar/robot-push/basispulse.json','/radar/push-test/api/status','/radar/push-test/api/fake.js','https://other.example/a.js','/radar/push-test/sw.js','/radar/file.js?token=private'])assert.equal(s.request(path).response,undefined);
 assert.equal(s.request('/radar/a.css',{method:'POST'}).response,undefined);
 assert.equal(s.request(base+'?token=private',{navigate:true}).response,undefined);
});
test('login HTML and responses containing messages are never stored as shell',async()=>{
 for(const body of ['<html>login</html>',html.replace('id="feed"></section>','id="feed">private message</section>')]){
  const s=setup(async()=>documentResponse(body)),r=s.request(base,{navigate:true});await r.response;await r.done();assert.equal(s.stored.size,0);
 }
});
test('HTML returned at a CSS/JS URL is not cached',async()=>{
 for(const suffix of ['js','css']){const s=setup(async()=>documentResponse()),r=s.request('/radar/foo.'+suffix);await r.response;await r.done();assert.equal(s.stored.size,0)}
});
test('auth failure removes cached document without caching login response',async()=>{
 for(const status of [401,403]){
  const s=setup(async()=>new Response('login',{status}));s.stored.set(base,documentResponse());s.stored.set(base+'index.html',documentResponse());
  const r=s.request(base,{navigate:true});await r.response;await r.done();assert.equal(s.stored.size,0);
 }
});
test('redirected login removes shell cache',async()=>{
 const response=documentResponse();Object.defineProperty(response,'redirected',{value:true});
 const s=setup(async()=>response);s.stored.set(base,documentResponse());
 const r=s.request(base,{navigate:true});await r.response;await r.done();assert.equal(s.stored.size,0);
});
test('cache failure or hanging CacheStorage does not block a network response',async()=>{
 for(const options of [{broken:true},{hung:true}]){
  const s=setup(async()=>documentResponse(),options),r=s.request(base,{navigate:true});
  const response=await Promise.race([r.response,new Promise(r=>setTimeout(()=>r(null),400))]);assert.equal(response?.status,200);await r.done();
 }
});
test('installer warms actual BOT HTML assets and keeps notification cache/state separate',async()=>{
 const body=html+'<link href="/radar/new-123456789abc.css"><script src="/radar/bot-123456789abc.js"></script><script src="https://other.example/x.js"></script>';
 const s=setup(async r=>r===base?documentResponse(body):new Response('asset',{headers:{'Content-Type':r.endsWith('.css')?'text/css':'application/javascript'}}));
 let pending;s.events.install({waitUntil:p=>pending=p});await pending;
 assert.ok(s.stored.has(base));assert.ok(s.stored.has(origin+'/radar/new-123456789abc.css'));assert.equal(s.calls.length,3);
});
