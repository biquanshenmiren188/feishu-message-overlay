import test from 'node:test';
import assert from 'node:assert/strict';
import {fallbackChoices,FALLBACK_ORDER} from './fallback.js';
test('legacy auto/single/off preserve actual source permission across all main venues',()=>{
 for(const main of FALLBACK_ORDER){
  assert.deepEqual(fallbackChoices(null,main),FALLBACK_ORDER.filter(v=>v!==main&&v!=='aster'));
  assert.deepEqual(fallbackChoices({fallbackExchange:'off'},main),[]);
  for(const other of FALLBACK_ORDER)assert.deepEqual(fallbackChoices({fallbackExchange:other},main),other===main?[]:[other]);
 }
});
test('explicit empty and subsets never expand to automatic sources',()=>{
 for(const main of FALLBACK_ORDER){
  assert.deepEqual(fallbackChoices({fallbackExchange:'auto',fallbackExchanges:[]},main),[]);
  assert.deepEqual(fallbackChoices({fallbackExchange:'auto',fallbackExchanges:['aster','okx']},main),['okx','aster'].filter(v=>v!==main));
 }
});
