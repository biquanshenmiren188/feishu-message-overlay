// Parse only explicit source statements; an absent chain is never inferred open.
export function chainName(value) {
  const name=value.trim();
  if (/^(ERC[- ]?20|ETH|ETHEREUM(?:\s*\(ERC20\))?)$/i.test(name)) return 'ETH';
  if (/^(BSC|BEP[- ]?20|BNB(?: SMART CHAIN)?(?:\s*\(BEP20\))?)$/i.test(name)) return 'BNB';
  return name;
}
export function periodWarning(legs) {
  if(legs?.length!==2 || legs.some(l=>l.spot!==false || !Number.isFinite(l.hours) || l.hours<=0))return null;
  return legs[0].hours!==legs[1].hours?`周期 ${legs[0].hours}h/${legs[1].hours}h`:null;
}
export function strategyCopy(data) {
  const legs=data.details?.legs || [], [buy,sell]=legs;
  const allowed=new Set(['binance','bitget','bybit','gate','okx','aster']);
  if(!buy || !sell || !['SF','FS','FF'].includes(data.strategy) || !allowed.has(buy.exchange) || !allowed.has(sell.exchange)) return null;
  if(data.strategy==='FS' && sell.exchange==='aster')return null;
  if(Boolean(buy.spot)!==(data.strategy==='SF') || Boolean(sell.spot)!==(data.strategy==='FS'))return null;
  const a=String(buy.symbol || '').replace(/[_/\-]/g,'').toUpperCase(), b=String(sell.symbol || '').replace(/[_/\-]/g,'').toUpperCase();
  if(a!==b || !/^[A-Z0-9]+USDT$/.test(a))return null;
  return 'ASTRO-QUICK-COPY:\n'+JSON.stringify({type:data.strategy,name:a.slice(0,-4),buyEx:buy.exchange,sellEx:sell.exchange,...(data.strategy==='FS'?{spotMarginType:'cross'}:{})},null,2);
}

export function fundingWarnings(legs) {
 const warnings=[];
 const period=periodWarning(legs); if(period)warnings.push(period);
 if(legs?.some(l=>l.spot===false && String(l.exchange).toLowerCase()==='bybit' && l.hours===1)) warnings.push('Bybit 1h 计算不同');
 return warnings;
}
