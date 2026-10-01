// No console output. This module only projects public field shapes, never payload values.
const fields=['url','href','multi_url','open_url','behaviors','action','value','default_url','pc_url'];
export function safeUrl(value){if(typeof value!=='string'||value.length>4096)return false;try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}}
function target(value){if(safeUrl(value))return value;if(!value||typeof value!=='object'||Array.isArray(value))return '';for(const key of ['pc_url','url','default_url','href'])if(safeUrl(value[key]))return value[key];return '';}
export function buttonTarget(node){
 for(const key of ['url','href','multi_url','open_url']){const result=target(node?.[key]);if(result)return result;}
 if(safeUrl(node?.default_url))return node.default_url;
 for(const action of [...(Array.isArray(node?.behaviors)?node.behaviors.slice(0,8):[]),node?.action])if(action?.type==='open_url'){const result=target(action);if(result)return result;}
 return '';
}
export function projectCard(content){
 const meta={buttons:0,targets:0,header:false,title:false,callback:false,shapes:[]};
 if(typeof content!=='string'||content.length>524288)return {content,meta};
 try{
  const root=JSON.parse(content);let count=0;const shapes=new Set();
  meta.header=!!root?.header;meta.title=typeof root?.title==='string'||!!root?.header?.title;
  function walk(node,depth=0){
   if(depth>32||++count>2048||!node||typeof node!=='object')return;
   if(Array.isArray(node)){for(const child of node)walk(child,depth+1);return;}
   if(node.tag==='button'){
    meta.buttons++;for(const key of fields)if(Object.hasOwn(node,key)){const v=node[key];shapes.add(key+':'+(v===null?'null':Array.isArray(v)?'array':typeof v));}
    const url=buttonTarget(node);if(url){node.url=url;meta.targets++;}
    if(node.action?.type==='callback'||(Array.isArray(node.behaviors)&&node.behaviors.some(v=>v?.type==='callback')))meta.callback=true;
    return;
   }
   for(const key of ['elements','body','content','text','fields','actions'])if(node[key]&&typeof node[key]==='object')walk(node[key],depth+1);
  }
  walk(root);meta.shapes=[...shapes].sort().slice(0,20);return {content:JSON.stringify(root),meta};
 }catch{return {content,meta};}
}
export class CardDetails {
 constructor(fetch){this.fetch=fetch;this.disabled=false;this.busy=0;this.noTargets=new Set();}
 async resolve(event){
  const message=event.event.message;const original=projectCard(message.content);message.content=original.content;
  const meta={...original.meta,detail:'not_needed',code:null,requiredScopes:[]};
  const scopes=value=>typeof value==='string'?[...new Set((value.match(/(?<![a-zA-Z0-9_:.-])im:message(?::readonly|\.group_msg)?(?![a-zA-Z0-9_:.-])/g)??[]))]:[];
  if(!original.meta.buttons||original.meta.targets===original.meta.buttons)return meta;
  if(this.disabled){meta.detail='disabled';return meta;}
  const source=event.event.sender?.sender_id?.open_id??'';const key=source+':'+original.meta.shapes.join(',');
  if(this.noTargets.has(key)){meta.detail='detail_has_no_targets';return meta;}
  if(this.noTargets.size>=64){meta.detail='disabled';return meta;}
  if(this.busy>=2){meta.detail='busy';return meta;}
  this.busy++;let timeout;
  try{
   const response=await Promise.race([this.fetch(message.message_id),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('timeout')),2500);})]);
   if(response?.code!==0){meta.code=Number.isInteger(response?.code)?response.code:null;meta.requiredScopes=scopes(response?.msg);meta.detail='api_rejected';this.disabled=true;return meta;}
   const item=response.data?.items?.find(v=>v.message_id===message.message_id&&v.chat_id===message.chat_id&&v.msg_type==='interactive'&&['app','bot'].includes(v.sender?.sender_type));
   if(!item||typeof item.body?.content!=='string'){meta.detail='identity_mismatch';this.disabled=true;return meta;}
   const detail=projectCard(item.body.content);
   if(detail.meta.targets>original.meta.targets){message.content=detail.content;Object.assign(meta,detail.meta);meta.detail='enriched';}
   else{meta.detail='detail_has_no_targets';this.noTargets.add(key);}
   return meta;
  }catch(error){meta.code=Number.isInteger(error?.response?.data?.code)?error.response.data.code:null;meta.requiredScopes=scopes(error?.response?.data?.msg);meta.detail=error?.message==='timeout'?'timeout':'request_failed';this.disabled=true;return meta;}
  finally{clearTimeout(timeout);this.busy--;}
 }
}
