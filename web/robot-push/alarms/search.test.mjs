import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesInstrument,matchesAlarm} from './search.js';

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
