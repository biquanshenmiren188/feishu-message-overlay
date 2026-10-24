import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Opportunities, percent, money, safeRadar} from './basispulse-model.js';
const now=Date.parse('2026-10-04T10:00:00Z');
const iso=n=>new Date(n).toISOString();
const card=(id='a',over={})=>({id,asset:'name:USDT:ABC',enteredAt:iso(now-60000),updatedAt:iso(now),validUntil:iso(now+100000),v2Residual:{level:1,bps:50},...over});
const envelope=(cards,stamp=now,complete=true)=>({snapshot:{sampledAt:iso(stamp),complete,active:cards}});
test('equal name and rank put longest active first, matching source duration descending',()=>{const m=new Opportunities();m.ingest(envelope([card('new',{enteredAt:iso(now-1000)}),card('old',{enteredAt:iso(now-600000)})]),now);assert.deepEqual(m.order,['old','new']);});
test('numbers retain units; unknown is not zero',()=>{assert.equal(percent(50),'+0.50%');assert.equal(percent(.001,.01),'+0.10%');assert.equal(percent(null),'—');assert.equal(money(0),'0.00');assert.equal(money(null),'—');});
test('updates replace same ID without duplicate; older snapshots ignored',()=>{const m=new Opportunities();m.ingest(envelope([card()]),now);m.ingest(envelope([card('a',{rawBps:85})],now+1),now+1);assert.equal(m.cards.size,1);m.ingest(envelope([],now),now+2);assert.equal(m.cards.get('a').data.rawBps,85);});
test('complete empty snapshot expires then removes at exactly 30 seconds',()=>{const m=new Opportunities();m.ingest(envelope([card()]),now);m.ingest(envelope([],now+1000),now+1000);assert.equal(m.tick(now+30999).length,1);assert.equal(m.tick(now+31000).length,0);});
test('incomplete snapshots do not manufacture removals',()=>{const m=new Opportunities();m.ingest(envelope([card()]),now);m.ingest(envelope([],now+1,false),now+1);assert.equal(m.tick(now+2000)[0].expiredAt,now+100000);});
test('source validUntil still expires when polling stops',()=>{const m=new Opportunities();m.ingest(envelope([card('a',{validUntil:iso(now+5000)})]),now);assert.equal(m.tick(now+6000)[0].expiredAt,now+5000);assert.equal(m.tick(now+35000).length,0);});
test('active card can recover during grey retention',()=>{const m=new Opportunities();m.ingest(envelope([card()]),now);m.ingest(envelope([],now+1),now+1);m.ingest(envelope([card()],now+2),now+2);assert.equal(m.tick(now+3)[0].missingAt,null);});

test('fresh and delayed readers share the server retention deadline and active replacement wins',()=>{
 const shared=envelope([],now+1000);shared.snapshot.retained=[{card:card(),expiredAt:iso(now+1000)}];
 const early=new Opportunities(),late=new Opportunities();early.ingest(shared,now+1000);late.ingest(shared,now+29000);
 assert.equal(early.tick(now+30999).length,1);assert.equal(late.tick(now+30999).length,1);
 assert.equal(late.tick(now+31000).length,0);assert.equal(early.tick(now+31000).length,0);
 const recovered=envelope([card()],now+30000);recovered.snapshot.retained=shared.snapshot.retained;
 late.ingest(recovered,now+31001);assert.equal(late.tick(now+31001)[0].missingAt,null);
});

test('fallback absence uses source time, never restarts retention on delayed delivery',()=>{
 const m=new Opportunities();m.ingest(envelope([card()]),now);
 m.ingest(envelope([],now+1000),now+20000);
 assert.equal(m.tick(now+30999).length,1);assert.equal(m.tick(now+31000).length,0);
});
test('new cards append until next 15 second sort',()=>{const m=new Opportunities();m.ingest(envelope([card('z',{asset:'name:USDT:ZZZ'})]),now);m.ingest(envelope([card('z',{asset:'name:USDT:ZZZ'}),card('a')],now+1),now+1);assert.deepEqual(m.order,['z','a']);m.tick(now+15000);assert.deepEqual(m.order,['a','z']);});
test('R level must remain stable 15 seconds before reordering',()=>{const m=new Opportunities();m.ingest(envelope([card('a'),card('b',{v2Residual:{level:0}})]),now);m.ingest(envelope([card('a'),card('b',{v2Residual:{level:2}})],now+1000),now+1000);m.tick(now+15000);assert.deepEqual(m.order,['a','b']);m.tick(now+30000);assert.deepEqual(m.order,['b','a']);});
test('only verified radar host/path is linked',()=>{assert.equal(safeRadar('javascript:alert(1)'),null);assert.equal(safeRadar('https://evil.test/radar/'),null);assert.equal(safeRadar('https://u:p@leida.shenmiren.work/radar/'),null);assert.ok(safeRadar('https://leida.shenmiren.work/radar/?tab=FF'));});
test('re-entered market pair replaces earlier span instead of duplicate grey cards',()=>{const m=new Opportunities();m.ingest(envelope([card('old',{pair:'A>B'})]),now);m.ingest(envelope([],now+1),now+1);m.ingest(envelope([card('new',{pair:'A>B'})],now+2),now+2);assert.equal(m.tick(now+2).length,1);assert.equal(m.tick(now+2)[0].data.id,'new');});

test('snapshot expiry is pending, confirmed absence expires, reconnect does not imply active',async()=>{
 const {opportunityState}=await import('./basispulse-model.js');
 const c={expiredAt:now+5000,missingAt:null};
 assert.equal(opportunityState(c,true,now),'active');
 assert.equal(opportunityState(c,true,now+6000),'pending');
 assert.equal(opportunityState(c,false,now),'recovering');
 assert.equal(opportunityState({...c,missingAt:now},true,now),'expired');
 assert.equal(opportunityState({...c,expiredAt:now+10000},true,now+6000),'active');
});
