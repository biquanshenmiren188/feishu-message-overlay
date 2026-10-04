import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import {timingSafeEqual} from 'node:crypto';
import {SendGate,safeSendError} from './send-gate.mjs';
const sendGate=new SendGate();
const root=process.env.OPENCLAW_HOME;
const config=JSON.parse(fs.readFileSync(path.join(root,'gateway.json'),'utf8'));
const apiToken=config.gateway.auth.token;
const preferenceFile=path.join(root,'forwarding.json');let preferences={enabled:false,echoVerified:false};
try{preferences={...preferences,...JSON.parse(fs.readFileSync(preferenceFile,'utf8'))};}catch{}
function savePreferences(){fs.writeFileSync(preferenceFile,JSON.stringify(preferences),{mode:0o600});}
const stats={bound:false,contextReady:false,echoReplies:0,echoVerified:preferences.echoVerified===true,forwarded:0,failed:0,enabled:preferences.enabled===true&&preferences.echoVerified===true,sendPaused:false};
globalThis.feishuWeixinStatus=stats;
const originalFetch=globalThis.fetch;
globalThis.fetch=async(...args)=>{const result=await originalFetch(...args);try{const url=String(args[0]);if(url.includes('/sendmessage')&&result.ok){const body=JSON.parse(args[1]?.body||'{}');const text=body.msg?.item_list?.[0]?.text_item?.text;if(text==='测试123'){const reply=await result.clone().json();if((reply.ret??0)===0&&(reply.errcode??0)===0){sendGate.verifiedEcho();stats.sendPaused=false;stats.echoReplies++;stats.echoVerified=true;preferences.echoVerified=true;savePreferences();}}}}catch{}return result;};
const {listIndexedWeixinAccountIds,loadWeixinAccount}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/auth/accounts.js');
const {getContextToken,restoreContextTokens}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/inbound.js');
const {sendMessageWeixin}=await import('./node_modules/@tencent-weixin/openclaw-weixin/dist/src/messaging/send.js');
const ids=listIndexedWeixinAccountIds();
if(ids.length!==1)throw Error('UNIQUE_BINDING_REQUIRED');
const id=ids[0],account=loadWeixinAccount(id);
if(!account?.token||!account?.userId)throw Error('BINDING_INCOMPLETE');
stats.bound=true;restoreContextTokens(id);
const seen=new Map();let busy=false,nextSendAt=0;
function authorized(req){const given=Buffer.from(req.headers.authorization||''),expected=Buffer.from('Bearer '+apiToken);return given.length===expected.length&&timingSafeEqual(given,expected)&&!req.headers.origin;}
const server=http.createServer(async(req,res)=>{
 const reply=(code,obj)=>{res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(obj));};
 if(!authorized(req))return reply(401,{code:'UNAUTHORIZED'});
 stats.contextReady=Boolean(getContextToken(id,account.userId));
 if(req.method==='GET'&&req.url==='/status')return reply(200,stats);
 if(req.method==='POST'&&req.url==='/enable'){stats.enabled=stats.echoVerified&&stats.contextReady;preferences.enabled=stats.enabled;savePreferences();return reply(stats.enabled?200:409,{enabled:stats.enabled});}
 if(req.method==='POST'&&req.url==='/disable'){stats.enabled=false;preferences.enabled=false;savePreferences();return reply(200,{enabled:false});}
 if(req.method!=='POST'||req.url!=='/forward')return reply(404,{code:'NOT_FOUND'});
 if(!stats.enabled||!stats.contextReady)return reply(409,{code:'NOT_READY'});
 if(!sendGate.canSend())return reply(409,{code:'SEND_PAUSED_WAIT_VERIFIED_ECHO'});
 if(busy)return reply(429,{code:'BUSY'});
 let size=0,body='';for await(const chunk of req){size+=chunk.length;if(size>65536)return reply(413,{code:'TOO_LARGE'});body+=chunk;}
 let message;try{message=JSON.parse(body);}catch{return reply(400,{code:'INVALID_MESSAGE'});}
 const now=Date.now();for(const [key,time] of seen)if(now-time>120000)seen.delete(key);
 if(typeof message.id!=='string'||message.id.length>256||typeof message.text!=='string'||message.text.length>20000||!Number.isFinite(message.sentAt)||now-message.sentAt>120000||message.sentAt>now+30000)return reply(400,{code:'INVALID_MESSAGE'});
 if(seen.has(message.id))return reply(200,{duplicate:true});
 if(seen.size>=128)return reply(429,{code:'CAPACITY'});
 busy=true;seen.set(message.id,now);
 try{const wait=Math.max(0,nextSendAt-Date.now());if(wait)await new Promise(resolve=>setTimeout(resolve,wait));if(!stats.enabled||!sendGate.canSend())return reply(409,{code:'SEND_PAUSED_WAIT_VERIFIED_ECHO'});nextSendAt=Date.now()+2000;await sendMessageWeixin({to:account.userId,text:message.text,opts:{baseUrl:account.baseUrl,token:account.token,accountId:id,contextToken:getContextToken(id,account.userId)}});stats.forwarded++;reply(200,{sent:true});}
 catch(error){stats.failed++;sendGate.failed();stats.sendPaused=true;stats.lastSendError=safeSendError(error);reply(502,{code:'SEND_FAILED_UNCERTAIN'});}
 finally{busy=false;}
});
server.listen(18882,'127.0.0.1');server.unref();
