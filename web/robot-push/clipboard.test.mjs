import {test} from 'node:test';
import assert from 'node:assert/strict';
import {clipboardText,copyText} from './clipboard.js';
import {strategyCopy,gcStrategyCopy} from './basispulse-card-model.js';

test('both buttons copy importer JSON without a URI prefix, preserving direction and GC codes',()=>{
 const data={strategy:'FF',details:{legs:[{exchange:'binance',symbol:'SIRENUSDT',spot:false},{exchange:'bybit',symbol:'SIRENUSDT',spot:false}]}};
 for(const [builder,buyEx,sellEx] of [[strategyCopy,'binance','bybit'],[gcStrategyCopy,'gc-binance','gc-bybit']]){
  const text=clipboardText(builder(data));assert.ok(text.startsWith('{'));
  assert.deepEqual(JSON.parse(text),{type:'FF',name:'SIREN',buyEx,sellEx});
 }
});
test('Unicode, contract multipliers, FS borrowing fields and summaries are lossless',()=>{
 const payload={type:'FS',name:'1000测试币',buyEx:'gc-okx',sellEx:'gate',spotMarginType:'cross'};
 assert.deepEqual(JSON.parse(clipboardText('ASTRO-QUICK-COPY:\n'+JSON.stringify(payload))),payload);
 const summary='卡片文字\n买入 → 卖出\nhttps://example.test/radar';assert.equal(clipboardText(summary),summary);
 assert.throws(()=>clipboardText('ASTRO-QUICK-COPY:invalid'));
});

function env(writeText,{success=true,selects=true,modal=false}={}){
 const oldNavigator=Object.getOwnPropertyDescriptor(globalThis,'navigator'),oldDocument=globalThis.document;
 const state={removed:false,restored:false,listeners:new Map(),formats:new Map([['text/html','old html'],['text/uri-list','old uri']])};
 const host={append(field){state.field=field;state.host=modal?'dialog':'body';}};
 const previous={closest(selector){assert.ok(selector.includes('dialog[open]'));return modal?host:null},focus(){state.restored=true;doc.activeElement=previous}};
 const doc={activeElement:previous,body:host,createElement(tag){assert.equal(tag,'textarea');return {style:{},value:'',readOnly:false,focus(){doc.activeElement=this},select(){},setSelectionRange(a,b){this.selectionStart=selects?a:1;this.selectionEnd=b},remove(){state.removed=true}}},
  addEventListener(name,fn){state.listeners.set(name,fn)},removeEventListener(name,fn){assert.equal(state.listeners.get(name),fn);state.listeners.delete(name)},
  execCommand(command){assert.equal(command,'copy');state.listeners.get('copy')({clipboardData:{clearData(){state.formats.clear()},setData(type,value){state.formats.set(type,value)}},preventDefault(){state.prevented=true}});return success;}};
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:writeText?{writeText}:undefined}});globalThis.document=doc;
 return {state,restore(){if(oldNavigator)Object.defineProperty(globalThis,'navigator',oldNavigator);else delete globalThis.navigator;if(oldDocument===undefined)delete globalThis.document;else globalThis.document=oldDocument}};
}
test('native write starts synchronously in the click gesture and gets only plain JSON',async()=>{
 let written;const e=env(text=>{written=text;return Promise.resolve()});
 try{const pending=copyText('ASTRO-QUICK-COPY:\n{"name":"币"}');assert.equal(written,'{\n  "name": "币"\n}');assert.equal(await pending,true);assert.equal(e.state.field,undefined)}finally{e.restore()}
});
test('denied native API falls back within active dialog, clears rich formats and restores focus',async()=>{
 const e=env(async()=>{throw Error('denied')},{modal:true});
 try{assert.equal(await copyText('ASTRO-QUICK-COPY:{"name":"SIREN"}'),true);assert.equal(e.state.host,'dialog');assert.deepEqual([...e.state.formats.keys()],['text/plain']);assert.deepEqual(JSON.parse(e.state.formats.get('text/plain')),{name:'SIREN'});assert.ok(e.state.removed&&e.state.restored&&e.state.prevented);assert.equal(e.state.listeners.size,0)}finally{e.restore()}
});
test('missing API also falls back, preserving ordinary card text',async()=>{
 const e=env(null);try{assert.equal(await copyText('卡片\n正文'),true);assert.equal(e.state.formats.get('text/plain'),'卡片\n正文')}finally{e.restore()}
});
test('failed copy or incomplete selection never reports success and cleans up',async()=>{
 for(const opts of [{success:false},{selects:false}]){const e=env(null,opts);try{await assert.rejects(copyText('content'),/复制失败/);assert.ok(e.state.removed&&e.state.restored);assert.equal(e.state.listeners.size,0)}finally{e.restore()}}
});
test('an older rejected write cannot replace the most recently clicked code through fallback',async()=>{
 let rejectFirst,calls=0;const e=env(()=>++calls===1?new Promise((_,reject)=>rejectFirst=reject):Promise.resolve());
 try{const first=copyText('old');assert.equal(await copyText('new'),true);rejectFirst(Error('superseded'));assert.equal(await first,false);assert.equal(e.state.field,undefined)}finally{e.restore()}
});
