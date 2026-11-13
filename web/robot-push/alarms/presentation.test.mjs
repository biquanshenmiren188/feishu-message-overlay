import test from 'node:test';
import assert from 'node:assert/strict';
import {presentRule} from './presentation.js';

const rule=(status='watching',extra={})=>({enabled:true,state:{status,sampleAt:90,observedAt:98,...extra}});
test('device wall clock cannot override a healthy server route',()=>{
 const original=Date.now;
 try{
  for(const skew of [-86400,1.2,86400]){
   Date.now=()=>(100+skew)*1000;
   assert.deepEqual(presentRule(rule(),{serverTime:100}),{status:'watching',fresh:true});
  }
 }finally{Date.now=original;}
});
test('delayed responses hide old prices without inventing an exchange outage',()=>{
 assert.deepEqual(presentRule(rule(),{serverTime:100,elapsed:4}),{status:'watching',fresh:false});
});
test('new fallback snapshot restores price even if source timestamp is older',()=>{
 const r=rule('watching',{sampleAt:103,observedAt:104,source:{fallback:true,exchange:'okx'}});
 assert.deepEqual(presentRule(r,{serverTime:105,elapsed:.5}),{status:'watching',fresh:true});
});
test('actual server outage remains an outage despite a recent prior price',()=>{
 assert.deepEqual(presentRule(rule('stale'),{serverTime:100}),{status:'stale',fresh:false});
});
test('offline cached snapshots and legacy responses never show a live price',()=>{
 assert.equal(presentRule(rule(),{serverTime:100,verified:false}).fresh,false);
 assert.equal(presentRule(rule(),{}).fresh,false);
 assert.equal(presentRule(rule(),{serverTime:100,elapsed:13}).fresh,false);
});
test('receipt duration uses elapsed monotonic time, rejects invalid and future samples',()=>{
 for(const elapsed of [-1,NaN,Infinity])assert.equal(presentRule(rule(),{serverTime:100,elapsed}).fresh,false);
 assert.equal(presentRule(rule('watching',{sampleAt:104}),{serverTime:100}).fresh,false);
 assert.equal(presentRule(rule('watching',{observedAt:80}),{serverTime:100}).fresh,false);
});
test('paused expired and one-shot status remain independent of device clock',()=>{
 assert.equal(presentRule({...rule(),enabled:false},{serverTime:100}).status,'paused');
 assert.equal(presentRule({...rule(),expiresAt:99},{serverTime:100}).status,'expired');
 assert.equal(presentRule(rule('triggered'),{serverTime:100}).status,'triggered');
});
