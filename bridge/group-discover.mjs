for(const method of ['log','info','warn','error','debug','trace'])console[method]=()=>{};
const Lark=await import('@larksuiteoapi/node-sdk');
import {createInterface} from 'node:readline';
const silent={error(){},warn(){},info(){},debug(){},trace(){}};
let handling=false;
const emit=record=>process.stdout.write(JSON.stringify(record)+'\n',()=>process.exit(0));
const input=createInterface({input:process.stdin});
input.once('line',async line=>{
 handling=true;let target='';
 try{
  const config=JSON.parse(line.replace(/^\uFEFF/,''));line='';target=config.target;
  if(typeof target!=='string'||!target||target.length>256)throw new Error();
  const client=new Lark.Client({appId:config.appId,appSecret:config.appSecret,domain:Lark.Domain.Feishu,logger:silent});config.appSecret='';
  let token,complete=false;const matches=[];let code=-1;
  for(let page=0;page<20;page++){
   const response=await client.im.chat.list({params:{page_size:100,...(token?{page_token:token}:{})}});
   code=Number.isInteger(response.code)?response.code:-1;if(code!==0)break;
   for(const item of response.data?.items??[])if(item.name===target && typeof item.chat_id==='string' && /^oc_[a-zA-Z0-9_-]+$/.test(item.chat_id))matches.push(item.chat_id);
   if(!response.data?.has_more){complete=true;break;}token=response.data.page_token;if(!token)break;
  }
  const unique=[...new Set(matches)];
  emit({kind:'group_match',target,code,complete,count:unique.length,chatId:complete&&unique.length===1?unique[0]:null});
 }catch(error){emit({kind:'group_match',target,code:Number.isInteger(error?.response?.data?.code)?error.response.data.code:-1,complete:false,count:0,chatId:null});}
});
input.on('close',()=>{if(!handling)process.exit(1);});
