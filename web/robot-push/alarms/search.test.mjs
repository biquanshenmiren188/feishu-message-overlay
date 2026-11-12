import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesInstrument,matchesAlarm,instrumentLabel,resolveInstrument} from './search.js';

test('coin catalog matches complete base or exchange symbol, never a substring',()=>{
 const rows=['BTC','WBTC','BTCB','BT','1000BTC','ETH'].map(base=>({base,symbol:base+'USDT'}));
 for(const query of ['BTC',' btc ','btcusdt'])assert.deepEqual(rows.filter(r=>matchesInstrument(query,r)).map(r=>r.base),['BTC']);
 assert.deepEqual(rows.filter(r=>matchesInstrument('B',r)),[]);
 assert.equal(rows.filter(r=>matchesInstrument('',r)).length,rows.length);
 assert.equal(matchesInstrument('RATS',{base:'1000RATS',symbol:'1000RATSUSDT'}),false);
 assert.equal(matchesInstrument('1000RATS',{base:'1000RATS',symbol:'1000RATSUSDT'}),true);
 assert.equal(matchesInstrument('BTC-USDT-SWAP',{base:'BTC',symbol:'BTC-USDT-SWAP'}),true);
 assert.equal(matchesInstrument('BTC_USDT',{base:'BTC',symbol:'BTC_USDT'}),true);
});

test('saved alarms match exact coin, full symbol, venue or complete note',()=>{
 for(const symbol of ['BTCUSDT','BTC_USDT','BTC-USDT','BTC-USDT-SWAP']){
  const r={symbol,note:'突破观察',exchange:'binance'};
  for(const q of ['btc',symbol,'突破观察','BINANCE'])assert.equal(matchesAlarm(q,r),true);
  for(const q of ['BT','突破','bin','USDT'])assert.equal(matchesAlarm(q,r),false);
 }
 for(const symbol of ['WBTCUSDT','1000BTCUSDT','BTCBUSDT'])assert.equal(matchesAlarm('BTC',{symbol}),false);
 assert.equal(matchesAlarm('RATS',{symbol:'1000RATSUSDT'}),false);
});

test('canonical display pair can be searched without aliasing wrapped or scaled coins',()=>{
 const r={symbol:'BTC-USDT-SWAP',state:{asset:{base:'BTC',pair:'BTC/USDT'}}};
 for(const q of ['BTC','btc/usdt','BTC-USDT-SWAP'])assert.equal(matchesAlarm(q,r),true);
 for(const q of ['WBTC','1000BTC','BTC/USD'])assert.equal(matchesAlarm(q,r),false);
});

test('picker displays one canonical pair but resolves the exact native symbol for each venue',()=>{
 for(const symbol of ['BTCUSDT','BTC-USDT-SWAP','BTC_USDT']){
  const item={symbol,base:'BTC',quote:'USDT'};
  assert.equal(instrumentLabel(item),'BTC/USDT');
  for(const query of ['BTC','btc/usdt',symbol])assert.equal(resolveInstrument(query,[item]).symbol,symbol);
 }
 const items=['BTC','WBTC','1000BTC','ETH'].map(base=>({symbol:base+'USDT',base,quote:'USDT'}));
 assert.equal(resolveInstrument('BTC/USDT',items).base,'BTC');
 assert.equal(resolveInstrument('ETH/USDT',items).base,'ETH');
 assert.equal(resolveInstrument('BT',items),null);
 assert.equal(resolveInstrument('BTC/USD',items),null);
 assert.equal(resolveInstrument('BTC/USDT',items.slice(1)),null);
});

test('ambiguous display identities do not silently save the first native instrument',()=>{
 const items=['BTC-USDT-SWAP','BTC-USDT-OTHER'].map(symbol=>({symbol,base:'BTC',quote:'USDT'}));
 assert.equal(resolveInstrument('BTC/USDT',items),null);
 assert.equal(resolveInstrument('BTC',items),null);
 assert.equal(resolveInstrument('',items),null);
 assert.equal(resolveInstrument('BTC-USDT-SWAP',items).symbol,'BTC-USDT-SWAP');
});
