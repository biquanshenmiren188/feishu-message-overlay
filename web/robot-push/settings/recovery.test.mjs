import test from 'node:test';
import assert from 'node:assert/strict';
import './rules.js';
const R=globalThis.RadarRules;
test('restore stages all filters cleared and preserves cadence/action without mutating original',()=>{const saved={...R.defaults(),enabled:false,rows:2,interval:300,desktopAction:'mute',coins:[{coin:'PTB',exchange:'all',enabled:true}],blockedExchanges:['bybit'],legRules:[{exchange:'okx',side:'right',market:'perp',enabled:true}],globalOI:500,exchangeOI:{gate:{mode:'custom',value:10}},coinOI:[{coin:'PTB',exchange:'gate',value:5,enabled:true}],rPercent:.5,ranks:['R0'],modes:['SF']};const before=JSON.stringify(saved),draft=R.resetFilters(saved);assert.equal(JSON.stringify(saved),before);assert.deepEqual(draft,{...R.defaults(),rows:2,interval:300,desktopAction:'mute'});draft.coins.push({coin:'ALT'});assert.equal(saved.coins[0].coin,'PTB');});
