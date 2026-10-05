import {chainName} from './basispulse-card-model.js?v=20261005base1';
export function transferCoin(leg) {
  const symbol=String(leg?.symbol || '').toUpperCase();
  return /^([\p{L}\p{N}_]{1,40})(?:\/|_)?USDT$/u.exec(symbol)?.[1]?.replace(/_$/,'') || null;
}
export function walletStates(wallet, key, now) {
  const states=new Map(), checked=Date.parse(wallet?.checkedAt), expires=Date.parse(wallet?.expiresAt);
  if(!wallet || wallet.key!==key || wallet.refreshFailed!==false || !Number.isFinite(checked)
    || checked>now+30000 || now-checked>120000 || !Number.isFinite(expires) || expires<=now)return states;
  const text=String(wallet.text || '');
  // Accept a known attribution and complete explicit status clauses only.
  if(!/【(?:官方|官方名单|Cexorer补充)[｜|]/.test(text))return states;
  const body=text.split('】：')[1];if(!body)return states;
  const values={开:'open',关:'closed',支持:'supported',延迟:'delayed',拥堵:'congested',受限:'restricted',未知:'unknown','?':'unknown'};
  for(const clause of body.split(/[；;\n]/)) {
    const m=/^\s*充(开|关|支持|延迟|拥堵|受限|未知|\?)\/提(开|关|支持|延迟|拥堵|受限|未知|\?)\s+([^：:；;]+)\s*$/.exec(clause);
    if(!m)continue;
    // Commas delimit explicit network lists; do not split multiword names.
    for(const raw of m[3].split(/[,，、]/)) {
      const name=chainName(raw);if(!name || name.length>80)continue;
      const pair=[values[m[1]],values[m[2]]],old=states.get(name);
      states.set(name,old?pair.map((v,i)=>v===old[i]?v:'unknown'):pair);
    }
  }
  return states;
}
export function radarMatrix(legs, lookup, now=Date.now(), wallets=[]) {
  const chains=[], descriptions=[];
  const rows=legs.map(leg=>{
    const coin=transferCoin(leg), result=coin?lookup(coin):null;
    const data=result?.items?.find(x=>x.exchange===leg.exchange && x.coin===coin);
    const fresh=!!data&&!data.error&&Number.isFinite(data.checkedAt)&&now-data.checkedAt<=120000&&data.checkedAt<=now+30000;
    // Source catalog evidence is explicit, coin-scoped and time-bounded.
    // An empty radar response alone never means that spot is unavailable.
    const wallet=wallets.find(w=>w.key===`${leg.exchange}:${coin}`);
    const checked=Date.parse(wallet?.checkedAt), expires=Date.parse(wallet?.expiresAt);
    const noSpot=!leg.spot && !!wallet && wallet.refreshFailed===false
      && Number.isFinite(checked) && checked<=now+30000 && Number.isFinite(expires) && expires>now
      && expires-checked<=7200001 && /[｜|]无现货[｜|】]/.test(wallet.text || '')
      && /该平台无现货/.test(wallet.text || '') && !(fresh && data.chains?.length);
    const states=new Map(), blocked=new Map(), supplements=new Map();
    for(const c of data?.chains || []) {
      // Match the radar's retired Binance Beacon-chain exclusion.
      if(leg.exchange==='binance'&&['BNB','BEP2','BNBBEACONCHAIN','BNBBEACONCHAINBEP2'].includes(String(c.chain).toUpperCase().replace(/[\s_()-]/g,'')))continue;
      const name=c.network==='eip155:56'?'BNB':c.network==='eip155:1'?'ETH':chainName(c.chain);
      const pair=['deposit','withdraw'].map(side=>{
        const evidence=c[side+'Evidence'];
        if(!fresh||c[side+'Hidden']||evidence&&(!Number.isFinite(evidence.at)||now-evidence.at>120000||evidence.at>now+30000))return 'unknown';
        return ({'可用':'open','暂停':'closed','不支持':'closed','支持':'supported','延迟':'delayed','拥堵':'congested','受限':'restricted'})[c[side]] || 'unknown';
      });
      const previousBlock=blocked.get(name)||[false,false];
      blocked.set(name,['deposit','withdraw'].map((side,i)=>previousBlock[i]||!!c[side+'Hidden']));
      const old=states.get(name);if(old)blocked.set(name,pair.map((s,i)=>blocked.get(name)[i]||s!==old[i]));states.set(name,old?pair.map((s,i)=>s===old[i]?s:'unknown'):pair);
      if(!chains.includes(name))chains.push(name);
    }
    if(!noSpot)for(const [name,pair] of walletStates(wallet,`${leg.exchange}:${coin}`,now)) {
      if(leg.exchange==='binance'&&name==='BNB'&&/充[^；]+ BNB(?:；|$)/.test(wallet.text))continue;
      const current=states.get(name)||['unknown','unknown'], denied=blocked.get(name)||[];
      const used=pair.map((value,i)=>current[i]==='unknown'&&!denied[i]&&value!=='unknown');
      states.set(name,current.map((value,i)=>used[i]?pair[i]:value));
      if(used.some(Boolean))supplements.set(name,used);
      if(!chains.includes(name))chains.push(name);
    }
    const at=value=>Number.isFinite(value)?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未提供';
    const source=side=>side?.source==='official'?'官方':side?.source==='cexorer'?'Cexorer补充':'雷达公开源';
    descriptions.push(`${String(leg.exchange).toUpperCase()} ${coin || leg.symbol}\n`+(data?
      `查询时间：${at(data.checkedAt)} · UTC+8\n${fresh?'':'状态已过期或查询失败，当前按未知显示\n'}${data.warning || ''}\n`+
      (data.chains?.length?data.chains.map(c=>`${c.chain}：充 ${c.deposit} / 提 ${c.withdraw}\n  充值来源：${source(c.depositEvidence)} · ${at(c.depositEvidence?.at ?? data.checkedAt)}\n  提现来源：${source(c.withdrawEvidence)} · ${at(c.withdrawEvidence?.at ?? data.checkedAt)}`).join('\n'):'未取得分链状态，当前显示未知')+
      `\n来源页面：${data.sourceUrl || '未提供'}`:'雷达充提数据正在查询，失败后自动重试'));
    return {exchange:String(leg.exchange).toUpperCase(),noSpot,states,supplements,supplementAt:checked};
  });
  if(!chains.length)chains.push('状态');
  return {text:'数据来源：资金费雷达 /api/transfers/query\n\n'+descriptions.join('\n\n'),chains,rows:rows.map(r=>({...r,cells:chains.map(c=>r.noSpot?['none','none']:(r.states.get(c)||['unknown','unknown']))}))};
}
export function createRadarTransfers(onChange, fetcher=fetch, clock=Date.now) {
  const entries=new Map();let running=false;
  return {
    get:coin=>entries.get(coin)?.data,
    async refresh(legs) {
      if(running||document.hidden)return;
      running=true;
      const coins=[...new Set(legs.map(transferCoin).filter(Boolean))];
      for(const coin of entries.keys())if(!coins.includes(coin))entries.delete(coin);
      try {
        // Bound concurrency; repeated cards share a single coin query.
        let index=0;
        await Promise.all([0,1].map(async()=>{while(index<coins.length){
          const coin=coins[index++], old=entries.get(coin);
          if(old&&clock()<old.next)continue;
          const entry=old || {data:null,failures:0,next:0};entries.set(coin,entry);
          try {
            const r=await fetcher('/api/transfers/query?coin='+encodeURIComponent(coin),{credentials:'same-origin',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(15000)});
            if(!r.ok)throw Error('transfer');const data=await r.json();
            if(data.coin!==coin||!Array.isArray(data.items)||!Array.isArray(data.pending))throw Error('schema');
            entry.data=data;entry.failures=0;entry.next=clock()+(data.pending.length?1000:5000);
          }catch{entry.failures++;entry.next=clock()+Math.min(30000,5000*2**Math.min(3,entry.failures-1));}
          onChange();
        }}));
      }finally{running=false;}
    }
  };
}
