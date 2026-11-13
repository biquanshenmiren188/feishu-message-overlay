// Display cadence only: never feeds the router, thresholds or delivery scheduler.
export function createQuoteDisplay(interval=5000){
 const values=new Map();
 return {
  clear(){values.clear();},
  prune(ids){const keep=new Set(ids);for(const id of values.keys())if(!keep.has(id))values.delete(id);},
  read(rule,{fresh},now){
   const state=rule.state||{};
   const identity=JSON.stringify([rule.exchange,rule.market,rule.symbol,rule.priceType,state.asset?.pair]);
   let saved=values.get(rule.id);
   if(saved?.identity!==identity){values.delete(rule.id);saved=null;}
   const valid=state.price!=null&&Number.isFinite(Number(state.price))&&Number(state.price)>0;
   if(valid&&(!saved||fresh&&now-saved.at>=interval)){
    saved={identity,at:now,value:state.price,source:{...state.source}};values.set(rule.id,saved);
   }
   return {value:saved?.value??null,source:saved?.source??null,last:!fresh};
  }
 };
}
