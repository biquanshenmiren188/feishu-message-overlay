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

// A selectable field remains usable when Safari refuses both programmatic methods.
export function showCopyFallback(title,payload,opener) {
  const dialog=document.createElement('dialog');dialog.className='bp-dialog bp-copy-dialog';dialog.setAttribute('aria-label',title);
  const heading=document.createElement('h2');heading.textContent=title;
  const status=document.createElement('p');status.textContent='自动复制未成功。可重试复制，或选择全部后长按复制。';status.setAttribute('role','status');
  const field=document.createElement('textarea');field.value=clipboardText(payload);field.readOnly=true;field.spellcheck=false;field.setAttribute('aria-label','待复制文本');
  Object.assign(field.style,{display:'block',boxSizing:'border-box',width:'100%',height:'min(240px,35dvh)',margin:'12px 0',padding:'10px',font:'16px/1.5 ui-monospace,monospace',whiteSpace:'pre',overflow:'auto',border:'1px solid #d2d2d7',borderRadius:'8px',userSelect:'text',webkitUserSelect:'text'});
  const actions=document.createElement('div');Object.assign(actions.style,{display:'flex',flexWrap:'wrap',gap:'8px'});
  const retry=document.createElement('button'),select=document.createElement('button'),close=document.createElement('button');
  retry.textContent='重试复制';select.textContent='选择全部';close.textContent='关闭';
  for(const button of [retry,select,close]){button.type='button';button.style.minHeight='44px';actions.append(button);}
  retry.onclick=async()=>{try{if(await copyText(field.value))status.textContent='已复制，可以返回目标应用粘贴。';}catch{status.textContent='请点“选择全部”，再长按文本并选择复制。';}};
  select.onclick=()=>{field.focus({preventScroll:true});field.select();field.setSelectionRange(0,field.value.length);};
  close.onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();if(opener?.isConnected)opener.focus({preventScroll:true});});
  dialog.append(heading,status,field,actions);document.body.append(dialog);dialog.showModal();
}
