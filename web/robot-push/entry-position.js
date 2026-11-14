// Entry positioning is separate from timed admission of subsequent messages.
export function createEntryPosition({board,feed,prepare,settled,busy=()=>false,target=window}) {
 let pending=true,frame=0,revision=0,following=false;
 const phase=value=>{if(board.dataset)board.dataset.entryPosition=value;};
 phase('pending');
 const cancel=()=>{pending=false;following=false;revision++;target.cancelAnimationFrame(frame);frame=0;phase('manual');};
 function flush(){
  frame=0;
  if(!pending||target.document.hidden||busy()||!feed.children.length||!board.clientHeight)return;
  const own=revision;phase('positioning');prepare();
  frame=target.requestAnimationFrame(()=>{
   frame=target.requestAnimationFrame(()=>{
    frame=0;if(own!==revision||!pending||target.document.hidden||busy())return;
    board.scrollTop=board.scrollHeight;
    pending=false;following=true;phase('latest');settled();
   });
  });
 }
 function update(){if(pending&&!frame)frame=target.requestAnimationFrame(flush);}
 function request(){revision++;target.cancelAnimationFrame(frame);frame=0;pending=true;phase('pending');update();}
 const observer=new target.ResizeObserver(()=>{if(pending)update();else if(following&&!busy())request();});
 observer.observe(board);
 // Layout-generated scroll events are not manual reading gestures.
 board.addEventListener('wheel',cancel,{passive:true});
 board.addEventListener('touchstart',cancel,{passive:true});
 board.addEventListener('pointerdown',cancel,{passive:true});
 board.addEventListener('keydown',event=>{if(['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key))cancel();});
 target.document.addEventListener('visibilitychange',()=>{if(!target.document.hidden)request();});
 target.addEventListener('pageshow',event=>{if(event.persisted)request();});
 return {update,request,cancel,setAtTail(value){if(!pending)following=value;},get pending(){return pending;}};
}
