// Local subprocess protocol fixture. No SDK import, HTTP, credentials, or account use.
import {createInterface} from 'node:readline';
const input=createInterface({input:process.stdin});
const emit=record=>process.stdout.write(JSON.stringify(record)+'\n');
input.once('line',line=>{
  const config=JSON.parse(line); const chat=config.chatIds[0];
  const event={header:{event_type:'im.message.receive_v1'},event:{sender:{sender_type:'bot',sender_id:{open_id:'synthetic-bot'}},message:{message_id:'synthetic-pipe-message',chat_id:chat,chat_type:'group',create_time:String(Date.now()),message_type:'text',content:'{"text":"本地契约测试：机器人告警"}'}}};
  emit({kind:'status',state:'connected'}); emit({kind:'event',payload:event}); emit({kind:'event',payload:event});
  input.on('line',command=>{
    if(command==='reconnect'){emit({kind:'status',state:'reconnecting'});setTimeout(()=>{emit({kind:'status',state:'connected'});emit({kind:'event',payload:event});},150);}
    if(command==='fail'){emit({kind:'status',state:'failed'});}
    if(command==='stop'){process.exit(0);}
  });
});
input.on('close',()=>process.exit(0));
