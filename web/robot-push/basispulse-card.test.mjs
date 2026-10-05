import {test} from 'node:test';
import assert from 'node:assert/strict';
import {radarMatrix,transferCoin,createRadarTransfers} from './basispulse-transfers.js';
import {strategyCopy,periodWarning,fundingWarnings} from './basispulse-card-model.js';
const now=1791162796000;
test('period warning excludes spot, missing and equal periods',()=>{
 assert.equal(periodWarning([{spot:false,hours:4},{spot:false,hours:1}]),'周期 4h/1h');
 for(const legs of [[{spot:false,hours:4},{spot:false,hours:4}],[{spot:true,hours:4},{spot:false,hours:1}],[{spot:false,hours:null},{spot:false,hours:1}]])assert.equal(periodWarning(legs),null);
});
const legs=[{exchange:'gate',symbol:'ABC_USDT',spot:true},{exchange:'binance',symbol:'ABCUSDT',spot:false}];
const data=(chains,extra={})=>({coin:'ABC',exchange:'gate',checkedAt:now,chains,...extra});
const matrix=(items,t=now)=>radarMatrix(legs,()=>({items}),t);
test('exact symbols are used; no inferred 1000 unit stripping',()=>{assert.equal(transferCoin(legs[0]),'ABC');assert.equal(transferCoin({symbol:'1000RATSUSDT'}),'1000RATS');assert.equal(transferCoin({symbol:'USDTC'}),null);});
test('radar chain states distinguish open closed and merely supported',()=>{const m=matrix([data([{chain:'ETH',deposit:'可用',withdraw:'暂停'},{chain:'BSC',deposit:'支持',withdraw:'延迟'}])]);assert.deepEqual(m.chains,['ETH','BNB']);assert.deepEqual(m.rows[0].cells,[['open','closed'],['supported','delayed']]);assert.deepEqual(m.rows[1].cells,[['unknown','unknown'],['unknown','unknown']]);});
test('stale evidence and hidden sides do not show as open',()=>{const c={chain:'ETH',deposit:'可用',withdraw:'可用',depositEvidence:{at:now-120001},withdrawHidden:true};assert.deepEqual(matrix([data([c])]).rows[0].cells,[['unknown','unknown']]);assert.deepEqual(matrix([data([{chain:'ETH',deposit:'可用',withdraw:'可用'}])],now+120001).rows[0].cells,[['unknown','unknown']]);});
test('wrong coin or exchange cannot fill a card',()=>{assert.deepEqual(matrix([data([{chain:'ETH',deposit:'可用',withdraw:'可用'}],{coin:'OTHER'})]).rows[0].cells,[['unknown','unknown']]);});
test('chain alias conflicts are unknown; no-chain does not imply no spot',()=>{const m=matrix([data([{chain:'ERC20',deposit:'可用',withdraw:'可用'},{chain:'ETH',deposit:'暂停',withdraw:'可用'}])]);assert.deepEqual(m.rows[0].cells,[['unknown','open']]);assert.equal(m.rows[1].noSpot,false);});
test('copy preserves verified strategy protocol and refuses mismatched units',()=>{const d={strategy:'SF',details:{legs}};assert.deepEqual(JSON.parse(strategyCopy(d).split('\n').slice(1).join('\n')),{type:'SF',name:'ABC',buyEx:'gate',sellEx:'binance'});assert.equal(strategyCopy({...d,details:{legs:[legs[0],{...legs[1],symbol:'1000ABCUSDT'}]}}),null);assert.equal(strategyCopy({strategy:'FS',details:{legs:[legs[1],{...legs[0],exchange:'aster'}]}}),null);});
test('same coin requests coalesce, refresh at five seconds and retry failures',async()=>{
  globalThis.document={hidden:false};let t=now,calls=0,fail=false;
  const cache=createRadarTransfers(()=>{},async()=>{calls++;if(fail)throw Error('offline');return {ok:true,json:async()=>({coin:'ABC',items:[data([])],pending:[]})}},()=>t);
  await cache.refresh([...legs,...legs]);assert.equal(calls,1);await cache.refresh(legs);assert.equal(calls,1);
  t+=5000;fail=true;await cache.refresh(legs);assert.equal(calls,2);assert.equal(cache.get('ABC').items.length,1);
  t+=4999;await cache.refresh(legs);assert.equal(calls,2);t++;fail=false;await cache.refresh(legs);assert.equal(calls,3);
  delete globalThis.document;
});

test('Bybit hourly warning independent of period mismatch and excludes spot',()=>{
 assert.deepEqual(fundingWarnings([{exchange:'binance',spot:false,hours:1},{exchange:'bybit',spot:false,hours:1}]),['Bybit 1h 计算不同']);
 assert.deepEqual(fundingWarnings([{exchange:'gate',spot:false,hours:4},{exchange:'bybit',spot:false,hours:1}]),['周期 4h/1h','Bybit 1h 计算不同']);
 assert.deepEqual(fundingWarnings([{exchange:'bybit',spot:true,hours:1}]),[]);
});
