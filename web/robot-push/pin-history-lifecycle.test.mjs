import test from 'node:test';
import assert from 'node:assert/strict';
import {createPinHistory} from './pin-history.js';

test('history starts independently, survives feed policy churn, isolates identity and retries failures',async()=>{
 const names=['window','document','localStorage','ResizeObserver','getComputedStyle','fetch','setTimeout','clearTimeout','setInterval'];
 const prior=new Map(names.map(n=>[n,Object.getOwnPropertyDescriptor(globalThis,n)]));
 const timers=new Map(),requests=[];let serial=0,identity='account-a';
 const document=Object.assign(new EventTarget(),{hidden:false,querySelector:()=>null});
 const element=Object.assign(new EventTarget(),{children:[],classList:{add(){}},style:{setProperty(){},removeProperty(){}},dataset:{},scrollTop:0,clientHeight:100,scrollHeight:100,
  setAttribute(){},removeAttribute(){},getBoundingClientRect:()=>({top:0,bottom:100}),
  replaceChildren(...nodes){this.children=nodes;this.scrollHeight=nodes.length*100;},get lastElementChild(){return this.children.at(-1);}});
 Object.defineProperty(element,'lastElementChild',{get(){return this.children.at(-1);}});
 element.parentElement={id:'board',before(node){node.parentElement={id:'board-shell'};}};
 Object.assign(globalThis,{document,window:new EventTarget(),localStorage:{getItem:()=>identity},ResizeObserver:class{observe(){}disconnect(){}},
  getComputedStyle:()=>({marginTop:'0',marginBottom:'0'}),setTimeout:(fn,ms)=>{const id=++serial;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),setInterval:()=>0,
  fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))});
 const settle=async()=>{for(let i=0;i<6;i++)await Promise.resolve();};
 const messages=Array.from({length:5},(_,n)=>({id:'pin'+n,title:'强信号聚集 | TEST | 3组',body:'原文',sentAt:new Date(1700000000000+n*1000).toISOString(),actions:[]}));
 const reply=(r,data,ok=true)=>r.resolve({ok,json:async()=>data});
 try{
  const manager=createPinHistory({element,renderCard:m=>({dataset:{id:m.id},getBoundingClientRect:()=>({top:0,bottom:100,height:100}),querySelector:()=>null})});
  await settle();assert.equal(requests.length,1,'first request must not wait for feed');assert.equal(element.parentElement.id,'board-shell');
  document.dispatchEvent(Object.assign(new Event('radar-feed-policy-snapshot'),{detail:{bound:true,ready:false}}));
  manager.setCurrent({...messages[0],id:'ordinary',title:'R0 | FF | TEST'});
  manager.setCurrent(null);
  assert.equal(requests.length,1);assert.equal(requests[0].options.signal.aborted,false);
  reply(requests[0],{messages,currentId:'pin4',sourceCurrentId:'different-current'});await settle();
  assert.deepEqual(element.children.map(n=>n.dataset.id),messages.map(m=>m.id));
  document.dispatchEvent(Object.assign(new Event('radar-feed-policy-snapshot'),{detail:{bound:true,ready:false}}));
  assert.equal(element.children.length,5,'unrelated policy refresh cannot clear independently filtered history');
  document.dispatchEvent(new Event('radar-rules-saved'));await settle();assert.equal(element.children.length,0);assert.equal(requests.length,2);
  reply(requests[1],{},false);await settle();assert.equal(element.dataset.historyError,'true');
  const retry=[...timers.values()].find(t=>t.ms===1000);assert.ok(retry,'retry without waiting 15s');retry.fn();await settle();assert.equal(requests.length,3);
  identity='account-b';document.dispatchEvent(new Event('radar-profile-changing'));await settle();
  assert.equal(requests[2].options.signal.aborted,true);assert.equal(requests.at(-1).options.headers.Authorization,'Bearer account-b');
  reply(requests[2],{messages,currentId:'pin4'});await settle();assert.equal(element.children.length,0,'late prior-account response discarded');
  reply(requests.at(-1),{messages:messages.slice(0,2),currentId:'pin1'});await settle();assert.equal(element.children.length,2);
 }finally{for(const [n,d]of prior)d?Object.defineProperty(globalThis,n,d):delete globalThis[n];}
});
