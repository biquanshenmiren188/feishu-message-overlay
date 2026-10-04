import assert from 'node:assert/strict';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createEchoOnlyProcessor, isAllowedEcho } from './echo-only-guard.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
for(const name of Object.keys(process.env)) {
  if(/(?:OPENAI|ANTHROPIC|CLAUDE|CODEX|GEMINI|AZURE|AWS|API_KEY|AUTH_TOKEN)/i.test(name)) delete process.env[name];
}
process.env.OPENCLAW_HOME=path.join(root,'offline-empty-home');
process.env.OPENCLAW_STATE_DIR=path.join(root,'offline-empty-state');
process.env.OPENCLAW_CONFIG_PATH=path.join(root,'offline-no-config.json');
process.env.OPENCLAW_CONFIG=process.env.OPENCLAW_CONFIG_PATH;
process.env.OPENCLAW_LOG_LEVEL='FATAL';
const requests=[];
globalThis.fetch=async(url,options)=>{
  assert.equal(new URL(url).hostname,'mock.invalid');
  requests.push(JSON.parse(options.body));
  return new Response(JSON.stringify({ret:0,message_id:'fictional-reply'}),{status:200});
};
const {processOneMessage}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/process-message.upstream.js');
const {processOneMessage:guardedInstalledProcess}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/process-message.js');
const {WeixinConfigSchema}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/config/config-schema.js');
const schema=WeixinConfigSchema.parse({quoteCache:{enabled:false},replyProgressMessages:false});
assert.equal(schema.quoteCache.enabled,false);
const input={from_user_id:'fictional-owner',context_token:'fictional-not-auth',create_time_ms:Date.now(),item_list:[{type:1,text_item:{text:'/echo 测试123'}}]};
let unintendedCalls=0;
const forbidden=()=>{unintendedCalls++;throw new Error('Unexpected AI/media/runtime path');};
const runtime=new Proxy({}, {get:forbidden});
const deps={accountId:'offline-fiction',config:{channels:{'openclaw-weixin':schema}},channelRuntime:runtime,baseUrl:'https://mock.invalid',cdnBaseUrl:'https://mock.invalid',log:forbidden,errLog:forbidden};
const handler=createEchoOnlyProcessor(processOneMessage,'fictional-owner');
assert.equal((await handler(input,deps)).accepted,true);
assert.equal(requests.length,2);
assert.equal(requests[0].msg.item_list[0].text_item.text,'测试123');
for(const message of [
  {...input,from_user_id:'fictional-other'},
  {...input,item_list:[{type:1,text_item:{text:'ordinary private text'}}]},
  {...input,item_list:[{type:1,text_item:{text:'/toggle-debug'}}]},
  {...input,item_list:[{type:2,image_item:{media:{full_url:'https://mock.invalid/image'}}}]},
  {...input,item_list:[...input.item_list,{type:2}]},
  {...input,item_list:[{type:1,text_item:{text:'/echo 测试123'},ref_msg:{}}]},
])assert.equal((await handler(message,deps)).accepted,false);
assert.equal(isAllowedEcho(input,''),false);
assert.equal(requests.length,2);
assert.equal(unintendedCalls,0);
await guardedInstalledProcess(input,{...deps,accountId:'unbound-fictional-account'});
assert.equal(requests.length,2);
assert.equal(unintendedCalls,0);
assert.equal(fs.existsSync(process.env.OPENCLAW_STATE_DIR),false);
console.log(JSON.stringify({officialPlugin:'2.4.9',host:'2026.8.1',mockReplies:2,realNetworkRequests:0,aiOrMediaCalls:0,unknownAndMediaRejected:true,installedGuardFailsClosedWithoutBinding:true,quoteCacheDisabled:true,credentialFilesCreated:0,liveBindingValidated:false}));
