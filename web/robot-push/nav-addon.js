// Additive integration: preserve the site's bundle and existing tab behavior.
(()=>{
 function attach(){
  const tab=[...document.querySelectorAll('button,a')].find(e=>e.textContent.trim()==='充提查询');
  if(!tab||!tab.parentElement||tab.parentElement.querySelector('[data-robot-push-nav]'))return;
  const a=document.createElement('a');a.href='/radar/robot-push/';a.textContent='机器人推送';a.dataset.robotPushNav='true';a.className=tab.className;
  Object.assign(a.style,{display:'inline-flex',alignItems:'center',justifyContent:'center',textDecoration:'none',whiteSpace:'nowrap'});
  tab.insertAdjacentElement('afterend',a);
  const url=new URL(location.href),requested=url.searchParams.get('robot-return');
  if(requested==='opportunities'){
   const previous=[...tab.parentElement.querySelectorAll('button')].find(e=>e.textContent.trim()==='机会筛选');
   if(previous){url.searchParams.delete('robot-return');history.replaceState(null,'',url);previous.click();}
  }
 }
 let queued=false;const observer=new MutationObserver(()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;attach();});});
 observer.observe(document.getElementById('root')||document.body,{childList:true,subtree:true});attach();
})();
