import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BotGate } from './filter.mjs';
const now = 1800000000000;
const fixture = () => ({sender: {sender_type:'bot',sender_id:{open_id:'synthetic-bot'}}, message:{chat_id:'oc_selected',chat_type:'group',message_id:'synthetic-message',create_time:String(now+1),message_type:'text',content:'{"text":"模拟告警"}'}});
test('only authorized group/bot: rejected metadata never accesses content', () => {
  const gate = new BotGate(['oc_selected'], now);
  for (const mode of ['user', 'wrong-group']) {
    const data = fixture(); if(mode==='user') data.sender.sender_type='user'; else data.message.chat_id='oc_other';
    Object.defineProperty(data.message,'content',{get(){throw new Error('body must not be accessed')}});
    assert.equal(gate.accept(data,now+2),null);
  }
});
test('new bot message once, same gate retained on SDK reconnect', () => {
  const gate = new BotGate(['oc_selected'],now); const data=fixture();
  assert.ok(gate.accept(data,now+2)); assert.equal(gate.accept(data,now+3),null);
});
test('restart/resume baseline prevents historical alarm', () => { const gate=new BotGate(['oc_selected'],now+3); assert.equal(gate.accept(fixture(),now+4),null); });
test('selection required, no all-group default', () => {assert.throws(()=>new BotGate([],now));assert.throws(()=>new BotGate(['display name'],now));});
test('dedup capacity refuses overflow without evicting IDs', () => {
  const gate=new BotGate(['oc_selected'],now);
  for(let i=0;i<10000;i++){const data=fixture();data.message.message_id='fake-'+i;gate.accept(data,now+2);}
  const extra=fixture();extra.message.message_id='overflow';assert.throws(()=>gate.accept(extra,now+2));
  const first=fixture();first.message.message_id='fake-0';assert.equal(gate.accept(first,now+2),null);
});
test('expired IDs are removed so long-running receiver recovers capacity',()=>{
  const gate=new BotGate(['oc_selected'],now);
  for(let i=0;i<10000;i++){const data=fixture();data.message.message_id='expired-'+i;gate.accept(data,now+2);}
  const later=now+31*60*1000;const data=fixture();data.message.create_time=String(later);data.message.message_id='fresh';
  assert.ok(gate.accept(data,later+1));assert.equal(gate.seen.size,1);
});
test('bot allowlist is identity based and checked before content',()=>{
  const gate=new BotGate(['oc_selected'],now,['different-bot']);const data=fixture();
  Object.defineProperty(data.message,'content',{get(){throw new Error('do not access rejected bot body')}});assert.equal(gate.accept(data,now+2),null);
});
test('recovery advances baseline so replay cannot alarm',()=>{const gate=new BotGate(['oc_selected'],now);gate.resume(now+10);assert.equal(gate.accept(fixture(),now+11),null);});

test('verified membership replacement adds new joined group and removes departed group before content',()=>{
 const gate=new BotGate(['oc_selected'],now);gate.replaceChats(['oc_new']);
 const old=fixture();Object.defineProperty(old.message,'content',{get(){throw new Error('not authorized')}});assert.equal(gate.accept(old,now+2),null);
 const added=fixture();added.message.chat_id='oc_new';assert.ok(gate.accept(added,now+2));
 gate.replaceChats([]);const removed=fixture();removed.message.chat_id='oc_new';Object.defineProperty(removed.message,'content',{get(){throw new Error('not authorized')}});assert.equal(gate.accept(removed,now+3),null);
 assert.throws(()=>gate.replaceChats(['invalid']));
});
