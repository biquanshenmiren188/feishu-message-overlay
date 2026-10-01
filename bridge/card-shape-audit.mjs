// Explicit one-shot diagnostic: no string values, message IDs or URLs are returned.
export function auditCard(content){
 const rows=new Map();let visited=0,complete=true,httpStrings=0,httpMentions=0,encodedJson=0,buttons=0,buttonTargets=0,buttonLabels=0;
 const safeKey=k=>/^[a-z][a-z_]{0,39}$/.test(k)?k:'<unknown-key>';
 const url=v=>{try{const u=new URL(v);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password;}catch{return false;}};
 function walk(value,path='$',depth=0,inButton=false){
  if(++visited>8192||depth>40){complete=false;return;}
  const type=value===null?'null':Array.isArray(value)?'array':typeof value;
  if(rows.size<256)rows.set(path+':'+type,{path,type});else complete=false;
  const button=value&&type==='object'&&value.tag==='button';
  if(button){buttons++;if(typeof value.text==='string'||typeof value.text?.content==='string'||typeof value.text?.text==='string')buttonLabels++;}
  if(type==='string'){
   if(value.length>524288){complete=false;return;}
   if(url(value)){httpStrings++;if(inButton)buttonTargets++;}
   httpMentions+=(value.match(/https?:\/\//g)??[]).length;
   if(/^[\s]*[\[{]/.test(value)){try{const decoded=JSON.parse(value);if(decoded&&typeof decoded==='object'){encodedJson++;walk(decoded,path+'.<encoded-json>',depth+1,inButton);}}catch{}}
  }else if(type==='array'){for(const v of value)walk(v,path+'[]',depth+1,inButton);}
  else if(type==='object'){for(const [k,v]of Object.entries(value))walk(v,path+'.'+safeKey(k),depth+1,inButton||button);}
 }
 try{walk(JSON.parse(content));}catch{return {parsed:false};}
 return {parsed:true,complete,visited,buttons,buttonLabels,buttonTargets,httpStrings,httpMentions,encodedJson,fields:[...rows.values()]};
}
