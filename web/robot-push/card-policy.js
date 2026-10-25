/* The BOT and desktop share server-side card decisions, including OI/history. */
import {openCardManager} from './card-manager.js?v=20261024-clarity1';
export class CardPolicyState {
  constructor(){this.reset('');}
  reset(token){this.token=token;this.data=null;this.receivedAt=0;this.error='';this.access='unknown';}
  accept(data,now){
    if(!data||!Number.isInteger(data.revision)||typeof data.cardsEnabled!=='boolean'||!data.decisions||typeof data.decisions!=='object'||Array.isArray(data.decisions)||Object.values(data.decisions).some(v=>!['hide','allow'].includes(v)))throw Error('规则响应无效');
    this.data=data;this.receivedAt=now;this.error='';this.access='profile';
  }
  denied(){this.data=null;this.receivedAt=0;this.access='unknown';}
  canManage(now){return !!this.token&&this.access==='profile'&&!!this.data&&now-this.receivedAt<10000;}
  outcome(card,now){
    if(!this.token)return 'public';
    if(!this.data||now-this.receivedAt>=10000)return 'pending';
    if(!this.data.cardsEnabled)return 'hide';
    return this.data.decisions[card.pair||card.id]||'pending';
  }
  visible(card,now){return ['public','allow'].includes(this.outcome(card,now));}
  emptyMessage(cards,now){
    if(!this.token||cards.some(c=>this.visible(c,now)))return '';
    if(!this.data||now-this.receivedAt>=10000||cards.some(c=>this.outcome(c,now)==='pending'))return '等待卡片规则校验后显示';
    if(!this.data.cardsEnabled)return '行情卡片接收已关闭，可在“卡片规则”恢复';
    return cards.length?'当前卡片均已被规则屏蔽':'';
  }
}

export function createCardPolicy(toolbar,render,{renderCard,preserveViewport=(_board,commit)=>commit()}={}){
  const css=document.createElement('link');css.rel='stylesheet';css.href='/radar/robot-push/card-policy.css?v=20261025-blocked1';document.head.append(css);
  const state=new CardPolicyState(),status=document.createElement('span'),group=document.createElement('div'),link=document.createElement('a');
  group.className='bp-policy';status.className='bp-policy-status';status.setAttribute('role','status');
  const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  const settings=standalone?'/radar/push-test/settings/':'/radar/robot-push/settings/';
  link.textContent='卡片规则';link.href=settings+'?channel=cards';link.className='bp-policy-link';
  const blockedButton=document.createElement('button');blockedButton.type='button';blockedButton.className='bp-blocked-button';blockedButton.textContent='已屏蔽 0 张';blockedButton.hidden=true;blockedButton.setAttribute('aria-haspopup','dialog');
  link.target='_blank';link.rel='noopener';group.append(status,blockedButton,link);toolbar.append(group);
  let busy=false,identity='',controller=null,identityRevision=0,latestRows=[],preview=null;
  const token=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
  function syncIdentity(){const next=token();if(next!==identity){identity=next;identityRevision++;controller?.abort();state.reset(next);latestRows=[];if(preview){preview.list.replaceChildren();preview.dialog.close();}}return next;}
  function updatePreview(now){
    if(!preview)return;
    if(!state.canManage(now)){preview.list.replaceChildren();preview.nodes.clear();preview.message.textContent='规则尚未确认，请关闭后重试。';return;}
    const hidden=latestRows.filter(c=>state.outcome(c.data,now)==='hide');
    preview.title.textContent=`已屏蔽卡片 · ${hidden.length} 张`;
    preview.message.textContent=hidden.length?'仅查看，不改变屏蔽规则。数据为最近快照，非当前可执行报价；失效卡片按原期限移除。':'当前没有被屏蔽的卡片。';
    preserveViewport(preview.list,()=>{
      const keep=new Set();
      for(const c of hidden){
        const id=c.data.id;keep.add(id);
        const reason=state.data.cardsEnabled?'已被本方案规则屏蔽':'本方案行情卡片接收已关闭';
        const stamp=JSON.stringify([c.data,c.expiredAt,reason]);let saved=preview.nodes.get(id);
        if(!saved||saved.stamp!==stamp&&now-preview.valuesAt>=10000){
          const node=renderCard(c),note=document.createElement('p');note.className='bp-blocked-reason';note.textContent=reason;
          node.card.prepend(note);node.card.dataset.pair=c.data.pair||'';decorate(node.card,c.data);
          const action=saved?.card.contains(document.activeElement)?document.activeElement.dataset.action:null;
          if(saved)saved.card.replaceWith(node.card);else preview.list.append(node.card);
          saved={...node,stamp};preview.nodes.set(id,saved);
          if(action)node.card.querySelector(`[data-action="${action}"]`)?.focus({preventScroll:true});
        }
        saved.card.querySelector('.bp-blocked-reason').textContent=reason;
        saved.age.textContent=c.missingAt!=null?'已屏蔽 · 已失效':now>=c.expiredAt?'已屏蔽 · 待确认':'已屏蔽';saved.card.classList.toggle('bp-expired',now>=c.expiredAt);
      }
      for(const [id,node]of preview.nodes)if(!keep.has(id)){node.card.remove();preview.nodes.delete(id);}
    });
    if(now-preview.valuesAt>=10000)preview.valuesAt=now;
  }
  blockedButton.onclick=()=>{
    syncIdentity();if(preview||!renderCard||!state.canManage(Date.now()))return;
    const dialog=document.createElement('dialog'),header=document.createElement('header'),title=document.createElement('h2'),close=document.createElement('button'),message=document.createElement('p'),list=document.createElement('section');
    dialog.className='bp-blocked-dialog';dialog.setAttribute('aria-label','已屏蔽卡片');close.type='button';close.textContent='关闭';close.setAttribute('aria-label','关闭已屏蔽卡片');message.className='bp-blocked-help';list.className='bp-blocked-list';list.setAttribute('aria-label','已屏蔽卡片列表');
    header.append(title,close);dialog.append(header,message,list);document.body.append(dialog);
    preview={dialog,title,message,list,nodes:new Map(),valuesAt:-Infinity};close.onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{preview=null;dialog.remove();if(!blockedButton.hidden)blockedButton.focus({preventScroll:true});});
    updatePreview(Date.now());dialog.showModal();close.focus({preventScroll:true});
  };
  async function refresh(){
    const auth=syncIdentity();if(busy||document.hidden||!auth)return;
    const revision=identityRevision;busy=true;controller=new AbortController();const timer=setTimeout(()=>controller.abort(),7000);
    try{
      const res=await fetch('/radar/push-test/api/card-decisions',{headers:{Authorization:'Bearer '+auth},cache:'no-store',redirect:'error',signal:controller.signal});
      if(auth!==token()||revision!==identityRevision)return;
      if(!res.ok){state.error=res.status===401?'连接已失效，请重新连接推送码':res.status===403?'当前推送码无权读取此方案，请重新连接':'规则同步失败，正在重试';state.denied();return;}
      const data=await res.json();if(auth===token()&&revision===identityRevision)state.accept(data,Date.now());
    }catch{if(auth===token()&&revision===identityRevision){state.error='规则同步失败，正在重试';state.denied();}}
    finally{clearTimeout(timer);busy=false;render();}
  }
  function summary(rows){
    syncIdentity();const now=Date.now(),blocked=rows.filter(c=>state.outcome(c.data,now)==='hide').length,pending=rows.filter(c=>state.outcome(c.data,now)==='pending').length;
    latestRows=rows;blockedButton.hidden=!state.token||!renderCard;blockedButton.disabled=!state.canManage(now);blockedButton.textContent=`已屏蔽 ${blocked} 张`;blockedButton.title=blockedButton.disabled?'等待本方案规则校验后查看':'查看被本方案屏蔽的卡片';updatePreview(now);
    for(const b of document.querySelectorAll('.bp-manage-rules')){b.disabled=!state.canManage(now);b.title=b.disabled?'连接自己的推送码并读取规则后可管理本方案':b.getAttribute('aria-label');}
    status.textContent=!state.token?'公共浏览 · 连接自己的推送码后应用本方案规则':!state.data||now-state.receivedAt>=10000?(state.error||'正在同步本方案卡片规则…')+' · 暂停展示':!state.data.cardsEnabled?'本方案行情卡片已暂停':`本方案规则已接入${pending?' · 待校验 '+pending+' 张':''}${state.error?' · 同步重试中':''}`;
    const empty=document.querySelector('.bp-empty');
    // A genuine empty market keeps the original source/connection message.
    const message=state.emptyMessage(rows.map(c=>c.data),now);
    if(empty&&message){empty.hidden=false;empty.textContent=message;}
  }
  function decorate(card,data){
    if(card.querySelector('[data-action="manage-rules"]'))return;
    const coin=String(data.asset||'').split(':').at(-1).toUpperCase(),footer=card.querySelector('.bp-card-foot');if(!footer)return;
    const b=document.createElement('button');b.type='button';b.textContent='管理';b.title='管理 '+coin+' 的三端规则';b.setAttribute('aria-label',b.title);b.dataset.action='manage-rules';b.className='bp-manage-rules';b.onclick=()=>openCardManager(coin,{onSaved:()=>{render();refresh();}});footer.insertBefore(b,footer.querySelector('.bp-radar'));
  }
  const wake=()=>{syncIdentity();render();refresh();};
  window.addEventListener('storage',wake);window.addEventListener('focus',wake);document.addEventListener('visibilitychange',()=>{if(!document.hidden)wake();});
  syncIdentity();setTimeout(refresh,0);setInterval(refresh,3000);
  return {visible:data=>{syncIdentity();return state.visible(data,Date.now());},decorate,summary};
}
