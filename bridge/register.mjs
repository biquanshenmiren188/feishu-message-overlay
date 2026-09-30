import * as Lark from '@larksuiteoapi/node-sdk';
// Invoked only by the desktop setup window. stdout is its anonymous private pipe.
// No console logging, result printing, files, message APIs, or credential CLI parameters.
const abort=new AbortController(); process.stdin.resume(); process.stdin.on('end',()=>{abort.abort();process.exit(0);});
const emit=record=>process.stdout.write(JSON.stringify(record)+'\n');
process.on('uncaughtException',()=>{emit({kind:'error'});process.exit(1);});
process.on('unhandledRejection',()=>{emit({kind:'error'});process.exit(1);});
try {
  const result=await Lark.registerApp({
    domain:'accounts.feishu.cn', createOnly:true, signal:abort.signal,
    appPreset:{name:'飞书机器人消息小窗',desc:'仅在本机展示指定群中其他机器人的新消息；无发送消息能力'},
    addons:{preset:false,scopes:{tenant:['im:message.group_msg.include_bot:read','im:chat:read'],user:[]},events:{items:{tenant:['im.message.receive_v1'],user:[]}}},
    onQRCodeReady:info=>{
      const url=new URL(info.url);
      if(url.protocol!=='https:' || !['accounts.feishu.cn','open.feishu.cn'].includes(url.hostname)) throw new Error('unexpected_host');
      emit({kind:'authorize',url:info.url,expireIn:info.expireIn});
    },
    onStatusChange:()=>{} // no identifiers or secrets are logged
  });
  emit({kind:'registered',appId:result.client_id,secret:result.client_secret});
  result.client_secret='';
  process.exit(0);
} catch {emit({kind:'error'});process.exit(1);}
