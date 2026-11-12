import test from 'node:test';
import assert from 'node:assert/strict';
import {historyRows,historySignals,visiblePins} from './pin-history.js';
const row=(id,n)=>({id,title:'强信号聚集 | TOKEN | 2组',body:'原文',sentAt:`2026-11-12T03:00:0${n}Z`,actions:[]});
test('history newest first, current distinct, dedup, source untouched',()=>{
 const first=row('a',1),next=row('b',2),source={messages:[first,next,first],currentId:'b'};
 const before=JSON.stringify(source),rows=historyRows(source);
 assert.deepEqual(rows.map(r=>[r.id,r.current]),[['b',true],['a',false]]);assert.equal(JSON.stringify(source),before);
});
test('bad history and unsafe links cannot become rendered actions',()=>{
 assert.throws(()=>historyRows({messages:Array.from({length:6},(_,n)=>row(String(n),n))}));
 assert.throws(()=>historyRows({messages:[{...row('a',1),sentAt:'invalid'}]}));
 const m={...row('a',1),actions:[{label:'bad',url:'javascript:alert(1)'},{label:'safe',url:'https://example.com/'}]};
 assert.deepEqual(historyRows({messages:[m]})[0].actions,[{label:'safe',url:'https://example.com/'}]);
});

test('history keeps each mixed-window value without borrowing next group',()=>{
 assert.equal(historySignals({body:'R1 | FF | 买 BITGET → 卖 ASTER\nV2收敛 · 60秒 · 净均 +0.23% · ACTIVE 1s\nR0 | SF | 买 GATE → 卖 ASTER\n未知\nR1 | FF | 买 GATE → 卖 OKX\nV2收敛 · 180秒 · 净均 +0.49%'}),'R1｜FF｜BG→AS｜+0.23%\nR0｜SF｜GT→AS\nR1｜FF｜GT→OK｜+0.49%');
});

test('blocked latest does not erase five eligible older pins; latest below',()=>{
 const rows=Array.from({length:5},(_,i)=>row(String(i),i));
 assert.deepEqual(visiblePins(null,rows).map(m=>m.id),['0','1','2','3','4']);
 assert.deepEqual(visiblePins(row('new',6),rows).map(m=>m.id),['1','2','3','4','new']);
 assert.equal(visiblePins(null,[]).length,0);
});
