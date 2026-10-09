// Transport only: source timestamps and expiry fields are never rewritten.
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const safe=k=>!['__proto__','constructor','prototype'].includes(k);
export function diffSnapshot(before,after,path=[],ops=[]){
 if(equal(before,after))return ops;
 if(Array.isArray(before)&&Array.isArray(after)){
  let start=0,tail=0;
  while(start<Math.min(before.length,after.length)&&equal(before[start],after[start]))start++;
  while(tail<Math.min(before.length,after.length)-start&&equal(before[before.length-1-tail],after[after.length-1-tail]))tail++;
  ops.push(['splice',path,start,before.length-start-tail,after.slice(start,after.length-tail)]);
 }else if(object(before)&&object(after)&&path.length<5&&Object.keys(after).every(safe)&&Object.keys(before).every(safe)){
  for(const key of Object.keys(before))if(!Object.hasOwn(after,key))ops.push(['delete',[...path,key]]);
  for(const key of Object.keys(after)){
   if(!Object.hasOwn(before,key))ops.push(['set',[...path,key],after[key]]);
   else diffSnapshot(before[key],after[key],[...path,key],ops);
  }
 }else ops.push(['set',path,after]);
 return ops;
}
export function applySnapshot(before,ops){
 if(!Array.isArray(ops)||ops.length>100000)throw Error('Invalid delta');
 let result=structuredClone(before);
 for(const op of ops){
  const [kind,path]=op;
  if(!Array.isArray(path)||path.length>6||path.some(k=>typeof k!=='string'||!safe(k)))throw Error('Invalid delta path');
  let parent=result;
  for(const key of path.slice(0,-1)){if(!object(parent)||!Object.hasOwn(parent,key))throw Error('Missing delta parent');parent=parent[key];}
  const key=path.at(-1);
  if(kind==='set'){
   if(!path.length)result=structuredClone(op[2]);
   else{if(!object(parent))throw Error('Invalid delta parent');parent[key]=structuredClone(op[2]);}
  }else if(kind==='delete'){
   if(!path.length||!object(parent)||!Object.hasOwn(parent,key))throw Error('Invalid deletion');delete parent[key];
  }else if(kind==='splice'){
   const target=path.length?parent?.[key]:result,[,,start,count,items]=op;
   if(!Array.isArray(target)||!Number.isInteger(start)||!Number.isInteger(count)||start<0||count<0||start+count>target.length||!Array.isArray(items))throw Error('Invalid array delta');
   // Avoid spreading large arrays into function arguments.
   const next=target.slice(0,start).concat(structuredClone(items),target.slice(start+count));
   if(path.length)parent[key]=next;else result=next;
  }else throw Error('Unknown delta operation');
 }
 return result;
}
