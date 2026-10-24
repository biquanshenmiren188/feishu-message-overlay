import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createScrollGate,stablePaneBottom,preserveCardViewport} from './mobile-scroll.js';
function fixture(){
 let time=0,id=0;const jobs=new Map(),target=new EventTarget(),phone=new EventTarget();
 target.document=new EventTarget();target.document.hidden=false;phone.matches=true;target.matchMedia=()=>phone;
 const gate=createScrollGate(target,{later:(fn,delay)=>{jobs.set(++id,{fn,at:time+delay});return id},cancel:n=>jobs.delete(n)});
 const tick=n=>{time+=n;for(const [key,j]of [...jobs])if(j.at<=time){jobs.delete(key);j.fn()}};
 const emit=(type,touches=[])=>{const e=new Event(type);Object.defineProperty(e,'touches',{value:touches});target.dispatchEvent(e)};
 return {target,phone,gate,tick,emit};
}
test('keeps one latest structural render through finger motion and inertia',()=>{
 const f=fixture();let rendered=0,latest=0;const render=()=>rendered=latest;
 f.emit('touchstart',[{}]);latest=1;assert.equal(f.gate.defer(render),true);f.tick(1000);assert.equal(rendered,0);
 latest=2;f.gate.defer(render);f.emit('touchend');f.tick(200);f.emit('scroll');f.tick(239);assert.equal(rendered,0);
 latest=3;f.tick(1);assert.equal(rendered,3);assert.equal(f.gate.defer(render),false);
});
test('cancel and multitouch cannot leave the gate stuck',()=>{
 const f=fixture();let calls=0;const render=()=>calls++;
 f.emit('touchstart',[{},{}]);f.gate.defer(render);f.emit('touchend',[{}]);f.tick(300);assert.equal(calls,0);
 f.emit('touchcancel');f.tick(240);assert.equal(calls,1);
});
test('desktop is immediate and crossing desktop breakpoint flushes latest state',()=>{
 const f=fixture();let calls=0;const render=()=>calls++;
 f.emit('touchstart',[{}]);f.gate.defer(render);f.phone.matches=false;f.phone.dispatchEvent(new Event('change'));
 assert.equal(calls,1);assert.equal(f.gate.defer(render),false);
});
test('backgrounding mid gesture resumes without losing pending rendering',()=>{
 const f=fixture();let calls=0;const render=()=>calls++;
 f.emit('touchstart',[{}]);f.gate.defer(render);f.target.document.hidden=true;f.target.document.dispatchEvent(new Event('visibilitychange'));
 f.tick(1000);assert.equal(calls,0);f.target.document.hidden=false;f.target.document.dispatchEvent(new Event('visibilitychange'));assert.equal(calls,1);
});
test('pane-relative height survives page scrolling and browser chrome changes',()=>{
 const height=(bottom,top,viewport)=>stablePaneBottom(bottom,viewport,true)-top;
 assert.equal(height(720,200,640),520);assert.equal(height(420,-100,590),520);
 assert.equal(height(720,200,760),520);assert.equal(stablePaneBottom(720,640,false),640);
});

function cardFixture({scroll=600,height=600,base=300,rows=['a','b','c','d','e'].map(id=>({id,height:200}))}={}){
 const f=fixture(),{target}=f,calls=[];let cards=[],modal=false;
 target.innerHeight=height;target.scrollY=scroll;target.scrollX=0;
 const body={};target.document.body=body;target.document.documentElement=body;
 const total=()=>base+cards.reduce((sum,node)=>sum+node.height,0)+100;
 target.document.scrollingElement={get scrollHeight(){return total()},get clientHeight(){return height}};
 target.document.querySelectorAll=()=>modal?[{hidden:false,getClientRects:()=>[{}]}]:[];
 const board={isConnected:true,parentElement:body,scrollHeight:0,clientHeight:0,querySelectorAll:()=>cards,
  getBoundingClientRect:()=>({top:base-target.scrollY,bottom:total()-100-target.scrollY})};
 target.getComputedStyle=()=>({position:'static',overflowY:'visible'});
 const maximum=()=>Math.max(0,total()-height);
 target.scrollTo=({top,behavior})=>{calls.push({top,behavior});target.scrollY=Math.max(0,Math.min(maximum(),top));};
 function set(rows,{clamp=true}={}){
  cards=rows.map(row=>{const node={dataset:{id:row.id,pair:row.pair||''},height:row.height,isConnected:true};
   node.getBoundingClientRect=()=>{const index=cards.indexOf(node),top=base+cards.slice(0,index).reduce((sum,n)=>sum+n.height,0)-target.scrollY;return {top,bottom:top+node.height,height:node.height,width:380};};return node;});
  if(clamp)target.scrollY=Math.max(0,Math.min(maximum(),target.scrollY));
 }
 set(rows);const top=id=>cards.find(c=>c.dataset.id===id)?.getBoundingClientRect().top;
 const run=mutate=>preserveCardViewport(board,mutate,{target,gate:f.gate});
 return {...f,board,calls,run,set,top,rows:()=>cards.map(c=>({id:c.dataset.id,pair:c.dataset.pair,height:c.height})),modal:on=>modal=on};
}
test('removing an expired card above the reader preserves the same fractional viewport position',()=>{
 const f=cardFixture({scroll:300+284.527-90.256,rows:[{id:'bbb',height:284.527},{id:'ccc',height:420},{id:'ddd',height:420}]});
 // BBB overlaps the viewport top; the CCC being read must survive its removal.
 const before=f.top('ccc');f.run(()=>f.set(f.rows().filter(c=>c.id!=='bbb')));
 assert.ok(Math.abs(f.top('ccc')-before)<1e-9);assert.equal(f.calls.length,1);assert.equal(f.calls[0].behavior,'instant');
});
test('prepending, replacing heights, and sorting preserve a surviving reading card',()=>{
 const f=cardFixture(),before=f.top('b');
 f.run(()=>f.set([{id:'new',height:125},...f.rows().map(c=>c.id==='a'?{...c,height:275}:c)]));
 assert.equal(f.top('b'),before);
 const again=f.top('b');f.run(()=>f.set([f.rows().find(c=>c.id==='new'),f.rows().find(c=>c.id==='e'),...f.rows().filter(c=>!['new','e'].includes(c.id))]));
 assert.equal(f.top('b'),again);assert.equal(f.calls.length,2);
});
test('deleted first visible anchor falls back to the next surviving visible card',()=>{
 const f=cardFixture(),before=f.top('c');f.run(()=>f.set(f.rows().filter(c=>c.id!=='b')));
 assert.equal(f.top('c'),before);assert.equal(f.calls.length,1);
});
test('temporary document collapse and scrollY clamp are repaired from the final layout',()=>{
 const f=cardFixture(),rows=f.rows(),before=f.top('b');
 f.run(()=>{f.set([]);assert.equal(f.target.scrollY,0);f.set(rows);});
 assert.equal(f.target.scrollY,600);assert.equal(f.top('b'),before);assert.equal(f.calls.length,1);
});
test('already anchored browsers and repeated unchanged transactions do not compensate twice',()=>{
 const f=cardFixture(),before=f.top('b');f.run(()=>{f.set([{id:'new',height:100},...f.rows()]);f.target.scrollY+=100;});
 assert.equal(f.top('b'),before);assert.equal(f.calls.length,0);
 f.run(()=>{});f.run(()=>f.run(()=>{}));assert.equal(f.calls.length,0);
});
test('pair identity survives DOM replacement with a new message/card id',()=>{
 const f=cardFixture({rows:['a','b','c','d','e'].map(id=>({id,pair:`pair-${id}`,height:200}))}),before=f.top('b');
 f.run(()=>f.set([{id:'new',height:100},...f.rows().map(c=>c.id==='b'?{...c,id:'b-next'}:c)]));
 assert.equal(f.top('b-next'),before);assert.equal(f.calls.length,1);
});
test('no retained neighbour means no arbitrary old scroll offset restoration',()=>{
 const f=cardFixture();f.run(()=>f.set(['x','y','z'].map(id=>({id,height:300}))));assert.equal(f.calls.length,0);
});
test('document bottom clamp remains bounded when maintaining the exact offset is impossible',()=>{
 const f=cardFixture({scroll:800}),before=f.top('c');
 f.run(()=>f.set(f.rows().filter(c=>c.id!=='e')));
 assert.equal(f.target.scrollY,600);assert.ok(f.top('c')>=before);assert.equal(f.calls.length,0);
 f.run(()=>{});assert.equal(f.calls.length,0);
});
test('desktop, top BOT reading, modal, pinch zoom, and nested scrollers never move document scrolling',()=>{
 for(const disable of [f=>f.phone.matches=false,f=>f.target.scrollY=0,f=>f.modal(true),f=>f.target.visualViewport={offsetTop:0,height:600,scale:2},f=>{f.board.scrollHeight=1000;f.board.clientHeight=400;f.target.getComputedStyle=()=>({overflowY:'auto'});}]){
  const f=cardFixture();disable(f);let invoked=0;f.run(()=>{invoked++;f.set([{id:'new',height:100},...f.rows()]);});assert.equal(invoked,1);assert.equal(f.calls.length,0);
 }
 const top=cardFixture({base:500,scroll:20});top.run(()=>top.set([{id:'new',height:100},...top.rows()]));assert.equal(top.calls.length,0);
});
test('touch and inertia gates prevent restoration, then allow it only after quiet',()=>{
 const f=cardFixture();f.emit('touchstart',[{}]);assert.equal(f.gate.active,true);f.run(()=>f.set([{id:'n1',height:50},...f.rows()]));assert.equal(f.calls.length,0);
 f.emit('touchend');f.emit('scroll');f.tick(239);f.run(()=>f.set([{id:'n2',height:50},...f.rows()]));assert.equal(f.calls.length,0);
 f.tick(1);assert.equal(f.gate.active,false);const before=f.top('b');f.run(()=>f.set([{id:'n3',height:50},...f.rows()]));assert.equal(f.top('b'),before);assert.equal(f.calls.length,1);
});
test('new gesture, modal, or viewport transition during mutation cancels compensation',()=>{
 for(const transition of [f=>f.emit('touchstart',[{}]),f=>f.emit('wheel'),f=>f.modal(true),f=>f.target.innerHeight=500,f=>f.phone.matches=false]){
  const f=cardFixture();f.run(()=>{f.set([{id:'new',height:100},...f.rows()]);transition(f);});assert.equal(f.calls.length,0);
 }
});
test('promise-returning mutation never schedules restoration after later user activity',async()=>{
 const f=cardFixture();let resolve;const promise=new Promise(r=>resolve=r);
 const result=f.run(()=>{f.set([{id:'new',height:100},...f.rows()]);return promise;});assert.equal(result,promise);assert.equal(f.calls.length,0);
 f.emit('touchstart',[{}]);resolve('done');assert.equal(await result,'done');assert.equal(f.calls.length,0);
});
test('partial DOM mutation that throws still restores synchronously and propagates error',()=>{
 const f=cardFixture(),before=f.top('b');assert.throws(()=>f.run(()=>{f.set([{id:'new',height:100},...f.rows()]);throw Error('synthetic failure');}),/synthetic failure/);
 assert.equal(f.top('b'),before);assert.equal(f.calls.length,1);
});
