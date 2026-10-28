import test from 'node:test';
import assert from 'node:assert/strict';
import {FeedPolicyState,fingerprintMessage,fingerprintText,DECISION_TTL} from './feed-policy.js';

const now=Date.parse('2026-10-28T14:00:00Z');
const message=(id,extra={})=>({id,groupId:'ordinary',senderType:'bot',title:'R0 +0.4% | UNITREE | FF',body:'买 GATE 卖 ASTER',sentAt:new Date(now-60000).toISOString(),actions:[],...extra});
async function ingest(state,batch,time=now){state.ingest(batch,time);for(const [id,raw] of state.raw)state.recordHash(id,fingerprintText(raw),await fingerprintMessage(raw));}
async function decision(state,actions,time=now){
  const entries=await Promise.all(Object.entries(actions).map(async([id,action])=>[id,{action,fingerprint:await fingerprintMessage(state.raw.get(id))}]));
  state.accept({revision:1,desktopEnabled:true,decisions:Object.fromEntries(entries)},time);
}

test('message fingerprints match the backend Unicode/raw-time fixture',async()=>{
  const raw=message('a'.repeat(64),{title:'机器人 🧪 | FF',body:'买 GATE → 卖 ASTER\n"报价" \\ 测试\u2028',sentAt:'2026-10-28T21:01:17.123+08:00'});
  assert.equal(await fingerprintMessage(raw),'66027d99003130040699f969da2f2272763924f6e80555d93053a0c2b3094c59');
  assert.equal(fingerprintText({...raw,title:null}),null);
});
test('public browser receives everything; a bound profile waits and filters normal/pinned history',async()=>{
  const state=new FeedPolicyState();await ingest(state,{messages:[message('normal'),message('allowed')],pinned:message('strong',{groupId:'pin'})});
  assert.equal(state.project(now).messages.length,2);assert.equal(state.project(now).pinned.id,'strong');
  state.reset('first');assert.deepEqual(state.project(now),{messages:[],pinned:null});
  await decision(state,{normal:'hide',allowed:'allow',strong:'hide'});
  assert.deepEqual(state.project(now).messages.map(value=>value.id),['allowed']);assert.equal(state.project(now).pinned,null);
});
test('unblocking restores retained history without replaying sound, then blocking removes it again',async()=>{
  const state=new FeedPolicyState();state.reset('first');await ingest(state,{messages:[message('normal')],pinned:null});
  await decision(state,{normal:'hide'});assert.equal(state.project(now).messages.length,0);
  await decision(state,{normal:'allow'});assert.equal(state.project(now).messages.length,1);assert.deepEqual(state.takeAudible(now),[]);
  await decision(state,{normal:'hide'});assert.equal(state.project(now).messages.length,0);
});
test('mute remains visible but never sounds; only a newly allowed arrival is audible once',async()=>{
  const state=new FeedPolicyState();state.reset('first');await ingest(state,{messages:[message('baseline')],pinned:null});
  await ingest(state,{messages:[message('muted'),message('allowed'),message('hidden')],pinned:null});
  await decision(state,{baseline:'allow',muted:'mute',allowed:'allow',hidden:'hide'});
  assert.deepEqual(state.project(now).messages.map(value=>value.id),['baseline','muted','allowed']);
  assert.deepEqual(state.takeAudible(now).map(value=>value.id),['allowed']);assert.deepEqual(state.takeAudible(now),[]);
  await decision(state,{baseline:'allow',muted:'allow',allowed:'allow',hidden:'allow'});assert.deepEqual(state.takeAudible(now),[]);
});
test('unknown history, expired proof, disabled reception and changed identity fail closed',async()=>{
  const state=new FeedPolicyState();state.reset('first');await ingest(state,{messages:[message('normal'),message('unknown')]});
  await decision(state,{normal:'allow'});assert.equal(state.project(now).messages.length,1);
  assert.equal(state.project(now+DECISION_TTL).messages.length,0);
  state.accept({...state.data,desktopEnabled:false},now);assert.equal(state.project(now).messages.length,0);
  state.reset('second');assert.equal(state.project(now).messages.length,0);
  state.reset('');assert.equal(state.project(now).messages.length,2);assert.deepEqual(state.takeAudible(now),[]);
});
test('same ID changed body or raw sentAt cannot reuse the old allow proof',async()=>{
  const state=new FeedPolicyState();state.reset('first');await ingest(state,{messages:[message('same')]});await decision(state,{same:'allow'});
  const old=state.data;await ingest(state,{messages:[message('same',{body:'新的被屏蔽币种内容'})]});
  assert.equal(state.project(now).messages.length,0);assert.equal(state.source.messages[0].body,'新的被屏蔽币种内容');
  await decision(state,{same:'allow'});assert.equal(state.project(now).messages.length,1);
  state.accept(old,now);assert.equal(state.project(now).messages.length,0);
});
test('retained raw history remains bounded and clearing the pin removes it immediately',async()=>{
  const state=new FeedPolicyState();await ingest(state,{messages:Array.from({length:120},(_,i)=>message('m'+i,{sentAt:new Date(now-i*1000).toISOString()})),pinned:message('pin',{groupId:'pin'})});
  assert.equal(state.source.messages.length,30);assert.equal(state.raw.size,31);await ingest(state,{messages:[],pinned:null});
  assert.equal(state.source.messages.length,30);assert.equal(state.raw.size,30);assert.equal(state.project(now).pinned,null);
});
test('invalid API responses are rejected rather than interpreted as all-allow',()=>{
  const state=new FeedPolicyState();for(const data of [null,{}, {revision:1,desktopEnabled:true,decisions:[]},{revision:1,desktopEnabled:true,decisions:{x:{action:'allow',fingerprint:'bad'}}},{revision:1,desktopEnabled:true,decisions:{x:{action:'unknown',fingerprint:'a'.repeat(64)}}}])assert.throws(()=>state.accept(data,now));
});
test('blocked snapshot includes only known hidden source text and clears on expiry or identity changes',async()=>{
  const state=new FeedPolicyState();state.reset('first');await ingest(state,{messages:[message('hidden'),message('muted'),message('pending')],pinned:message('pin',{groupId:'pin'})});
  await decision(state,{hidden:'hide',muted:'mute',pin:'hide'});
  const snapshot=state.blockedSnapshot(now);assert.equal(snapshot.ready,true);assert.deepEqual(snapshot.blocked.map(message=>message.id),['hidden','pin']);
  assert.deepEqual(Object.keys(snapshot.blocked[0]).sort(),['body','id','sentAt','title']);
  assert.deepEqual(state.blockedSnapshot(now+DECISION_TTL),{bound:true,ready:false,blocked:[]});
  state.reset('second');assert.deepEqual(state.blockedSnapshot(now),{bound:true,ready:false,blocked:[]});
  state.reset('');assert.deepEqual(state.blockedSnapshot(now),{bound:false,ready:false,blocked:[]});
});
