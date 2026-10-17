// Only the clipboard boundary changes; strategy builders retain their existing protocol.
export function clipboardText(text) {
  const prefix='ASTRO-QUICK-COPY:';
  if(!text.startsWith(prefix))return text;
  return JSON.stringify(JSON.parse(text.slice(prefix.length)),null,2);
}

let request=0;
export async function copyText(payload) {
  const text=clipboardText(payload), current=++request;
  // Called directly from the click handler, before any asynchronous work.
  try { await navigator.clipboard.writeText(text); return current===request; } catch {}
  if(current!==request)return false;
  const previous=document.activeElement;
  const host=previous?.closest('dialog[open], [role="dialog"]') || document.body;
  const field=document.createElement('textarea');field.value=text;field.readOnly=true;
  Object.assign(field.style,{position:'fixed',top:'0',left:'0',width:'1px',height:'1px',opacity:'0',fontSize:'16px'});
  const plainCopy=event=>{
    if(!event.clipboardData)return;
    event.clipboardData.clearData();event.clipboardData.setData('text/plain',text);event.preventDefault();
  };
  host.append(field);document.addEventListener('copy',plainCopy,true);
  try {
    field.focus({preventScroll:true});field.select();field.setSelectionRange(0,text.length);
    if(document.activeElement!==field || field.selectionStart!==0 || field.selectionEnd!==text.length || !document.execCommand('copy'))throw Error('复制失败');
    return true;
  } finally {
    document.removeEventListener('copy',plainCopy,true);field.remove();previous?.focus({preventScroll:true});
  }
}
