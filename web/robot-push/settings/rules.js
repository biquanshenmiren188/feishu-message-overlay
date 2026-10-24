(function(root){
  const exchanges=[['binance','Binance','币安'],['okx','OKX','欧易'],['bybit','Bybit',''],['bitget','Bitget',''],['gate','Gate',''],['aster','Aster',''],['hyperliquid','Hyperliquid','']];
  const name=id=>(exchanges.find(e=>e[0]===id)||[id,id])[1];
  const sideName=s=>({all:'任意一侧',left:'左腿（买入）',right:'右腿（卖出）'})[s];
  const marketName=s=>({all:'现货和永续',spot:'现货',perp:'永续'})[s];
  const defaults=()=>({version:1,desktopAction:"hide",enabled:true,coins:[],blockedExchanges:[],legRules:[],globalOI:null,exchangeOI:{},coinOI:[],missing:'block',rows:4,interval:60,rPercent:null,ranks:[],modes:[]});
  const resetFilters=s=>({...s,enabled:true,coins:[],blockedExchanges:[],legRules:[],globalOI:null,exchangeOI:{},coinOI:[],missing:'block',rPercent:null,ranks:[],modes:[]});
  const coin=s=>String(s||'').trim().toUpperCase();
  function threshold(s,c,e){const special=s.coinOI.find(r=>r.enabled&&r.coin===coin(c)&&r.exchange===e);if(special)return {value:special.value,source:'币种特殊门槛'};const ex=s.exchangeOI[e];if(ex&&ex.mode!=='inherit')return {value:ex.mode==='none'?null:ex.value,source:'交易所门槛'};return {value:s.globalOI,source:'统一门槛'};}
  function evaluate(s,sample){
    const reasons=[];if(!s.enabled)reasons.push('接收消息已关闭');
    const c=coin(sample.coin);const legs=[{...sample.left,side:'left'},{...sample.right,side:'right'}];
    for(const r of s.coins.filter(r=>r.enabled&&r.coin===c)){if(r.exchange==='all'||legs.some(l=>l.exchange===r.exchange))reasons.push(`${c} 已屏蔽${r.exchange==='all'?'（全部交易所）':'（'+name(r.exchange)+'）'}`);}
    for(const l of legs){const title=`${name(l.exchange)} ${sideName(l.side)}`;
      if(s.blockedExchanges.includes(l.exchange))reasons.push(`${name(l.exchange)} 已整所屏蔽`);
      for(const r of s.legRules.filter(r=>r.enabled)){if(r.exchange===l.exchange&&(r.side==='all'||r.side===l.side)&&(r.market==='all'||r.market===l.market))reasons.push(`${title} · ${marketName(l.market)} 命中定向屏蔽`);}
      if(l.market==='perp'){const t=threshold(s,c,l.exchange);if(t.value!==null){if(l.oi===null||!Number.isFinite(l.oi)||l.stale){if(s.missing==='block')reasons.push(`${title} OI 缺失或过期，暂不推送`);}else if(l.oi<t.value)reasons.push(`${title} OI ${l.oi} 万 < ${t.value} 万 USDT（${t.source}）`);}}
    }
    const mode=sample.left.market==='spot'?(sample.right.market==='perp'?'SF':'SS'):(sample.right.market==='spot'?'FS':'FF');
    if(mode==='SS')return {allowed:false,reasons:['当前样例为现货／现货，不属于 SF、FS、FF 机会'],mode};
    if(s.modes.includes(mode))reasons.push(`${mode} 类型已屏蔽`);
    const rank=String(sample.rank||'').toUpperCase();if(s.ranks.some(r=>r===rank||(!r.endsWith('+')&&r+'+'===rank)))reasons.push(`${rank} 等级已屏蔽`);
    if(s.rPercent!==null&&Number.isFinite(sample.percent)&&sample.percent<s.rPercent)reasons.push(`R 百分比 ${sample.percent}% < ${s.rPercent}%`);
    return {allowed:reasons.length===0,reasons:[...new Set(reasons)],mode};
  }
  const api={exchanges,name,sideName,marketName,defaults,resetFilters,coin,threshold,evaluate};root.RadarRules=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
