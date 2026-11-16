import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

const source=fs.readFileSync(new URL('./blocked-pushes.js',import.meta.url),'utf8').replaceAll('export function ','function ');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 class Element extends EventTarget{
  constructor(tag){super();this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.textContent='';}
  append(...nodes){for(const node of nodes){node.parent=this;this.children.push(node);}}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  setAttribute(k,v){this.attrs[k]=v;}
  focus(){} showModal(){this.open=true;}
  close(){this.open=false;this.dispatchEvent(new Event('close'));}
  remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 }
 const document=new EventTarget(),window=new EventTarget(),storage=new Map([['radar-settings-token','test-a']]);
 Object.assign(document,{head:new Element('head'),body:new Element('body'),hidden:false,createElement:tag=>new Element(tag),querySelector:()=>null});
 const toolbar=new Element('div'),requests=[],intervals=[];let gate=null,status=200;
 const fetch=async(url,options)=>{
  const auth=options.headers.Authorization;
  requests.push({url,auth,signal:options.signal});
  if(gate)await gate;
  const item={id:auth,channel:'desktop',action:'hide',at:1,coin:auth,reasons:['blocked']};
  return {ok:status===200,status,json:async()=>url.endsWith('/status')?{blockedHistory:[item]}:{history:[item]}};
 };
 const ctx=vm.createContext({document,window,localStorage:{getItem:k=>storage.get(k)||null},fetch,Event,AbortController,setTimeout,clearTimeout,queueMicrotask,setInterval:fn=>{intervals.push(fn);},toolbar});
 vm.runInContext(source,ctx);const api=vm.runInContext('createBlockedPushes(toolbar)',ctx);
 const nodes=()=>{const all=[];function walk(n){all.push(n);for(const child of n.children)walk(child);}walk(document.body);return all;};
 const find=text=>nodes().find(n=>n.tag==='button'&&n.textContent.startsWith(text));
 const snapshot=()=>{const event=new Event('radar-feed-policy-snapshot');event.detail={bound:true,ready:true,blocked:[]};document.dispatchEvent(event);};
 document.addEventListener('radar-feed-policy-request',snapshot);snapshot();
 return {document,window,toolbar,storage,requests,intervals,api,nodes,find,gate:p=>gate=p,status:n=>status=n};
}

test('closed history viewer makes no API requests at startup, polling, focus or visibility',async()=>{
 const f=fixture();
 for(let n=0;n<60;n++){for(const tick of f.intervals)tick();f.window.dispatchEvent(new Event('focus'));f.document.dispatchEvent(new Event('visibilitychange'));}
 await f.api.refresh();await settle();assert.equal(f.requests.length,0);
 assert.equal(f.toolbar.children[0].textContent,'已屏蔽 0 条');
});

test('open fetches once, repeated wake preserves snapshot, explicit refresh and reopen fetch again',async()=>{
 const f=fixture();f.toolbar.children[0].onclick();await settle();assert.equal(f.requests.length,2);
 for(let n=0;n<10;n++){f.window.dispatchEvent(new Event('focus'));for(const tick of f.intervals)tick();}
 await settle();assert.equal(f.requests.length,2);
 f.find('刷新').onclick();await settle();assert.equal(f.requests.length,4);
 f.find('关闭').onclick();await f.api.refresh();assert.equal(f.requests.length,4);
 f.toolbar.children[0].onclick();await settle();assert.equal(f.requests.length,6);f.find('关闭').onclick();
});

test('close cancels pending reads and late responses cannot become the new profile history',async()=>{
 const f=fixture();let release;f.gate(new Promise(r=>release=r));
 f.toolbar.children[0].onclick();assert.equal(f.requests.length,2);await f.api.refresh();assert.equal(f.requests.length,2);
 f.find('关闭').onclick();assert(f.requests.every(r=>r.signal.aborted));
 f.storage.set('radar-settings-token','test-b');f.window.dispatchEvent(new Event('storage'));
 f.gate(null);f.toolbar.children[0].onclick();await settle();release();await settle();
 f.find('电脑历史').onclick();const text=f.nodes().map(n=>n.textContent).join(' ');
 assert(text.includes('test-b'));assert(!text.includes('test-a'));f.find('关闭').onclick();
});

test('unauthorized reads show error; switching or clearing identity closes private history',async()=>{
 const f=fixture();f.status(401);f.toolbar.children[0].onclick();await settle();f.find('电脑历史').onclick();
 assert(f.nodes().some(n=>n.textContent.includes('连接已失效')));
 f.storage.clear();f.window.dispatchEvent(new Event('storage'));await settle();
 assert(!f.nodes().some(n=>n.tag==='dialog'));assert(f.toolbar.children[0].disabled);
 assert(f.requests.every(r=>r.url.includes('/api/')&&!r.url.includes('settings?')));
});
