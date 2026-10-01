import {test} from 'node:test';import assert from 'node:assert/strict';
import {buttonTarget,projectCard,CardDetails} from './card-content.mjs';
const url='https://example.com/radar?first=1&encoded=%E4%B8%AD%E6%96%87&last=2';
const card=node=>JSON.stringify({title:'Synthetic',elements:[[{tag:'button',text:'Open',...node}]]});
test('official URL variants preserve complete query and never use callback value',()=>{
 for(const node of [{url},{href:url},{url:{url}},{multi_url:{pc_url:url}},{open_url:{url}},{behaviors:[{type:'open_url',default_url:url}]}])assert.equal(buttonTarget(node),url);
 assert.equal(buttonTarget({value:{url},behaviors:[{type:'callback',default_url:url}]}),'');assert.equal(buttonTarget({url:'javascript:alert(1)'}),'');
});
test('shape projection contains no label, address, body, arbitrary key or callback value',()=>{
 const result=projectCard(card({behaviors:[{type:'callback',value:'private-only'}]}));const text=JSON.stringify(result.meta);
 assert.equal(result.meta.callback,true);assert.deepEqual(result.meta.shapes,['behaviors:array']);for(const value of ['private-only','Synthetic','Open',url])assert.equal(text.includes(value),false);
});
const event=()=>({event:{message:{message_id:'om_fixture',chat_id:'oc_fixture',content:card({})}}});
test('exact message detail restores target without rewriting or trading',async()=>{
 const resolver=new CardDetails(async()=>({code:0,data:{items:[{message_id:'om_fixture',chat_id:'oc_fixture',msg_type:'interactive',sender:{sender_type:'app'},body:{content:card({url})}}]}}));
 const item=event(),meta=await resolver.resolve(item);assert.equal(meta.detail,'enriched');assert.equal(meta.targets,1);assert.equal(JSON.parse(item.event.message.content).elements[0][0].url,url);
});
test('permission rejection stops further detail attempts, retains event and never adds scopes',async()=>{
 let calls=0;const resolver=new CardDetails(async()=>{calls++;return {code:99991672,msg:'private scopes [im:message, im:message:readonly]'};});
 const item=event();const meta=await resolver.resolve(item);assert.equal(meta.detail,'api_rejected');assert.equal(meta.code,99991672);assert.deepEqual(meta.requiredScopes,['im:message','im:message:readonly']);await resolver.resolve(event());assert.equal(calls,1);assert.equal(JSON.stringify(meta).includes('private'),false);
});
test('original URL field types survive normalization without saving values',()=>{const result=projectCard(card({url:{url}}));assert.deepEqual(result.meta.shapes,['url:object']);assert.equal(result.meta.targets,1);assert.equal(JSON.stringify(result.meta).includes(url),false);});
test('natural event user_dsl restores original header and action button without querying downgraded detail',async()=>{
 const native={header:{template:'blue',title:{tag:'plain_text',content:'Synthetic'}},elements:[{tag:'action',actions:[{tag:'button',text:{content:'Open'},behaviors:[{type:'open_url',default_url:url}]}]}]};
 const e=event();e.event.message.content=JSON.stringify({title:'Synthetic',elements:[[{tag:'button',text:'Open'}]],user_dsl:JSON.stringify(native)});
 let calls=0;const meta=await new CardDetails(async()=>{calls++;throw new Error();}).resolve(e);
 assert.equal(meta.targets,1);assert.equal(meta.header,true);assert.equal(meta.detail,'not_needed');assert.equal(calls,0);assert.equal(JSON.parse(e.event.message.content).elements[0].actions[0].url,url);
});
test('invalid encoded DSL retains simplified content and callbacks remain non-navigation',()=>{
 const a=projectCard(JSON.stringify({title:'Synthetic',elements:[[{tag:'button',text:'Open'}]],user_dsl:'not-json'}));assert.equal(a.meta.buttons,1);assert.equal(a.meta.targets,0);
 const b=projectCard(JSON.stringify({user_dsl:JSON.stringify({elements:[{tag:'button',text:'Open',value:{url}}]})}));assert.equal(b.meta.targets,0);
});
test('missing-target details suppressed per source but do not disable another bot',async()=>{
 let calls=0;const resolver=new CardDetails(async()=>{calls++;return {code:0,data:{items:[{message_id:'om_fixture',chat_id:'oc_fixture',msg_type:'interactive',sender:{sender_type:'app'},body:{content:card({})}}]}};});
 const first=event();first.event.sender={sender_id:{open_id:'bot-a'}};await resolver.resolve(first);await resolver.resolve(first);const second=event();second.event.sender={sender_id:{open_id:'bot-b'}};await resolver.resolve(second);assert.equal(calls,2);
});
test('downgraded details and wrong identity never associate body link with button',async()=>{
 for(const item of [{message_id:'om_other',chat_id:'oc_fixture'},{message_id:'om_fixture',chat_id:'oc_fixture',msg_type:'interactive',sender:{sender_type:'app'},body:{content:card({})}}]){
 const resolver=new CardDetails(async()=>({code:0,data:{items:[item]}}));assert.notEqual((await resolver.resolve(event())).detail,'enriched');}
});
