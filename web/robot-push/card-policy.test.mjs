import test from 'node:test';
import assert from 'node:assert/strict';
import {CardPolicyState} from './card-policy.js';
const card={id:'span-2',pair:'PTB:BN>GT'},data={revision:2,cardsEnabled:true,decisions:{'PTB:BN>GT':'hide','IRYS:GT>AS':'allow'}};
test('guest is explicit public mode; connected owner waits for first check',()=>{const p=new CardPolicyState();assert.equal(p.outcome(card,1),'public');p.reset('owner');assert.equal(p.visible(card,1),false);});
test('shared pair identity blocks new spans, unknown cards wait, allowed cards show',()=>{const p=new CardPolicyState();p.reset('owner');p.accept(data,100);assert.equal(p.visible(card,101),false);assert.equal(p.visible({pair:'IRYS:GT>AS'},101),true);assert.equal(p.outcome({id:'unseen'},101),'pending');});
test('unblock reappears without reloading; disabling reception hides all',()=>{const p=new CardPolicyState();p.reset('owner');p.accept(data,100);p.accept({...data,revision:3,decisions:{[card.pair]:'allow'}},200);assert.equal(p.visible(card,201),true);p.accept({...data,cardsEnabled:false},300);assert.equal(p.visible({pair:'IRYS:GT>AS'},301),false);});
test('expired decisions and scheme changes never reuse allowed cards',()=>{const p=new CardPolicyState();p.reset('owner');p.accept(data,100);assert.equal(p.visible({pair:'IRYS:GT>AS'},10099),true);assert.equal(p.visible({pair:'IRYS:GT>AS'},10100),false);p.reset('other');assert.equal(p.data,null);assert.equal(p.visible(card,200),false);});
test('reject malformed response and unsupported mute action for cards',()=>{const p=new CardPolicyState();for(const d of [null,{}, {...data,decisions:[]},{...data,decisions:{[card.pair]:'mute'}}])assert.throws(()=>p.accept(d,100));});
