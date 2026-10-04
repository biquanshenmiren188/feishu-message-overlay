// stdout is a private pipe to the single Python state writer. Never redirect it to a log.
for(const name of ['log','info','warn','error','debug','trace'])console[name]=()=>{};
import {createInterface} from 'node:readline';
import {BotGate} from './filter.mjs';
import {digest,projectEvent} from './cloud-project.mjs';
const Lark=await import('@larksuiteoapi/node-sdk');
const silent={error(){},warn(){},info(){},debug(){},trace(){}};
let client,gate,rest,timer,busy=false,stopping=false,configured=false,delay=60000;
let blocked=false,queuedBytes=0;const outbound=[];
function stop(){if(stopping)return;stopping=true;clearTimeout(timer);client?.close({force:true});process.exit(0);}
function emit(value){
 const line=JSON.stringify(value)+'\n';
 if(blocked){if(outbound.length>=128||queuedBytes+line.length>2*1024*1024){stop();return;}outbound.push(line);queuedBytes+=line.length;return;}
 blocked=!process.stdout.write(line);
}
process.stdout.on('drain',()=>{blocked=false;while(outbound.length&&!blocked){const line=outbound.shift();queuedBytes-=line.length;blocked=!process.stdout.write(line);}});
process.stdout.on('error',stop);
async function membership(){
 if(busy||stopping)return;busy=true;
 try{
  let token,complete=false;const groups=[];
  for(let page=0;page<20;page++){
   const r=await rest.im.chat.list({params:{page_size:100,...(token?{page_token:token}:{})}});
   if(r.code!==0)throw new Error();
   for(const g of r.data?.items??[])if(typeof g.chat_id==='string'&&/^oc_[a-zA-Z0-9_-]+$/.test(g.chat_id))groups.push({id:g.chat_id,groupId:digest(g.chat_id),name:typeof g.name==='string'?g.name.slice(0,256):''});
   if(!r.data?.has_more){complete=true;break;}token=r.data.page_token;if(!token)break;
  }
  if(!complete)throw new Error();gate.replaceChats(groups.map(g=>g.id));delay=60000;emit({kind:'membership',verified:true,groups});
 }catch{gate.replaceChats([]);delay=Math.min(300000,delay*2);emit({kind:'membership',verified:false,groups:[]});}
 finally{busy=false;if(!stopping)timer=setTimeout(membership,delay);}
}
process.on('uncaughtException',()=>{emit({kind:'status',connected:false});stop();});
process.on('unhandledRejection',()=>{emit({kind:'status',connected:false});stop();});
process.on('SIGTERM',stop);process.on('SIGINT',stop);
const input=createInterface({input:process.stdin,crlfDelay:Infinity});input.on('close',stop);
input.on('line',async line=>{
 if(configured){if(line==='stop')stop();return;}configured=true;
 try{
  if(line.length>16384)throw new Error();const cfg=JSON.parse(line);line='';
  if(typeof cfg.appId!=='string'||!/^cli_[a-zA-Z0-9]+$/.test(cfg.appId)||typeof cfg.appSecret!=='string'||!cfg.appSecret)throw new Error();
  gate=new BotGate(['oc_bootstrap']);gate.replaceChats([]);
  rest=new Lark.Client({appId:cfg.appId,appSecret:cfg.appSecret,domain:Lark.Domain.Feishu,logger:silent});
  await membership();
  client=new Lark.WSClient({appId:cfg.appId,appSecret:cfg.appSecret,domain:Lark.Domain.Feishu,logger:silent,autoReconnect:true,handshakeTimeoutMs:15000,
   onReady:()=>emit({kind:'status',connected:true}),onReconnecting:()=>emit({kind:'status',connected:false}),
   onReconnected:()=>{gate.resume();emit({kind:'status',connected:true});},onError:()=>{emit({kind:'status',connected:false});stop();}});
  cfg.appSecret='';
  await client.start({eventDispatcher:new Lark.EventDispatcher({logger:silent}).register({'im.message.receive_v1':data=>{
   // Synchronous bounded projection; never await REST in the acknowledgement path.
   const accepted=gate.accept(data);if(accepted){const message=projectEvent(accepted);if(message)emit({kind:'message',message});}
  }})});
 }catch{emit({kind:'status',connected:false});stop();}
});
