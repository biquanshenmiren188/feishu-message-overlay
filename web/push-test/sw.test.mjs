import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('./sw.js',import.meta.url),'utf8');
function setup({fail=false,latest=null}={}){
 const events=[],state=new Map(latest?[['latest',latest]]:[]),reports=[];
 const old={data:{kind:'radar-six-test',seq:1},close(){events.push('close-old')}};
 const unrelated={data:{kind:'unrelated'},close(){throw Error('must not close unrelated')}};
 let shown=false;
 const context=vm.createContext({console,URL,Response,setTimeout,self:{location:{origin:'https://leida.shenmiren.work'},addEventListener(){},registration:{async getNotifications(){return shown?[{data:{kind:'radar-six-test'}}]:[old,unrelated]},async showNotification(title,opts){events.push({title,opts});if(fail)throw Error('display failed');shown=true}}}});
 vm.runInContext(source,context);
 context.state=state;context.reports=reports;
 vm.runInContext('get=async key=>state.get(key);put=async(key,value)=>{state.set(key,value)};report=async record=>{reports.push(record)};',context);
 return {context,events,reports};
}
const payload={kind:'radar-six-test',seq:2,run:'abc',rows:['A 10:00','B 10:01']};
test('show succeeds before closing only captured test notifications',async()=>{const s=setup();s.context.p=payload;await vm.runInContext('display(p)',s.context);assert.equal(s.events[0].title,'雷达 · 测试');assert.equal(s.events[0].opts.body,'A 10:00\nB 10:01');assert.equal(s.events[1],'close-old');assert.equal(s.reports[0].closeCalls,1);assert.equal(s.reports[0].after,1)});
test('failed new notification preserves old notification',async()=>{const s=setup({fail:true});s.context.p=payload;await assert.rejects(vm.runInContext('display(p)',s.context));assert.equal(s.events.length,1)});
test('late push cannot roll content backward',async()=>{const latest={...payload,seq:9,rows:['Newest']};const s=setup({latest});s.context.p=payload;await vm.runInContext('display(p)',s.context);assert.equal(s.events[0].opts.body,'Newest');assert.equal(s.reports[0].seq,9)});
test('rejects more than six rows',async()=>{const s=setup();s.context.p={...payload,rows:Array(7).fill('test')};await assert.rejects(vm.runInContext('display(p)',s.context));assert.equal(s.events.length,0)});
