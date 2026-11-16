import test from 'node:test';
import assert from 'node:assert/strict';
import {createEntryPosition} from './entry-position.js';
function fixture(){
 const target=new EventTarget(),board=new EventTarget(),feed={children:[]},frames=new Map();let id=0,resize,busy=false,settled=0;
 target.document=new EventTarget();target.document.hidden=false;
 target.requestAnimationFrame=fn=>{frames.set(++id,fn);return id;};target.cancelAnimationFrame=id=>frames.delete(id);
 target.ResizeObserver=class{constructor(fn){resize=fn;}observe(){}};
 board.clientHeight=400;board.scrollHeight=2000;board.scrollTop=0;
 const entry=createEntryPosition({board,feed,target,prepare(){},settled(){settled++;},busy:()=>busy});
 return {entry,board,feed,target,resize:()=>resize(),busy:v=>busy=v,count:()=>settled,
  frame(){const todo=[...frames.values()];frames.clear();todo.forEach(fn=>fn());},flush(){for(let i=0;i<6;i++)this.frame();}};
}
test('empty and delayed feed reaches latest after layout settles',()=>{const f=fixture();f.entry.update();f.flush();assert(f.entry.pending);f.feed.children=[{}];f.entry.update();f.frame();f.board.scrollHeight=3000;f.flush();assert.equal(f.board.scrollTop,3000);assert.equal(f.count(),1);});
test('layout scroll cannot cancel initial jump',()=>{const f=fixture();f.feed.children=[{}];f.entry.update();f.frame();f.board.dispatchEvent(new Event('scroll'));f.flush();assert.equal(f.board.scrollTop,2000);});
test('manual touch between frames wins over pending initial jump',()=>{const f=fixture();f.feed.children=[{}];f.entry.update();f.frame();f.board.dispatchEvent(new Event('touchstart'));f.flush();assert.equal(f.board.scrollTop,0);assert(!f.entry.pending);});
test('hidden entry waits; visibility return and BFCache revisit go latest',()=>{const f=fixture();f.feed.children=[{}];f.target.document.hidden=true;f.entry.update();f.flush();assert(f.entry.pending);f.target.document.hidden=false;f.target.document.dispatchEvent(new Event('visibilitychange'));f.flush();assert.equal(f.count(),1);f.board.dispatchEvent(new Event('wheel'));f.board.scrollTop=50;const e=new Event('pageshow');e.persisted=true;f.target.dispatchEvent(e);f.flush();assert.equal(f.count(),2);assert.equal(f.board.scrollTop,2000);});
test('late size change keeps tail but never pulls manual history',()=>{const f=fixture();f.feed.children=[{}];f.entry.update();f.flush();f.board.scrollHeight=2500;f.resize();f.flush();assert.equal(f.board.scrollTop,2500);f.board.dispatchEvent(new Event('wheel'));f.board.scrollTop=400;f.resize();f.flush();assert.equal(f.board.scrollTop,400);});
test('busy layout retries on render and later arrivals keep timed reader',()=>{const f=fixture();f.feed.children=[{}];f.busy(true);f.entry.update();f.flush();assert(f.entry.pending);f.busy(false);f.entry.update();f.flush();f.board.scrollHeight=2800;f.entry.setAtTail(false);f.entry.update();f.resize();f.flush();assert.equal(f.board.scrollTop,2000);assert.equal(f.count(),1);});
