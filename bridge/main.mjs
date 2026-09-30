import * as Lark from '@larksuiteoapi/node-sdk';
import { createInterface } from 'node:readline';
import { BotGate } from './filter.mjs';
// stdout is private IPC to the desktop app, never a file or console log.
const silent = {error(){},warn(){},info(){},debug(){},trace(){}};
let client, gate, configured=false, blocked=false;
function emit(record) { if(blocked) return false; blocked=!process.stdout.write(JSON.stringify(record)+'\n'); return true; }
process.stdout.on('drain',()=>{blocked=false;});
function fail(reason='connection_failed'){ emit({kind:'status',state:reason==='dedup_capacity'?'protected':'failed'}); client?.close({force:true}); process.exitCode=1; setTimeout(()=>process.exit(1),100); }
process.on('uncaughtException',fail); process.on('unhandledRejection',fail);
const input=createInterface({input:process.stdin,crlfDelay:Infinity});
input.on('close',()=>{client?.close();process.exit(0);});
input.on('line',async line=>{
  if(configured){ if(line==='stop'){client?.close();process.exit(0);} return; }
  configured=true;
  try {
    if(line.length>16384) throw new Error('invalid_config');
    const config=JSON.parse(line); line='';
    if(typeof config.appId!=='string' || !/^cli_[a-zA-Z0-9]+$/.test(config.appId) || typeof config.appSecret!=='string' || !config.appSecret) throw new Error('invalid_config');
    gate=new BotGate(config.chatIds,Date.now(),config.botIds ?? []);
    client=new Lark.WSClient({appId:config.appId,appSecret:config.appSecret,domain:Lark.Domain.Feishu,logger:silent,autoReconnect:true,
      handshakeTimeoutMs:15000,
      onReady:()=>emit({kind:'status',state:'connected'}),
      onReconnecting:()=>emit({kind:'status',state:'reconnecting'}),
      onReconnected:()=>{gate.resume();emit({kind:'status',state:'connected'});},
      onError:()=>fail()});
    config.appSecret='';
    await client.start({eventDispatcher:new Lark.EventDispatcher({logger:silent}).register({
      'im.message.receive_v1':async data=>{
        try {const event=gate.accept(data); if(event && !emit({kind:'event',payload:event})) fail();}
        catch(error) { fail(error?.message==='dedup_capacity'?'dedup_capacity':'connection_failed'); }
      }
    })});
  }catch{fail();}
});
