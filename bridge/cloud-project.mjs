import {createHash} from 'node:crypto';
import {projectCard,buttonTarget,safeUrl} from './card-content.mjs';
export const digest=value=>createHash('sha256').update(value).digest('hex');
export function projectEvent(event){
 const m=event.event.message;let root;
 try{root=JSON.parse(m.message_type==='interactive'?projectCard(m.content).content:m.content);}catch{return null;}
 let title='',body='',actions=[],headerTone='grey',visited=0,budget=15900;
 const lines=[];const text=n=>typeof n==='string'?n:typeof n?.text==='string'?n.text:typeof n?.content==='string'?n.content:'';
 const add=v=>{if(typeof v!=='string'||!v.trim()||budget<=0)return;v=v.slice(0,budget);lines.push(v);budget-=v.length;};
 function visit(n,depth=0){
  if(depth>32||++visited>2048||budget<=0||!n||typeof n!=='object')return;
  if(Array.isArray(n)){for(const child of n)visit(child,depth+1);return;}
  if(n.tag==='button'){const url=buttonTarget(n),label=text(n.text)||text(n);if(actions.length<8&&label&&safeUrl(url))actions.push({label:label.slice(0,128),url});else if(label)add(label+' [interactive action unavailable]');return;}
  if(n.tag==='a'){add(text(n));if(safeUrl(n.href))add(n.href);return;}
  if(['text','plain_text','lark_md','markdown'].includes(n.tag)){add(text(n));return;}
  for(const key of ['elements','content','text','fields','actions','body','columns'])if(typeof n[key]==='string')add(n[key]);else if(n[key])visit(n[key],depth+1);
 }
 if(m.message_type==='text')add(root?.text);
 else if(m.message_type==='interactive'){
  headerTone=['blue','red','green','orange','purple','indigo','turquoise','yellow','grey'].includes(root.header?.template)?root.header.template:'grey';
  title=(typeof root.title==='string'?root.title:text(root.header?.title)).slice(0,512);visit(root.elements??root.body);
 }else if(m.message_type==='post'){
  const post=root.zh_cn??root.en_us??root;title=text(post.title).slice(0,512);visit(post.content);
 }else add('[Unsupported message type: '+String(m.message_type).slice(0,40)+']');
 body=lines.join('\n').slice(0,16000);if(!title&&!body&&!actions.length)body='[No readable text provided by API]';
 return {id:digest(m.chat_id+'\n'+m.message_id),groupId:digest(m.chat_id),senderType:'bot',sentAt:new Date(Number(m.create_time)).toISOString(),title,body,actions,headerTone};
}
