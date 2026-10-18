import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('./sw.js',import.meta.url),'utf8');

test('profile switch scopes sequences and receipts and rejects delayed old pushes',async()=>{
 const events={},state=new Map([['token','a'.repeat(40)],['latest',{kind:'radar-six-test',seq:900,rows:['old code']}],['outbox',[{seq:900,stage:'display-requested'}]]]),shown=[],uploads=[];
 const context=vm.createContext({URL,Response,setTimeout,clearTimeout,AbortSignal,
  fetch:async(url,options)=>{uploads.push({auth:options.headers.Authorization,body:JSON.parse(options.body)});return {ok:true}},
  self:{location:{origin:'https://leida.shenmiren.work'},addEventListener:(name,fn)=>{events[name]=fn},registration:{getNotifications:async()=>[],showNotification:async(title,options)=>shown.push(options)}}});
 vm.runInContext(source,context);context.state=state;
 vm.runInContext('get=async key=>state.get(key);put=async(key,value)=>state.set(key,value)',context);
 const profile='b'.repeat(32),token='b'.repeat(40);let pending,ack;
 const configure=async(token,profile)=>{events.message({data:{type:'configure',token,profile},ports:[{postMessage:value=>ack=value}],waitUntil:p=>pending=p});await pending};
 await configure(token,profile);
 assert.equal(ack.ok,true);assert.equal(state.get('identity').profile,profile);
 async function push(profile,seq,rows){events.push({data:{json:()=>({kind:'radar-six-test',profile,seq,rows})},waitUntil:p=>pending=p});await pending}
 await push(profile,1,['new code']);assert.equal(shown[0].body,'new code');
 await push('legacy',901,['late old code']);assert.equal(shown.length,1);
 assert.equal(state.get('latest').seq,900);assert.equal(state.get('latest:'+profile).seq,1);
 assert.ok(uploads.every(item=>item.auth==='Bearer '+token));assert.ok(uploads.every(item=>item.body.records.every(record=>record.seq!==900)));
 await configure('a'.repeat(40));assert.equal(ack.ok,false);assert.equal(state.get('identity').profile,profile);
 await configure('a'.repeat(40),'legacy');await push('legacy',902,['returned code']);assert.equal(shown.at(-1).body,'returned code');
 assert.ok(uploads.some(item=>item.auth==='Bearer '+'a'.repeat(40)&&item.body.records.some(record=>record.seq===900)));
});

test('failed durable worker configuration does not acknowledge a switch',async()=>{
 const events={},state=new Map([['identity',{token:'a'.repeat(40),profile:'legacy'}]]);let pending,ack;
 const context=vm.createContext({URL,Response,setTimeout,clearTimeout,AbortSignal,self:{location:{origin:'https://leida.shenmiren.work'},addEventListener:(name,fn)=>events[name]=fn}});
 vm.runInContext(source,context);context.state=state;
 vm.runInContext("get=async key=>state.get(key);put=async()=>{throw Error('disk')}",context);
 events.message({data:{type:'configure',token:'b'.repeat(40),profile:'b'.repeat(32)},ports:[{postMessage:value=>ack=value}],waitUntil:p=>pending=p});await pending;
 assert.equal(ack.ok,false);assert.equal(state.get('identity').profile,'legacy');
});
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
 assert.equal(ack.version,'radar-delivery-v6-20261018-treasure1');assert.equal(state.get('outbox').length,0);
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
