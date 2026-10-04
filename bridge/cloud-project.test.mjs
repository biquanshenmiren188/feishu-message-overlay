import test from 'node:test';import assert from 'node:assert/strict';
import {BotGate} from './filter.mjs';import {digest,projectEvent} from './cloud-project.mjs';
const now=Date.now();
const event=(type,content,id='m1')=>({sender:{sender_type:'bot',sender_id:{open_id:'ou_fixture'}},message:{message_id:id,chat_id:'oc_fixture',chat_type:'group',create_time:String(now),message_type:type,content:JSON.stringify(content)}});
test('joined bot filtering and duplicate suppression precede projection',()=>{
 const gate=new BotGate(['oc_fixture'],now-1);const msg=event('text',{text:'Synthetic'});
 assert.equal(gate.accept({...msg,sender:{sender_type:'user'}}),null);
 assert.equal(gate.accept({...msg,message:{...msg.message,chat_id:'oc_other'}}),null);
 const accepted=gate.accept(msg);assert.ok(accepted);assert.equal(gate.accept(msg),null);
 const projected=projectEvent(accepted);assert.equal(projected.body,'Synthetic');assert.equal(projected.groupId,digest('oc_fixture'));assert.equal(projected.id,digest('oc_fixture\nm1'));
 gate.replaceChats([]);assert.equal(gate.accept(event('text',{text:'after leave'},'m2')),null);
});
test('native card DSL preserves title, text and safe buttons',()=>{
 const card={header:{title:{content:'Fixture title'}},elements:[{tag:'markdown',content:'First\nSecond'},{tag:'button',text:{content:'Open'},multi_url:{pc_url:'https://example.invalid/a?x=1&y=2'}},{tag:'button',text:{content:'Unsafe'},url:'javascript:alert(1)'}]};
 const gate=new BotGate(['oc_fixture'],now-1);const p=projectEvent(gate.accept(event('interactive',{user_dsl:JSON.stringify(card)})));
 assert.equal(p.title,'Fixture title');assert.match(p.body,/First\nSecond/);assert.equal(p.actions.length,1);assert.equal(p.actions[0].url,'https://example.invalid/a?x=1&y=2');assert.match(p.body,/unavailable/);
});
test('projection is bounded and source timestamps remain unchanged',()=>{
 const gate=new BotGate(['oc_fixture'],now-1);const p=projectEvent(gate.accept(event('interactive',{elements:[{tag:'markdown',content:'x'.repeat(20000)}]})));
 assert.ok(p.body.length<=16000);assert.equal(p.sentAt,new Date(now).toISOString());
});

test('header template survives native DSL and unknown colors remain safe',()=>{for(const tone of ['blue','red','not-a-style']){const gate=new BotGate(['oc_fixture'],now-1);const card={header:{template:tone,title:{content:'Synthetic'}},elements:[{tag:'markdown',content:'Body'}]};const p=projectEvent(gate.accept(event('interactive',{user_dsl:JSON.stringify(card)},tone)));assert.equal(p.headerTone,tone==='not-a-style'?'grey':tone);}});
