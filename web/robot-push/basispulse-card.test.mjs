import {test} from 'node:test';
import assert from 'node:assert/strict';
import {radarMatrix,transferCoin,createRadarTransfers} from './basispulse-transfers.js';
import {strategyCopy,periodWarning,fundingWarnings,residualTone} from './basispulse-card-model.js';
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

test('source residual color boundaries preserve all five tiers',()=>{
 for(const [level,tone] of [[null,'grey'],[NaN,'grey'],[0,'grey'],[1,'grey'],[2,'blue'],[3,'blue'],[4,'yellow'],[5,'yellow'],[6,'orange'],[9,'orange'],[10,'red'],[81,'red']])assert.equal(residualTone(level),tone);
});

test('TON full name and ticker merge into a single chain column',()=>{
 const m=matrix([data([{chain:'The Open Network (TON)',deposit:'可用',withdraw:'可用'},{chain:'TON',deposit:'可用',withdraw:'可用'}])]);
 assert.deepEqual(m.chains,['TON']);assert.deepEqual(m.rows[0].cells,[['open','open']]);
 const conflict=matrix([data([{chain:'The Open Network (TON)',deposit:'可用',withdraw:'可用'},{chain:'TON',deposit:'暂停',withdraw:'可用'}])]);
 assert.deepEqual(conflict.rows[0].cells,[['unknown','open']]);
});

test('news summaries preserve postponed and uncertain notices alongside funding warnings',()=>{
 const news=[{exchange:'okx',summary:'ONE永续合约下架',status:'postponed'},{exchange:'gate',summary:'维护',status:'uncertain'},null,{}];
 const result=fundingWarnings([{exchange:'bybit',spot:false,hours:1}],news);
 assert.deepEqual(result,['OKX ONE永续合约下架（已延期，时间未定）','GATE 维护（待确认）','Bybit 1h 计算不同']);
});

test('Base display case does not split one network into two columns',()=>{
 const m=matrix([data([{chain:'Base',deposit:'可用',withdraw:'可用'},{chain:'BASE',deposit:'可用',withdraw:'可用'}])]);
 assert.deepEqual(m.chains,['BASE']);assert.deepEqual(m.rows[0].cells,[['open','open']]);
});

test('no spot requires current matching explicit catalog evidence, not missing data',()=>{
 const w={key:'binance:ABC',text:'Binance【无数据｜无现货｜现货目录】：该平台无现货',checkedAt:new Date(now-1000).toISOString(),expiresAt:new Date(now+10000).toISOString(),refreshFailed:false};
 const build=(wallets,items=[])=>radarMatrix(legs,()=>({items}),now,wallets).rows[1];
 assert.equal(build([w]).noSpot,true);assert.deepEqual(build([w]).cells,[['none','none']]);
 for(const patch of [{key:'binance:OTHER'},{refreshFailed:true},{expiresAt:new Date(now-1).toISOString()},{text:'状态未知'},{checkedAt:new Date(now+60000).toISOString()}])assert.equal(build([{...w,...patch}]).noSpot,false);
 assert.equal(build([w],[data([{chain:'ETH',deposit:'可用',withdraw:'可用'}],{exchange:'binance'})]).noSpot,false);
});

test('fresh attributed source fills unknowns without overriding radar or hidden sides',()=>{
 const w={key:'gate:ABC',text:'Gate【官方｜12:00:00】：充开/提关 ETH；充支持/提支持 BSC',checkedAt:new Date(now-1000).toISOString(),expiresAt:new Date(now+10000).toISOString(),refreshFailed:false};
 const build=(wallet=w,items=[])=>radarMatrix(legs,()=>({items}),now,[wallet]);
 assert.deepEqual(build().rows[0].cells,[['open','closed'],['supported','supported']]);
 assert.deepEqual(build(w,[data([{chain:'ETH',deposit:'暂停',withdraw:'未知',withdrawHidden:true}])]).rows[0].cells[0],['closed','unknown']);
 for(const patch of [{key:'gate:OTHER'},{refreshFailed:true},{checkedAt:new Date(now-120001).toISOString()},{expiresAt:new Date(now-1).toISOString()},{text:'Gate【未知来源｜12:00】：充开/提开 ETH'}])assert.deepEqual(build({...w,...patch}).rows[0].cells,[['unknown','unknown']]);
 assert.deepEqual(build({...w,text:'Gate【官方｜12:00】：充开/提开 ETH；充关/提开 ERC20'}).rows[0].cells,[['unknown','open']]);
});


test('retained expired Gate/OKX cards still produce compatible strategy codes',()=>{
 const d={strategy:'SF',validUntil:'2000-01-01T00:00:00Z',details:{legs:[{exchange:'gate',symbol:'UP_USDT',spot:true},{exchange:'okx',symbol:'UP-USDT-SWAP',spot:false}]}};
 assert.deepEqual(JSON.parse(strategyCopy(d).split('\n').slice(1).join('\n')),{type:'SF',name:'UP',buyEx:'gate',sellEx:'okx'});
 for(const symbol of ['1000UP-USDT-SWAP','UP-USD-SWAP','UP-USDT-261225'])assert.equal(strategyCopy({...d,details:{legs:[d.details.legs[0],{...d.details.legs[1],symbol}]}}),null);
});

test('Hyperliquid card strategies use Astro hl identifier and reject unsupported margin spot',()=>{
 for(const side of [0,1]){
  const legs=[{exchange:side===0?'hyperliquid':'binance',symbol:'HYPEUSDT',spot:false},{exchange:side===1?'hyperliquid':'binance',symbol:'HYPEUSDT',spot:false}];
  const parsed=JSON.parse(strategyCopy({strategy:'FF',details:{legs}}).split('\n').slice(1).join('\n'));
  assert.equal(parsed[side===0?'buyEx':'sellEx'],'hl');assert.equal(parsed.name,'HYPE');
 }
 assert.equal(strategyCopy({strategy:'FS',details:{legs:[{exchange:'binance',symbol:'HYPEUSDT',spot:false},{exchange:'hyperliquid',symbol:'HYPEUSDT',spot:true}]}}),null);
});
