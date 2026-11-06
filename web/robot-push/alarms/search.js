// Exact identity matching only: never merge wrapped coins or multiplier contracts.
const normalized=value=>String(value??'').trim().toUpperCase();
export function matchesInstrument(query,item){
 const q=normalized(query);
 return !q||q===normalized(item.base)||q===normalized(item.symbol);
}
export function matchesAlarm(query,rule){
 const q=normalized(query),symbol=normalized(rule.symbol);
 const base=symbol.replace(/(?:-USDT-SWAP|[-_/]?USDT)$/,'');
 return matchesInstrument(q,{symbol,base})||q===normalized(rule.note)||q===normalized(rule.exchange);
}
