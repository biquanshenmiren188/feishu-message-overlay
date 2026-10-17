import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createScrollGate,stablePaneBottom} from './mobile-scroll.js';
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
