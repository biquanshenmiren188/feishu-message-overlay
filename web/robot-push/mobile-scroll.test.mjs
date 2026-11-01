import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createScrollGate,stablePaneBottom,preserveCardViewport,retireCardNode,clearCardPlaceholders,CARD_LAYOUT_GRACE_MS} from './mobile-scroll.js';
function fixture(){
 let time=0,id=0;const jobs=new Map(),target=new EventTarget(),phone=new EventTarget();
 target.document=new EventTarget();target.document.hidden=false;phone.matches=true;target.matchMedia=()=>phone;
 const later=(fn,delay)=>{jobs.set(++id,{fn,at:time+delay});return id},cancel=n=>jobs.delete(n);
 const gate=createScrollGate(target,{later,cancel});
 const tick=n=>{time+=n;for(const [key,j]of [...jobs])if(j.at<=time){jobs.delete(key);j.fn()}};
 const emit=(type,touches=[],origin=target)=>{const e=new Event(type);Object.defineProperty(e,'touches',{value:touches});Object.defineProperty(e,'target',{value:origin});target.dispatchEvent(e)};
 return {target,phone,gate,tick,emit,later,cancel};
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
 const nodeHeight=node=>parseFloat(node.style?.height)||node.height||0;
 const total=()=>base+Math.max(cards.reduce((sum,node)=>sum+nodeHeight(node),0),parseFloat(board.style.getPropertyValue('min-height'))||0)+100;
 target.document.scrollingElement={get scrollHeight(){return total()},get clientHeight(){return height}};
 target.document.querySelectorAll=()=>modal?[{hidden:false,getClientRects:()=>[{}]}]:[];
 const board={isConnected:true,parentElement:body,scrollHeight:0,clientHeight:0,querySelectorAll:selector=>selector==='.bp-reading-placeholder'?cards.filter(n=>n.className==='bp-reading-placeholder'):cards,
  getBoundingClientRect:()=>({top:base-target.scrollY,bottom:total()-100-target.scrollY,height:total()-base-100})};
 const values=new Map(),clamp=()=>{target.scrollY=Math.max(0,Math.min(maximum(),target.scrollY));};
 board.style={getPropertyValue:key=>values.get(key)||'',getPropertyPriority:()=>'',setProperty(key,value){values.set(key,value);clamp();},removeProperty(key){values.delete(key);clamp();}};
 target.getComputedStyle=()=>({position:'static',overflowY:'visible'});
 const maximum=()=>Math.max(0,total()-height);
 target.scrollTo=({top,behavior})=>{calls.push({top,behavior});target.scrollY=Math.max(0,Math.min(maximum(),top));};
 function nodeFor(row={}){
  const node={dataset:row.id?{id:row.id,pair:row.pair||''}:{},height:row.height||0,isConnected:true,parentElement:board,ownerDocument:target.document,style:{},className:row.id?'bp-card':'',textContent:row.id?'private card '+row.id:'',children:row.id?[{href:'https://example.test/private'}]:[],attributes:{},setAttribute(k,v){this.attributes[k]=v;}};
  node.getBoundingClientRect=()=>{const index=cards.indexOf(node),top=base+cards.slice(0,index).reduce((sum,n)=>sum+nodeHeight(n),0)-target.scrollY;return {top,bottom:top+nodeHeight(node),height:nodeHeight(node),width:380};};
  node.remove=()=>{cards=cards.filter(n=>n!==node);node.isConnected=false;clamp();};
  node.replaceWith=next=>{const index=cards.indexOf(node);node.remove();cards.splice(index,0,next);clamp();};
  return node;
 }
 target.document.createElement=()=>nodeFor();
 function set(rows,{clamp=true}={}){
  cards=rows.map(nodeFor);
  if(clamp)target.scrollY=Math.max(0,Math.min(maximum(),target.scrollY));
 }
 set(rows);const top=id=>cards.find(c=>c.dataset.id===id)?.getBoundingClientRect().top;
 const run=mutate=>preserveCardViewport(board,mutate,{target,gate:f.gate,later:f.later,cancel:f.cancel});
 return {...f,board,calls,run,set,top,node:id=>cards.find(c=>c.dataset.id===id),rows:()=>cards.map(c=>({id:c.dataset.id,pair:c.dataset.pair,height:c.height})),modal:on=>modal=on};
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
test('temporary document collapse is prevented throughout the complete DOM transaction',()=>{
 const f=cardFixture(),rows=f.rows(),before=f.top('b');
 f.run(()=>{f.set([]);assert.equal(f.target.scrollY,600);f.set(rows);});
 assert.equal(f.target.scrollY,600);assert.equal(f.top('b'),before);assert.equal(f.calls.length,0);
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

test('programmatic BOT and document scrolling cannot create a user gesture gate',()=>{
 const f=cardFixture(),nested={parentElement:f.target.document.body,scrollHeight:1000,clientHeight:200};
 f.emit('scroll',[],nested);f.emit('scroll');assert.equal(f.gate.active,false);assert.equal(f.gate.inputRevision,0);
 const before=f.top('c');f.run(()=>f.set(f.rows().filter(r=>r.id!=='a')));
 assert.equal(f.top('c'),before,'automatic message scrolling must not suppress card anchoring');
});

test('only the actual user scroller extends inertia; unrelated BOT auto-scroll does not',()=>{
 const f=cardFixture(),nested={parentElement:f.target.document.body,scrollHeight:1000,clientHeight:200};
 f.target.getComputedStyle=node=>({overflowY:node===nested?'auto':'visible'});
 f.emit('touchstart',[{}]);f.emit('touchend');f.tick(200);f.emit('scroll',[],nested);f.tick(40);
 assert.equal(f.gate.active,false,'nested programmatic motion must not prolong document inertia');
 f.emit('touchstart',[{}],nested);f.emit('touchend',[],nested);f.tick(200);f.emit('scroll',[],nested);f.tick(239);assert.equal(f.gate.active,true);f.tick(1);assert.equal(f.gate.active,false);
});

test('blocked and expired deletion preserves geometry during the real gesture and removes all content immediately',()=>{
 for(const policyBlocked of [true,false]){
  const f=cardFixture(),before=f.top('c'),y=f.target.scrollY,source=readFileSync(new URL('./basispulse.js',import.meta.url),'utf8');
  const body=source.slice(source.indexOf('function renderCards('),source.indexOf('\nconst cardPolicy='));
  const nodes=new Map(f.rows().map(row=>[row.id,{card:f.node(row.id)}])),model={tick:()=>policyBlocked?f.rows().map(row=>({data:{id:row.id}})):[]};
  let summaries=0;
  const deps={model,DISPLAY_REFRESH_MS:10000,failed:true,envelope:null,time:()=>'',count:{setAttribute(){},dataset:{}},cardPolicy:{visible:()=>false,summary(){summaries++;}},nodes,board:f.board,empty:{},retireCardNode:(node,deferred)=>retireCardNode(node,deferred,{target:f.target}),clearCardPlaceholders};
  const renderCards=Function(...Object.keys(deps),'let lastValuesAt=-Infinity;'+body+';return renderCards;')(...Object.values(deps));
  f.emit('touchstart',[{}]);const finish=()=>f.run(()=>renderCards(false));f.gate.defer(finish);renderCards(true);
  assert.equal(nodes.size,0);assert.equal(f.target.scrollY,y);assert.equal(summaries,0);
  const placeholders=f.board.querySelectorAll('.bp-reading-placeholder');assert.equal(placeholders.length,5);
  assert.equal(placeholders[2].getBoundingClientRect().top,before);
  for(const node of placeholders){assert.equal(node.textContent,'');assert.deepEqual(node.children,[]);assert.deepEqual(node.dataset,{});assert.equal(node.attributes['aria-hidden'],'true');assert.equal(node.inert,true);assert.equal(node.style.visibility,'hidden');assert.equal(node.style.pointerEvents,'none');}
  f.emit('touchend');f.tick(239);assert.equal(f.target.scrollY,y);assert.equal(f.board.querySelectorAll('.bp-reading-placeholder').length,5);
  f.tick(1);assert.equal(f.board.querySelectorAll('.bp-reading-placeholder').length,0);assert.equal(f.target.scrollY,y,'empty results get only a bounded geometry grace period');
  f.tick(CARD_LAYOUT_GRACE_MS);assert.equal(f.board.style.getPropertyValue('min-height'),'');
 }
});

test('nested feed render and fit transactions retain the outer height lock until final commit',()=>{
 const f=cardFixture(),rows=f.rows(),before=f.top('c');
 f.run(()=>{f.set([]);assert.equal(f.target.scrollY,600);f.run(()=>f.run(()=>{}));assert.equal(f.target.scrollY,600);assert.equal(f.board.style.getPropertyValue('min-height'),'1000px');f.set(rows);});
 assert.equal(f.top('c'),before);assert.equal(f.target.scrollY,600);assert.equal(f.board.style.getPropertyValue('min-height'),'');assert.equal(f.calls.length,0);
});

test('rules pending can clear then asynchronously refill without clamping or retaining card content',()=>{
 const f=cardFixture(),rows=f.rows(),before=f.top('c');f.run(()=>f.set([]));
 assert.equal(f.board.querySelectorAll('*').length,0);assert.equal(f.target.scrollY,600);assert.equal(f.board.style.getPropertyValue('min-height'),'1000px');
 f.tick(3000);f.run(()=>f.set(rows));assert.equal(f.top('c'),before);assert.equal(f.target.scrollY,600);assert.equal(f.board.style.getPropertyValue('min-height'),'');
 f.tick(1000);assert.equal(f.top('c'),before);assert.equal(f.calls.length,0);
});

test('repeated empty responses cannot extend the bounded geometry grace',()=>{
 const f=cardFixture();f.run(()=>f.set([]));f.tick(3000);f.run(()=>{});f.tick(499);assert.equal(f.target.scrollY,600);f.tick(1);
 assert.equal(f.board.style.getPropertyValue('min-height'),'');assert.equal(f.target.scrollY,0);assert.equal(f.calls.length,0);
});

test('a new gesture or viewport transition cancels empty recovery instead of restoring an old reading position',()=>{
 for(const action of [f=>f.emit('touchstart',[{}]),f=>f.emit('wheel'),f=>f.emit('keydown'),f=>f.emit('resize')]){
  const f=cardFixture(),rows=f.rows();f.run(()=>f.set([]));action(f);
  assert.equal(f.board.style.getPropertyValue('min-height'),'');assert.equal(f.target.scrollY,0);f.set(rows);f.tick(4000);f.run(()=>{});assert.equal(f.target.scrollY,0);assert.equal(f.calls.length,0);
 }
});

test('height reservation restores a pre-existing inline minimum and propagates failures',()=>{
 const f=cardFixture();f.board.style.setProperty('min-height','120px');const rows=f.rows();
 assert.throws(()=>f.run(()=>{f.set([]);f.set(rows);throw Error('commit failed');}),/commit failed/);
 assert.equal(f.board.style.getPropertyValue('min-height'),'120px');assert.equal(f.target.scrollY,600);
});
