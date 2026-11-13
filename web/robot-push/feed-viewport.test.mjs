import test from 'node:test';
import assert from 'node:assert/strict';
import {ordinaryViewportHeight} from './feed-viewport.js';
test('short histories keep usable space',()=>assert.equal(ordinaryViewportHeight([]),400));
test('six natural-height rows fit at every reading position',()=>{
 let y=0;const rows=[40,60,100,180,60,70,50,90,30].map(h=>{const r={top:y,bottom:y+h};y+=h;return r;});
 const height=ordinaryViewportHeight(rows,4);
 for(let i=0;i<=rows.length-6;i++)assert.ok(height>=rows[i+5].bottom-rows[i].top+4);
 assert.equal(height,556);
});
