import {test}from 'node:test';import assert from 'node:assert/strict';import {auditCard}from './card-shape-audit.mjs';
test('recursive audit covers unknown containers, encoded JSON and markdown without values',()=>{
 const secret='private-secret-NEVER';const target='https://example.com/?private=NEVER';
 const value={unknown_box:{columns:[{tag:'button',text:{content:secret},behaviors:[{type:'open_url',url:target}]}]},encoded:JSON.stringify({markdown:'[private](https://example.com/x)',x:secret}),token:secret};
 const a=auditCard(JSON.stringify(value));assert.equal(a.buttonTargets,1);assert.equal(a.encodedJson,1);assert.equal(a.httpStrings,1);assert.equal(a.buttons,1);assert.equal(a.complete,true);
 const text=JSON.stringify(a);for(const v of[secret,target,'example.com','NEVER'])assert.equal(text.includes(v),false);
});
test('button label alone is distinguished from an unrelated body URL',()=>{const a=auditCard(JSON.stringify({elements:[{tag:'button',text:'Label'},{tag:'markdown',content:'https://example.com/body'}]}));assert.equal(a.buttons,1);assert.equal(a.buttonLabels,1);assert.equal(a.buttonTargets,0);assert.equal(a.httpStrings,1);});
