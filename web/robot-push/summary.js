// Deterministic presentation only. No model, external requests or invented market fields.
export function mobileSummary(message) {
  const lines=String(message.body??'').split(/\r\n|\r|\n/).map(s=>s.trim()).filter(Boolean);
  const direction=lines.find(s=>/^(买|买入|做多).*(→|->|卖|做空)/u.test(s))??'';
  const route=direction.match(/^(?:买入|买|做多)\s+(\S+).*?(?:→|➡️?|->)\s*(?:卖出|卖|做空)\s+(\S+)/u);
  const exchanges={gate:'GT','gate.io':'GT',binance:'BN',bitget:'BG',bybit:'BY',okx:'OK',aster:'AS',hyperliquid:'HY',hl:'HY',hy:'HY'};
  const abbreviation=name=>exchanges[name.toLowerCase()]??name;
  const shortExchanges=text=>text.replace(/\b(?:gate\.io|gate|binance|bitget|bybit|okx|aster|hyperliquid|hl|hy)\b/giu,abbreviation);
  let title=String(message.title??'').replace(/V2\s*收敛/iu,match=>route?abbreviation(route[1])+'→'+abbreviation(route[2]):match);
  const signals=[];
  let dexSpread='';
  // DEX monitor messages put their instruments in numbered body entries, not
  // the message title. Parse those entries only; config blacklists are not coins.
  const dex=[];
  for(const [index,line] of lines.entries()){
    const entry=line.match(/^\d+[.、)]\s*\[(P\d+\+?)\]\s*\[(期期|现期|期现|FF|SF|FS)\]\s*([^\s|｜]+)\s*[|｜]\s*多\s+(\S+)\s*[/／]\s*空\s+(\S+)\s*$/iu);
    if(entry)dex.push({index,rank:entry[1].toUpperCase(),mode:({期期:'FF',现期:'SF',期现:'FS'})[entry[2]]??entry[2].toUpperCase(),coin:entry[3],route:abbreviation(entry[4])+'→'+abbreviation(entry[5])});
  }
  if(dex.length){
    title=dex.length===1?`${dex[0].coin}｜${dex[0].mode}｜${dex[0].route}｜${dex[0].rank}`:`DEX套利｜${[...new Set(dex.map(x=>x.coin))].join('、')}｜${dex.length}组`;
    dex.forEach((entry,i)=>{
      const block=lines.slice(entry.index+1,dex[i+1]?.index??lines.length);
      // The first take percentage is the observed opening order-book spread;
      // the second is the reverse quote. Do not use funding or the 30m mean.
      const take=block.map(s=>s.match(/^take\s*[:：]\s*([+−-]?\d+(?:\.\d+)?\s*%)\s*\/\s*[+−-]?\d+(?:\.\d+)?\s*%/iu)?.[1]).find(Boolean);
      const observed=take??block.map(s=>s.match(/(?:^|[｜|])\s*盘口差\s*[:：]?\s*([+−-]?\d+(?:\.\d+)?\s*%)/u)?.[1]).find(Boolean);
      const spread=observed?'盘口差 '+(/^[+−-]/u.test(observed)?'':'+')+observed.replace(/\s/gu,''):'';
      if(dex.length===1)dexSpread=spread;
      const quality=block.map(s=>s.match(/^质量\s*[:：]\s*(.+)$/u)?.[1]).find(Boolean);
      const details=[dex.length>1?`${entry.coin}｜${entry.mode}｜${entry.route}｜${entry.rank}`:'',dex.length>1?spread:'',quality?'质量：'+quality:''].filter(Boolean);
      if(details.length)signals.push(details.join(' · '));
    });
  }else if(!title.trim()||/^机器人消息$/u.test(title.trim())){
    title=lines.find(s=>!/^https?:\/\//iu.test(s)&&!(/^(?:时间|阈值|价格最大延迟|symbol黑名单|排除合约交易所)\s*[:：]/iu.test(s)))??'';
  }
  if(/强信号/u.test(title)){
    for(const [index,line] of lines.entries()){
      const signal=line.match(/^(R\d+\+?)\s*[｜|]\s*(SF|FS|FF)\s*[｜|]\s*买\s+(\S+)\s*→\s*卖\s+(\S+)/iu);
      if(!signal)continue;
      const next=lines[index+1]??'';
      const value=(line+'\n'+(/^净均/u.test(next)?next:'')).match(/净均\s*([+−-]?\d+(?:\.\d+)?%)/u)?.[1];
      signals.push(`${signal[1]}｜${signal[2]}｜${abbreviation(signal[3])}→${abbreviation(signal[4])}${value?'｜'+value:''}`);
    }
    if(signals.length){
      const count=title.match(/(\d+)\s*组/u)?.[1]??signals.length;
      title=title.replace(/^[🚨\s]+/u,'').replace('强信号聚集','强信号').split(/[｜|]/u).slice(0,2).map(s=>s.trim()).join('｜')+'｜'+count+'组';
    }
  }
  title=shortExchanges(title);
  const fields=[];
  for(const label of ['净收益','盘口差','资金费差']) {
    const found=lines.flatMap(s=>[...s.matchAll(new RegExp(label+'\\s*[:：]?\\s*[+−-]?\\d+(?:\\.\\d+)?\\s*%','gu'))]).map(m=>m[0]);
    if(found[0])fields.push(found[0]);
  }
  const fees=lines.filter(s=>/资费|资金费率/u.test(s)).map(s=>{
    const m=s.match(/^(.*?)(?:资费|资金费率)\s*[:：]?\s*([+−-]?\d+(?:\.\d+)?%\s*(?:\/\s*\d+h)?)/u);
    return m?m[1].trim()+m[2]:null;
  }).filter(Boolean).slice(0,2);
  // Keep the observed warning sentence, including instrument and effective time.
  // Missing-data placeholders and sampling statistics are not actionable alerts.
  const placeholder=/^(?:(?:无|没有|暂无)(?:数据|信息|风险|警告|警示|提醒)?|未知|未提供|不适用|无数据|未核验|待核验|不确定|[-—/|·.,，。:：;；\s])+$/u;
  const warningLabel=/^(?:[⚠\uFE0F\s]*(?:警告|警示|注意|风险提示|风险|提醒)\s*[:：]?\s*|[⚠\uFE0F\s]+)/u;
  const actionable=/下架|退市|停止交易|终止|暂停|维护|充关|提关|充值关闭|提现关闭|关闭|延迟|失败|异常|过期|禁止|不支持|不可用|不保证|勿|谨慎/iu;
  const warnings=[];let hasWarningLabel=false;
  for(const [index,line] of lines.entries()){
    // A configured maximum age is not evidence that a price is delayed.
    if(/^价格最大延迟\s*[:：]\s*\d+(?:\.\d+)?\s*(?:s|秒)\s*$/iu.test(line))continue;
    const labelled=warningLabel.test(line);
    let detail=line.replace(warningLabel,'').replace(/官方原文\s*[:：].*$/u,'').trim();
    if(!detail||placeholder.test(detail))continue;
    if(!labelled&&!actionable.test(detail))continue;
    if(/^[⚠\uFE0F\s]*(?:警告|警示)/u.test(line))hasWarningLabel=true;
    const continuation=lines[index+1]??'';
    if(/\d{1,2}[/-]\d{1,2}$/u.test(detail)&&/^\d{1,2}:\d{2}(?::\d{2})?\s*UTC\s*[+-]\d+(?::\d{2})?$/u.test(continuation))detail+=' '+continuation;
    // Retain exchange and actual status, omit the long lookup metadata.
    detail=shortExchanges(detail.replace(/【[^】]*】/gu,'').trim());
    if(detail&&!warnings.includes(detail))warnings.push(detail);
  }
  const transfer=lines.filter(s=>/充开|提开|充关|提关|充值|提现|充提/u.test(s));
  const states=[...new Set(transfer.flatMap(s=>s.match(/充开提开|充关提关|充开|提开|充关|提关|充值开放|提现开放|充值关闭|提现关闭/gu)??[]))];
  // Incomplete transfer data must not become a misleading all-open summary.
  const incomplete=transfer.some(s=>/未知|暂无|没有|无数据|未提供|无现货|未核验|待核验|不确定/u.test(s));
  const risk=warnings.length?(hasWarningLabel?'警告：':'注意：')+warnings.join('；'):states.length&&!incomplete?'充提：'+states.join(' / '):'';
  const spread=dex.length?dexSpread:(fields.find(s=>s.startsWith('盘口差'))??'').replace(/^盘口差\s*[:：]?\s*/u,'盘口差 ');
  return {title,signals:signals.join('\n'),spread,direction,metrics:fields.slice(0,2).join(' · '),fees:fees.length?'资费 '+fees.join(' · '):'',risk,warning:warnings.length>0,
    preview:direction||fields.length?'':lines.slice(0,3).join(' / ')};
}
