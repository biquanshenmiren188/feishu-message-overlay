import {chainName} from './basispulse-card-model.js?v=20261005b';
export function transferCoin(leg) {
  const symbol=String(leg?.symbol || '').toUpperCase();
  return /^([\p{L}\p{N}_]{1,40})(?:\/|_)?USDT$/u.exec(symbol)?.[1]?.replace(/_$/,'') || null;
}
export function radarMatrix(legs, lookup, now=Date.now()) {
  const chains=[], descriptions=[];
  const rows=legs.map(leg=>{
    const coin=transferCoin(leg), result=coin?lookup(coin):null;
    const data=result?.items?.find(x=>x.exchange===leg.exchange && x.coin===coin);
    const fresh=!!data&&!data.error&&Number.isFinite(data.checkedAt)&&now-data.checkedAt<=120000&&data.checkedAt<=now+30000;
    const states=new Map();
    for(const c of data?.chains || []) {
      // Match the radar's retired Binance Beacon-chain exclusion.
      if(leg.exchange==='binance'&&['BNB','BEP2','BNBBEACONCHAIN','BNBBEACONCHAINBEP2'].includes(String(c.chain).toUpperCase().replace(/[\s_()-]/g,'')))continue;
      const name=c.network==='eip155:56'?'BNB':c.network==='eip155:1'?'ETH':chainName(c.chain);
      const pair=['deposit','withdraw'].map(side=>{
        const evidence=c[side+'Evidence'];
        if(!fresh||c[side+'Hidden']||evidence&&(!Number.isFinite(evidence.at)||now-evidence.at>120000||evidence.at>now+30000))return 'unknown';
        return ({'可用':'open','暂停':'closed','不支持':'closed','支持':'supported','延迟':'delayed','拥堵':'congested','受限':'restricted'})[c[side]] || 'unknown';
      });
      const old=states.get(name);states.set(name,old?pair.map((s,i)=>s===old[i]?s:'unknown'):pair);
      if(!chains.includes(name))chains.push(name);
    }
    const at=value=>Number.isFinite(value)?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未提供';
    const source=side=>side?.source==='official'?'官方':side?.source==='cexorer'?'Cexorer补充':'雷达公开源';
    descriptions.push(`${String(leg.exchange).toUpperCase()} ${coin || leg.symbol}\n`+(data?
      `查询时间：${at(data.checkedAt)} · UTC+8\n${fresh?'':'状态已过期或查询失败，当前按未知显示\n'}${data.warning || ''}\n`+
      (data.chains?.length?data.chains.map(c=>`${c.chain}：充 ${c.deposit} / 提 ${c.withdraw}\n  充值来源：${source(c.depositEvidence)} · ${at(c.depositEvidence?.at ?? data.checkedAt)}\n  提现来源：${source(c.withdrawEvidence)} · ${at(c.withdrawEvidence?.at ?? data.checkedAt)}`).join('\n'):'未取得分链状态，当前显示未知')+
      `\n来源页面：${data.sourceUrl || '未提供'}`:'雷达充提数据正在查询，失败后自动重试'));
    return {exchange:String(leg.exchange).toUpperCase(),noSpot:false,states};
  });
  if(!chains.length)chains.push('状态');
  return {text:'数据来源：资金费雷达 /api/transfers/query\n\n'+descriptions.join('\n\n'),chains,rows:rows.map(r=>({...r,cells:chains.map(c=>r.states.get(c)||['unknown','unknown'])}))};
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
