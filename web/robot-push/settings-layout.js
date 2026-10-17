// Layout adapter only: no notification requests, storage, subscription or setting changes.
function attachLayout() {
  const toolbar=document.querySelector('.feed-tools');
  const dialog=document.getElementById('notification-settings');
  if(!toolbar||!dialog)return false;
  toolbar.classList.add('ns-toolbar');
  if(dialog.classList.contains('ns-compact'))return true;
  dialog.classList.add('ns-compact');
  let body=dialog.querySelector('.ns-body');
  if(!body){
    // Accommodate an older cached settings module without losing its event handlers.
    body=document.createElement('div');body.className='ns-body';
    for(const child of [...dialog.children]){
      if(!child.matches('.ns-head,.ns-actions'))body.append(child);
    }
    dialog.querySelector('.ns-head')?.after(body);
  }
  body.tabIndex=0;body.setAttribute('aria-label','推送设置选项，可上下滚动');
  const management=[...body.querySelectorAll(':scope > .ns-notification,:scope > .ns-plans')];
  if(management.length){
    const details=document.createElement('details');details.className='ns-device-details';
    const summary=document.createElement('summary');summary.textContent='通知与推送码';
    const hint=document.createElement('span');hint.textContent='管理';summary.append(hint);
    details.append(summary);management[0].before(details);management.forEach(section=>details.append(section));
  }
  const viewport=window.visualViewport;
  let listening=false,frame=0;
  function measure(){
    frame=0;
    dialog.style.setProperty('--ns-viewport-height',`${viewport?.height??window.innerHeight}px`);
    dialog.style.setProperty('--ns-viewport-top',`${viewport?.offsetTop??0}px`);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(measure);}
  function openState(){
    if(dialog.open&&!listening){
      listening=true;measure();
      viewport?.addEventListener('resize',schedule);viewport?.addEventListener('scroll',schedule);
      window.addEventListener('resize',schedule);
    }else if(!dialog.open&&listening){
      listening=false;viewport?.removeEventListener('resize',schedule);viewport?.removeEventListener('scroll',schedule);
      window.removeEventListener('resize',schedule);cancelAnimationFrame(frame);frame=0;
    }
  }
  new MutationObserver(openState).observe(dialog,{attributes:true,attributeFilter:['open']});
  dialog.addEventListener('close',openState);openState();
  return true;
}
if(!attachLayout()){
  // Settings and the feed shell are separate modules; stop observing once both mount.
  const ready=new MutationObserver(()=>{if(attachLayout())ready.disconnect();});
  ready.observe(document.body,{childList:true,subtree:true});
}
