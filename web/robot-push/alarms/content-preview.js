import {DEFAULT_TEMPLATE} from './content-template.js?v=20261114-template1';

const lines=[['行情来源','{{行情来源}}'],['触发价格','触发价格：{{触发价格}} USDT'],['触发原因','{{触发原因}}'],['时间','{{时间}}（北京时间）']];
const fields=new Set([...lines.map(([name])=>name),'备注','币种','触发条件']);
const tokens=/\{\{([^{}]+)\}\}/g;
const names={above:'涨到',below:'跌到',enter:'进入区间',exit:'离开区间'};

// Keep the same one-pass substitution and missing-field policy as alarms/content.py.
export function renderPreviewBody(text,rule,values){
  let template=text.trim()||DEFAULT_TEMPLATE+(rule.note?'\n{{备注}}':'');
  const present=new Set([...template.matchAll(tokens)].map(m=>m[1]));
  const unknown=[...present].filter(name=>!fields.has(name));
  if(unknown.length)throw Error('无法识别内容字段：'+unknown.sort().join('、'));
  const missing=lines.filter(([name])=>!present.has(name)).map(([,line])=>line);
  if(rule.note&&!present.has('备注'))missing.push('{{备注}}');
  if(missing.length)template+='\n\n'+missing.join('\n');
  return template.replace(tokens,(_,name)=>String(values[name]));
}

function sourceLabel(source){
  let text=(source.fallback?'备用行情：':'')+source.exchange.toUpperCase()+' · '+(source.market==='spot'?'现货':'永续')+' · '+source.symbol+' · '+(source.priceType==='last'?'最新成交价':'标记价格');
  if(source.conversionFactor&&source.conversionFactor!=='1')text+=`（×${source.conversionFactor}，按 ${source.targetUnit} 报价）`;
  return text;
}

export function previewContext(rule,{fresh=false,now=Date.now()}={}){
  const state=rule.state||{};
  const live=fresh&&state.source&&Number.isFinite(Number(state.price))&&Number(state.price)>0;
  const source=live?state.source:{exchange:rule.exchange,market:rule.market,symbol:rule.symbol,priceType:rule.priceType,fallback:false};
  const pair=state.asset?.pair||rule.symbol;
  const condition=names[rule.condition]+' '+rule.target+(rule.upper?'～'+rule.upper:'');
  const time=new Date(now+8*3600000).toISOString().slice(5,19).replace('T',' ');
  return {
    title:pair+' '+condition,
    caption:live?'按当前行情预览，实际以触发时为准 · 不会发送':'当前行情不可用，按设定价示例 · 不会发送',
    values:{'行情来源':sourceLabel(source),'触发价格':live?state.price:rule.target,
      '触发原因':rule.repeat&&state.status==='alarming'?'价格仍满足条件，每 30 秒提醒':'价格穿越',
      '时间':time,'备注':rule.note||'','币种':pair,'触发条件':condition}
  };
}
