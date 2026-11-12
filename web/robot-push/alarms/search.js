// Exact identity matching only: never merge wrapped coins or multiplier contracts.
const normalized=value=>String(value??'').trim().toUpperCase();
export function instrumentLabel(item){
 return item?.base&&item?.quote?`${item.base}/${item.quote}`:String(item?.symbol??'');
}
export function matchesInstrument(query,item){
 const q=normalized(query);
 return !q||q===normalized(item.base)||q===normalized(item.symbol)||q===normalized(instrumentLabel(item));
}
export function resolveInstrument(query,items){
 const q=normalized(query);
 if(!q)return null;
 const exact=items.filter(item=>q===normalized(item.symbol));
 const matches=exact.length?exact:items.filter(item=>matchesInstrument(q,item));
 return matches.length===1?matches[0]:null;
}
export function matchesAlarm(query,rule){
 const q=normalized(query),symbol=normalized(rule.symbol);
 const base=symbol.replace(/(?:-USDT-SWAP|[-_/]?USDT)$/,'');
 return matchesInstrument(q,{symbol,base:rule.state?.asset?.base||base})||q===normalized(rule.state?.asset?.pair)||q===normalized(rule.note)||q===normalized(rule.exchange);
}
