import test from 'node:test';import assert from 'node:assert/strict';import {oiPresentation} from './card-oi.js';
const now=1793000000000,ctx={bound:true,fresh:true,now,exchange:'aster',spot:false,raw:'371.60k'};
const proof={exchange:'aster',market:'perp',threshold:50,checkedAt:now,time:now-1000,expiresAt:now+299000,basis:'double-v1',status:'ok',value:871898};
test('display uses exact decision value rather than source reference or guessed double',()=>{const view=oiPresentation(proof,ctx);assert.equal(view.value,'871.90k');assert.match(view.title,/50 万 USDT/);assert.match(view.title,/双边/);});
test('stale, denied, wrong venue and missing values never fall back under a threshold',()=>{for(const [p,c]of [[proof,{...ctx,fresh:false}],[{...proof,expiresAt:now-1},ctx],[{...proof,checkedAt:now-10000},ctx],[{...proof,exchange:'gate'},ctx],[{...proof,status:'missing'},ctx],[undefined,ctx]])assert.equal(oiPresentation(p,c).value,'—');});
test('unbound or no-threshold reference is explicitly labelled',()=>{assert.equal(oiPresentation(null,{...ctx,bound:false}).label,'源 OI');assert.equal(oiPresentation({...proof,status:'not-filtered',threshold:null},ctx).value,'371.60k');});
