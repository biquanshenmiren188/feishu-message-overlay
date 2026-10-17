// Parse only explicit source statements; an absent chain is never inferred open.
export function chainName(value) {
  const name=value.trim();
  if (/^(ERC[- ]?20|ETH|ETHEREUM(?:\s*\(ERC20\))?)$/i.test(name)) return 'ETH';
  if (/^(BSC|BEP[- ]?20|BNB(?: SMART CHAIN)?(?:\s*\(BEP20\))?)$/i.test(name)) return 'BNB';
  if (/^(TON|(?:THE )?OPEN NETWORK(?:\s*\(TON\))?)$/i.test(name)) return 'TON';
  if (/^BASE$/i.test(name)) return 'BASE';
  return name;
}
export function periodWarning(legs) {
  if(legs?.length!==2 || legs.some(l=>l.spot!==false || !Number.isFinite(l.hours) || l.hours<=0))return null;
  return legs[0].hours!==legs[1].hours?`周期 ${legs[0].hours}h/${legs[1].hours}h`:null;
}
export function strategyCopy(data) {
  const legs=data.details?.legs || [], [buy,sell]=legs;
  const allowed=new Set(['binance','bitget','bybit','gate','okx','aster','hyperliquid']);
  if(!buy || !sell || !['SF','FS','FF'].includes(data.strategy) || !allowed.has(buy.exchange) || !allowed.has(sell.exchange)) return null;
  if(data.strategy==='FS' && ['aster','hyperliquid'].includes(sell.exchange))return null;
  if(Boolean(buy.spot)!==(data.strategy==='SF') || Boolean(sell.spot)!==(data.strategy==='FS'))return null;
  const symbol=leg=>{
    const raw=String(leg.symbol || '').toUpperCase();
    const pair=leg.exchange==='okx' && leg.spot===false && /^[\p{L}\p{Nd}]+-USDT-SWAP$/u.test(raw)?raw.slice(0,-5):raw;
    const normalized=pair.replace(/[_/\-]/g,'');
    return leg.exchange==='hyperliquid' && leg.spot===false && /^[\p{L}\p{Nd}]+$/u.test(normalized) && !normalized.endsWith('USDT')?normalized+'USDT':normalized;
  };
  const a=symbol(buy), b=symbol(sell);
  if(a!==b || !/^[\p{L}\p{Nd}]+USDT$/u.test(a))return null;
  return 'ASTRO-QUICK-COPY:\n'+JSON.stringify({type:data.strategy,name:a.slice(0,-4),buyEx:buy.exchange==='hyperliquid'?'hl':buy.exchange,sellEx:sell.exchange==='hyperliquid'?'hl':sell.exchange,...(data.strategy==='FS'?{spotMarginType:'cross'}:{})},null,2);
}

// Confirmed against the source trader GC button and its actual clipboard sample.
// Mixed pairs convert only supported legs; unsupported ordinary venues stay ordinary.
export function gcStrategyCopy(data) {
  const legs=data.details?.legs;
  const supported=new Set(['binance','bybit','gate','okx','hyperliquid']);
  if(!['SF','FS','FF'].includes(data.strategy) || legs?.length!==2 || legs.some(l=>typeof l.spot!=='boolean') || data.strategy==='SF'&&legs[0].exchange==='hyperliquid')return null;
  // FS keeps its borrowing spot leg ordinary; only the futures buy leg can use GC.
  const buyGc=supported.has(legs[0].exchange),sellGc=data.strategy!=='FS'&&supported.has(legs[1].exchange);
  if(!buyGc&&!sellGc)return null;
  const normal=strategyCopy(data);if(!normal)return null;
  const payload=JSON.parse(normal.slice(normal.indexOf('\n')+1));
  if(buyGc)payload.buyEx='gc-'+payload.buyEx;
  if(sellGc)payload.sellEx='gc-'+payload.sellEx;
  return 'ASTRO-QUICK-COPY:\n'+JSON.stringify(payload,null,2);
}

export function fundingWarnings(legs, news=[]) {
 const warnings=(Array.isArray(news)?news:[]).filter(w=>w && typeof w.summary==='string' && w.summary.trim()).map(w=>{
  const exchange=typeof w.exchange==='string'?w.exchange.toUpperCase():'';
  const status=w.status==='postponed'?'（已延期，时间未定）':w.status==='uncertain'?'（待确认）':'';
  const date=Date.parse(w.deadline);
  const deadline=Number.isFinite(date)?' · '+new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(date))+' UTC+8':'';
  return `${exchange} ${w.summary}${status}${deadline}`.trim();
 });
 const period=periodWarning(legs); if(period)warnings.push(period);
 if(legs?.some(l=>l.spot===false && String(l.exchange).toLowerCase()==='bybit' && l.hours===1)) warnings.push('Bybit 1h 计算不同');
 return warnings;
}

// Same residual-level thresholds as the source trader cards.
export function residualTone(level) {
 if(!Number.isFinite(level)||level<2)return 'grey';
 if(level<4)return 'blue';
 if(level<6)return 'yellow';
 if(level<10)return 'orange';
 return 'red';
}

export function gcBothLegs(data){const text=gcStrategyCopy(data);if(!text)return false;const p=JSON.parse(text.slice(text.indexOf('\n')+1));return p.buyEx.startsWith('gc-')&&p.sellEx.startsWith('gc-');}
