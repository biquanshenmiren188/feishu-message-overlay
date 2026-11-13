import test from 'node:test';
import assert from 'node:assert/strict';
import {createQuoteDisplay} from './quote-display.js';
const rule=(price,source='binance',extra={})=>({id:'r',exchange:'binance',market:'future',symbol:'BTCUSDT',priceType:'last',state:{price,source:{exchange:source,fallback:source!=='binance'}},...extra});
const live={fresh:true},offline={fresh:false};
test('price and selected source move together no more than once per five seconds',()=>{
 const d=createQuoteDisplay();d.read(rule('68000'),live,0);
 for(const t of [1000,2000,4000])assert.deepEqual(d.read(rule('67999','okx'),live,t),{value:'68000',source:{exchange:'binance',fallback:false},last:false});
 assert.deepEqual(d.read(rule('67999','okx'),live,5000),{value:'67999',source:{exchange:'okx',fallback:true},last:false});
});
test('outage retains explicitly marked last quote, never a zero or blank flash',()=>{
 const d=createQuoteDisplay();d.read(rule('68000'),live,0);
 assert.equal(d.read(rule(null),offline,2000).value,'68000');
 assert.equal(d.read(rule(null),offline,2000).last,true);
 assert.equal(d.read(rule('67000','okx'),live,6000).value,'67000');
 assert.equal(d.read(rule('67000','okx'),live,6000).last,false);
});
test('cold cache stays labelled last and disconnected empty state does not invent price',()=>{
 const d=createQuoteDisplay();assert.equal(d.read(rule(null),offline,0).value,null);
 assert.deepEqual(d.read(rule('68000'),offline,1000).last,true);
 assert.equal(d.read(rule('67000'),live,1100).value,'67000');
});
test('asset edit, removed rule, and profile changes discard old display values',()=>{
 const d=createQuoteDisplay();d.read(rule('68000'),live,0);
 assert.equal(d.read(rule('.0039','bybit',{symbol:'1000PEPEUSDT'}),live,100).value,'.0039');
 d.prune([]);assert.equal(d.read(rule('67000'),live,200).value,'67000');
 d.clear();assert.equal(d.read(rule('66000'),live,300).value,'66000');
});
test('display throttle preserves exact multiplier precision and never mutates server state',()=>{
 const d=createQuoteDisplay(),r=rule('0.0000039123456789');const before=JSON.stringify(r);
 assert.equal(d.read(r,live,0).value,'0.0000039123456789');
 assert.equal(JSON.stringify(r),before);
});
