export function demoData(now=Date.now()){
 const make=(n,groupId='demo-normal')=>({id:'fictional-'+n,groupId,senderType:'bot',sentAt:new Date(now-n*60000).toISOString(),title:['示例机会 · SF · 收敛观察','示例机会 · FF · 指标变化','示例通知 · 盘口监控'][n%3],body:'以下为虚构数据，用于检查网页布局。\n买 示例交易所A → 卖 示例交易所B\n均值：净收益0.32% | 盘口差+0.45% | 指数差-0.01%\n盘口差P75：+0.51%\n持续 ACTIVE 满10分钟 | 补充推送\n示例交易所A：资费+0.01%/4h | 24h成交额2.5m | OI1.2m\n现货充提（Cexorer）：示例详情完整保留\n未知说明也原样保留，不套用微信字段过滤。',actions:[{label:'查看机会',url:'https://example.invalid/radar/?combo=SF.DEMO.A.B&q=%E6%BC%94%E7%A4%BA&tab=SF'}]});
 return {messages:Array.from({length:8},(_,i)=>make(i+1)),pinned:make(0,'demo-pinned')};
}
