// Deterministic presentation only. No model, external requests or invented market fields.
export function mobileSummary(message) {
  const lines=String(message.body??'').split(/\r\n|\r|\n/).map(s=>s.trim()).filter(Boolean);
  const direction=lines.find(s=>/^(买|买入|做多).*(→|->|卖|做空)/u.test(s))??'';
  const fields=[];
  for(const label of ['净收益','盘口差','资金费差']) {
    const found=lines.flatMap(s=>[...s.matchAll(new RegExp(label+'\\s*[:：]?\\s*[+−-]?\\d+(?:\\.\\d+)?\\s*%','gu'))]).map(m=>m[0]);
    if(found[0])fields.push(found[0]);
  }
  const fees=lines.filter(s=>/资费|资金费率/u.test(s)).map(s=>{
    const m=s.match(/^(.*?)(?:资费|资金费率)\s*[:：]?\s*([+−-]?\d+(?:\.\d+)?%\s*(?:\/\s*\d+h)?)/u);
    return m?m[1].trim()+m[2]:null;
  }).filter(Boolean).slice(0,2);
  const text=lines.join('\n');
  const warningKinds=[...new Set(text.match(/不支持|未知|未核验|待核验|不可用|无数据|暂无|不确定|关闭|充关|提关|暂停|维护|延迟|失败|异常|风险|警告|警示|过期|禁止|不保证|勿|谨慎|⚠/gu)??[])];
  const transfer=lines.filter(s=>/充开|提开|充关|提关|充值|提现|充提/u.test(s));
  const states=[...new Set(transfer.flatMap(s=>s.match(/充开提开|充关提关|充开|提开|充关|提关|充值开放|提现开放|充值关闭|提现关闭/gu)??[]))];
  // Any negative/unknown statement wins over open states; never hide it behind a green badge.
  const risk=warningKinds.length?'注意：'+warningKinds.join(' / '):states.length?'充提：'+states.join(' / '):'充提状态未提供，需看原文核对';
  return {direction,metrics:fields.slice(0,2).join(' · '),fees:fees.length?'资费 '+fees.join(' · '):'',risk,warning:warningKinds.length>0||states.length===0,
    preview:direction||fields.length?'':lines.slice(0,3).join(' / ')};
}
