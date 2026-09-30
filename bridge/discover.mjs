// Never send SDK console output through the private metadata protocol.
for(const method of ['log','info','warn','error','debug','trace'])console[method]=()=>{};
const Lark=await import('@larksuiteoapi/node-sdk');
import {createInterface} from 'node:readline';
const input=createInterface({input:process.stdin});
const silent={error(){},warn(){},info(){},debug(){},trace(){}};
const emit=record=>process.stdout.write(JSON.stringify(record)+'\n',()=>process.exit(0));
let handling=false;
input.once('line',async line=>{
 handling=true;
 let appId='';
 try{
  const config=JSON.parse(line.replace(/^\uFEFF/,''));line='';appId=config.appId;
  if(config.mode!=='bot-only'||!/^cli_[a-zA-Z0-9]+$/.test(appId))throw new Error();
  const client=new Lark.Client({appId,appSecret:config.appSecret,domain:Lark.Domain.Feishu,logger:silent});config.appSecret='';
  const response=await client.request({method:'GET',url:'https://open.feishu.cn/open-apis/bot/v3/info/',timeout:15000});
  const code=Number.isInteger(response.code)?response.code:-1;
  const bot=response.bot;
  emit({kind:'bot_info',appId,code,botName:typeof bot?.app_name==='string'?bot.app_name.slice(0,256):null,activateStatus:Number.isInteger(bot?.activate_status)?bot.activate_status:null});
 }catch{emit({kind:'bot_info',appId,code:-1,botName:null,activateStatus:null});}
});
input.on('close',()=>{if(!handling)process.exit(1);});
