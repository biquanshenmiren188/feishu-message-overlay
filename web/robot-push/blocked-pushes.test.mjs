import test from 'node:test';
import assert from 'node:assert/strict';
import {blockedRecords,webpageRecords} from './blocked-pushes.js';

const row=(id='one')=>({id,title:'UNITREE | FF',body:'source body',sentAt:'2026-10-28T12:00:00Z'});
test('web viewer uses only ready bound hidden snapshots and copies safe fields',()=>{
 for(const value of [null,{}, {bound:false,ready:true,blocked:[row()]},{bound:true,ready:false,blocked:[row()]}])assert.equal(webpageRecords(value),null);
 const source={...row(),token:'not copied',action:'hide'},result=webpageRecords({bound:true,ready:true,blocked:[source,source,row('two'),{...row('invalid'),sentAt:'bad'}]});
 assert.equal(result.length,2);assert.deepEqual(Object.keys(result[0]).sort(),['body','id','sentAt','title']);source.body='changed';assert.equal(result[0].body,'source body');
 assert.deepEqual(webpageRecords({bound:true,ready:true,blocked:[]}),[]);
});
test('historical desktop records exclude cards and mute without changing mobile history',()=>{
 const rows=[{id:'one',channel:'desktop',action:'hide',at:2,reasons:['blocked']},{id:'two',channel:'desktop',action:'mute',at:3,reasons:['muted']},{id:'three',channel:'cards',action:'hide',at:4,reasons:['cards']}];
 assert.deepEqual(blockedRecords({history:rows},'desktop').map(r=>r.id),['one']);
 assert.deepEqual(blockedRecords({blockedHistory:[rows[0],rows[0]]},'mobile').map(r=>r.id),['one']);
});
