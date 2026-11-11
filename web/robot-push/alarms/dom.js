// Update only differing nodes, preserving focus and existing controls.
export function patchHTML(target,html){
 const template=document.createElement('template');template.innerHTML=html;
 function patch(a,b){
  if(a.nodeType!==b.nodeType||a.nodeName!==b.nodeName){a.replaceWith(b.cloneNode(true));return;}
  if(a.nodeType===3){if(a.data!==b.data)a.data=b.data;return;}
  if(a.nodeType!==1)return;
  for(const attr of [...a.attributes])if(!b.hasAttribute(attr.name))a.removeAttribute(attr.name);
  for(const attr of b.attributes)if(a.getAttribute(attr.name)!==attr.value)a.setAttribute(attr.name,attr.value);
  children(a,b);
 }
 function children(a,b){const old=[...a.childNodes],next=[...b.childNodes];for(let i=0;i<Math.max(old.length,next.length);i++){if(!next[i])old[i].remove();else if(!old[i])a.append(next[i].cloneNode(true));else patch(old[i],next[i]);}}
 children(target,template.content);
}
