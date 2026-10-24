/* The BOT and desktop share server-side card decisions, including OI/history. */
import {openCardManager} from './card-manager.js?v=20261024-manualsave1';
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

export function createCardPolicy(toolbar,render){
  const css=document.createElement('link');css.rel='stylesheet';css.href='/radar/robot-push/card-policy.css?v=20261024-manualsave1';document.head.append(css);
  const state=new CardPolicyState(),status=document.createElement('span'),group=document.createElement('div'),link=document.createElement('a');
  group.className='bp-policy';status.className='bp-policy-status';status.setAttribute('role','status');
  const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  const settings=standalone?'/radar/push-test/settings/':'/radar/robot-push/settings/';
  link.textContent='卡片规则';link.href=settings+'?channel=cards';link.className='bp-policy-link';
  link.target='_blank';link.rel='noopener';group.append(status,link);toolbar.append(group);
  let busy=false,identity='',controller=null,identityRevision=0;
  const token=()=>{try{return localStorage.getItem('radar-settings-token')||localStorage.getItem('radar-test-token')||'';}catch{return '';}};
  function syncIdentity(){const next=token();if(next!==identity){identity=next;identityRevision++;controller?.abort();state.reset(next);}return next;}
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
    for(const b of document.querySelectorAll('.bp-manage-rules')){b.disabled=!state.canManage(now);b.title=b.disabled?'连接自己的推送码并读取规则后可管理本方案':b.getAttribute('aria-label');}
    status.textContent=!state.token?'公共浏览 · 连接自己的推送码后应用本方案规则':!state.data||now-state.receivedAt>=10000?(state.error||'正在同步本方案卡片规则…')+' · 暂停展示':!state.data.cardsEnabled?'本方案行情卡片已暂停':`本方案规则已接入 · 已屏蔽 ${blocked} 张${pending?' · 待校验 '+pending+' 张':''}${state.error?' · 同步重试中':''}`;
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
