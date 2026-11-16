export const FALLBACK_ORDER=['binance','okx','bybit','bitget','gate','aster'];
// An explicit empty selection means disabled, never the automatic default.
export function fallbackChoices(rule,main){
 const legacy=rule?.fallbackExchange??'auto';
 const selected=Array.isArray(rule?.fallbackExchanges)?rule.fallbackExchanges:
  legacy==='auto'?FALLBACK_ORDER.filter(v=>v!=='aster'):legacy==='off'?[]:[legacy];
 return FALLBACK_ORDER.filter(v=>v!==main&&selected.includes(v));
}
