import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('./sw.js',import.meta.url),'utf8');
test('failed receipt upload survives and is flushed by a later foreground configure',async()=>{
 const events={},state=new Map([['token','a'.repeat(40)]]),uploads=[];let online=false,ack;
 const context=vm.createContext({URL,Response,setTimeout,clearTimeout,AbortSignal,
  fetch:async(url,options)=>{uploads.push(JSON.parse(options.body));return {ok:online}},
  self:{location:{origin:'https://leida.shenmiren.work'},addEventListener:(name,fn)=>{events[name]=fn}}});
 vm.runInContext(source,context);context.state=state;
 vm.runInContext('get=async key=>state.get(key);put=async(key,value)=>state.set(key,value)',context);
 await vm.runInContext("report({seq:99,stage:'display-requested',version:VERSION})",context);
 assert.equal(state.get('outbox').length,1);
 online=true;let pending;
 events.message({data:{type:'configure',token:'a'.repeat(40)},ports:[{postMessage:r=>{ack=r}}],waitUntil:p=>{pending=p}});
 await pending;
 assert.equal(ack.version,'radar-delivery-v5');assert.equal(state.get('outbox').length,0);
 assert.equal(uploads.at(-1).records[0].seq,99);assert.equal(uploads.at(-1).records[1].stage,'foreground-sync');
 assert.ok(!JSON.stringify(uploads).includes('a'.repeat(40)));
});
test('cache population failure does not prevent worker activation',async()=>{
 const events={};let skipped=false;
 const context=vm.createContext({URL,Response,setTimeout,clearTimeout,AbortSignal,
  caches:{open:async()=>({addAll:async()=>{throw Error('offline')}})},
  self:{location:{origin:'https://leida.shenmiren.work'},addEventListener:(name,fn)=>{events[name]=fn},skipWaiting:async()=>{skipped=true}}});
 vm.runInContext(source,context);let pending;
 events.install({waitUntil:p=>{pending=p}});await pending;assert.equal(skipped,true);
});

test('Apple declarative PushEvent with null data is displayed and acknowledged',async()=>{
 const events={},state=new Map(),shown=[],reports=[];
 const context=vm.createContext({URL,Response,setTimeout,clearTimeout,AbortSignal,
  self:{location:{origin:'https://leida.shenmiren.work'},addEventListener:(name,fn)=>{events[name]=fn},registration:{getNotifications:async()=>[],showNotification:async(title,options)=>shown.push({title,options})}}});
 vm.runInContext(source,context);context.state=state;context.reports=reports;
 vm.runInContext('get=async key=>state.get(key);put=async(key,value)=>state.set(key,value);report=async record=>reports.push(record)',context);
 let pending;
 events.push({data:null,notification:{title:'雷达',body:'first\nlast',data:{kind:'radar-six-test',seq:100,run:'verify'}},waitUntil:p=>{pending=p}});
 await pending;assert.equal(shown.length,1);assert.equal(shown[0].options.body,'first\nlast');assert.equal(shown[0].title,'');
 assert.equal(reports.at(-1).stage,'display-requested');assert.equal(reports.at(-1).seq,100);
});
