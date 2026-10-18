import test from 'node:test';
import assert from 'node:assert/strict';
import {mobileSummary} from './summary.mjs';

test('premium alert shows instrument, observed decline and endpoints instead of trigger thresholds',()=>{
 const message={title:'',body:'🟣 Bitget 溢价指数突变提醒\n本轮触发：1 条\n触发条件：达到涨跌档位线并持续 5 分钟\n二次确认：上涨需 premium>0.2000%；下跌需 premium<-0.2000%\n1. 🟢 TOKENUSDT / USDT-FUTURES | 5分钟 close持续突降 | -0.3029 个百分点 | 档位 跌幅>=0.10 个百分点 | close -0.1884% -> -0.4913% | high/low -0.1884% / -0.4913% | 二次确认 盘口确认 0.3810%'};
 const original=JSON.stringify(message),x=mobileSummary(message);
 assert.equal(x.title,'🟣 BG 溢价指数突变提醒');
 assert.equal(x.signals,'TOKENUSDT · 5分钟下跌 0.3029 个百分点\n溢价指数 -0.1884% → -0.4913%');
 assert.equal(x.spread,'');assert.equal(JSON.stringify(message),original);
});

test('premium batches preserve each instruments own signed change and source precision',()=>{
 const x=mobileSummary({title:'Bitget 溢价指数突变提醒',body:'1. 🔴 FIRSTUSDT / USDT-FUTURES | 1分钟 close持续突升 | +0.4000 个百分点 | close -0.1000% → 0.3000%\n2. 🟢 SECONDUSDT / USDT-FUTURES | 5分钟 close持续突降 | −0.2500 个百分点 | close 0.1000% -> -0.1500%\n3. ZEROUSDT / USDT-FUTURES | 1分钟 close | 0.0000 个百分点 | close 0.0000% -> 0.0000%'});
 assert.equal(x.signals,'FIRSTUSDT · 1分钟上涨 0.4000 个百分点\n溢价指数 -0.1000% → 0.3000%\nSECONDUSDT · 5分钟下跌 0.2500 个百分点\n溢价指数 0.1000% → -0.1500%\nZEROUSDT · 1分钟持平 0.0000 个百分点\n溢价指数 0.0000% → 0.0000%');
});

test('premium missing values never borrow thresholds, high-low values or another instruments data',()=>{
 const x=mobileSummary({title:'BG 溢价指数突变提醒',body:'检查窗口：1分钟, 5分钟\n1. FIRSTUSDT / USDT-FUTURES | 5分钟 close持续突降 | 未知 | 档位 跌幅>=0.10 个百分点 | high/low 0.4% / -0.4%\n2. SECONDUSDT / USDT-FUTURES | 1分钟 close持续突升 | +0.2000 个百分点'});
 assert.equal(x.signals,'FIRSTUSDT · 5分钟 close持续突降\nSECONDUSDT · 1分钟上涨 0.2000 个百分点');
 assert.equal(mobileSummary({title:'普通消息',body:'1. TOKEN / USDT-FUTURES | 5分钟 close | -0.3 个百分点'}).signals,'');
});

test('untitled DEX opportunities use the instrument, direction and original P rank',()=>{
 const message={title:'',body:'[Dex 套利监控命中][最高P3]\n价格最大延迟: 45s\nsymbol黑名单: MEME, ONE\n排除合约交易所: Bybit\n1. [P3][期期] TOKEN | 多 Binance / 空 Aster\ntake: 0.3759% / 0.4298%\n净费率: 0.0228%/h\n质量: 样本少'};
 const before=JSON.stringify(message),x=mobileSummary(message);
 assert.equal(x.title,'TOKEN｜FF｜BN→AS｜P3');assert.equal(x.signals,'质量：样本少');
 assert.equal(x.warning,false);assert.equal(x.risk,'');assert.equal(x.spread,'盘口差 +0.3759%');assert.equal(JSON.stringify(message),before);
});

test('DEX batches retain each coin, route and own spread without taking config blacklist coins',()=>{
 const x=mobileSummary({body:'[Dex 套利监控命中][最高P9]\nsymbol黑名单: BLACKLIST\n1. [P3][现期] FIRST | 多 Gate / 空 Bitget\ntake: -0.015% / +0.022%，30m +0.9%\n净费率: -0.01%/h\n质量: 样本少\n2. [P9][期现] SECOND | 多 OKX / 空 Binance\ntake: 0.32% / 0.45%\n净费率: +0.02%/h\n3. [P2][FF] THIRD | 多 Aster / 空 Bybit'});
 assert.equal(x.title,'DEX套利｜FIRST、SECOND、THIRD｜3组');
 assert.equal(x.signals,'FIRST｜SF｜GT→BG｜P3 · 盘口差 -0.015% · 质量：样本少\nSECOND｜FS｜OK→BN｜P9 · 盘口差 +0.32%\nTHIRD｜FF｜AS→BY｜P2');
 assert.ok(!x.title.includes('BLACKLIST'));
});

test('configuration maximum age is hidden but actual delay warnings remain',()=>{
 assert.equal(mobileSummary({body:'价格最大延迟: 45s'}).risk,'');
 assert.equal(mobileSummary({body:'价格最大延迟: 45s\n警告：TOKEN 价格已延迟90秒'}).risk,'警告：TOKEN 价格已延迟90秒');
 assert.equal(mobileSummary({body:'TOKEN 价格延迟，暂不可用'}).warning,true);
});

test('DEX summaries show opening spread only and never substitute a fee, reverse quote or average',()=>{
 const header='1. [P3][期期] TOKEN | 多 Binance / 空 Aster\n';
 for(const [body,expected] of [
  ['take: +0.3759% / 0.4298%，30m 0.2989% (7)\n净费率: 0.0228%/h','盘口差 +0.3759%'],
  ['take: 0.0000% / 0.1%','盘口差 +0.0000%'],
  ['take: −0.2% / 0.5%','盘口差 −0.2%'],
  ['盘口差: -0.15%\n净费率: 0.0228%/h','盘口差 -0.15%'],
  ['take: 未知 / 0.4298%，30m 0.2989% (7)\n净费率: 0.0228%/h',''],
  ['净费率: 0.0228%/h\n盘口差P75: +0.6%','']
 ]){const x=mobileSummary({body:header+body});assert.equal(x.spread,expected);assert.ok(!x.signals.includes('净费率'));}
});

test('unknown untitled messages use meaningful original context instead of a generic heading',()=>{
 assert.equal(mobileSummary({body:'系统自定义提醒\n检查原文'}).title,'系统自定义提醒');
 assert.equal(mobileSummary({title:'机器人消息',body:'TOKEN 合约即将下架\n其他细节'}).title,'TOKEN 合约即将下架');
 assert.equal(mobileSummary({body:'symbol黑名单: BLACKLIST\n价格最大延迟: 45s'}).title,'');
 assert.equal(mobileSummary({title:'正常标题',body:'普通正文'}).title,'正常标题');
});
test('extracts only observed fields, with direction and exchange fee context',()=>{
 const x=mobileSummary({body:'买 OKX 永续 → 卖 Bybit 永续\n均值：净收益+0.29% | 盘口差+0.505% | 资金费差+0.015%\nOKX: 资费+0.338%/4h | 市值\nBybit: 资费+0.001%/1h\nOKX：充开提开\nBybit：充开提开'});
 assert.equal(x.direction,'买 OKX 永续 → 卖 Bybit 永续');assert.match(x.metrics,/净收益\+0.29%/);assert.match(x.metrics,/盘口差\+0.505%/);assert.match(x.fees,/OKX:\s*\+0.338%\/4h/);assert.equal(x.risk,'充提：充开提开');assert.equal(x.warning,false);
});
test('concrete warnings override any open state',()=>{
 for(const warning of ['充值关闭','不支持该网络','暂停提现','警告：资金费计算方式不同']){const x=mobileSummary({body:'充开提开\n'+warning});assert.equal(x.warning,true);assert.match(x.risk,/注意|警告/);assert.ok(!x.risk.includes('充开提开'));}
});
test('unknown types expose original prefix without invented yield or status',()=>{const x=mobileSummary({body:'系统自定义提醒\n不要自动交易\n检查原文\nmore'});assert.equal(x.preview,'系统自定义提醒 / 不要自动交易 / 检查原文');assert.equal(x.metrics,'');assert.equal(x.fees,'');assert.equal(x.risk,'');});
test('empty and malformed fields never manufacture numbers',()=>{const x=mobileSummary({body:'净收益未知\n资金费率不可用'});assert.equal(x.metrics,'');assert.equal(x.fees,'');assert.equal(x.warning,true);});
test('EPIC delisting preserves instrument, event, date and timezone',()=>{
 const warning='BITGET EPICUSDT 将下架合约及相关服务 · 10/20 15:00 UTC+8';
 const x=mobileSummary({body:'买 Gate 现货 → 卖 Bitget 永续\n⚠ 警告：'+warning+'\n官方原文：https://www.bitget.com/en/support/articles/12560603897724\n180秒：有效179/180｜最长未知1秒\nBitget：该平台无现货，暂无充提数据'});
 assert.equal(x.risk,'警告：'+warning.replace('BITGET','BG'));assert.equal(x.warning,true);
});
test('SPACE sampling gaps and missing transfer data do not produce an alert or all-open claim',()=>{
 const x=mobileSummary({body:'买 OKX 永续 → 卖 Binance 永续\n最长未知4秒\nOKX：充开提开\nBinance：该平台无现货，暂无充提数据'});
 assert.equal(x.risk,'');assert.equal(x.warning,false);
});
test('empty warning labels and placeholder combinations are omitted',()=>{
 for(const value of ['','没有','暂无','暂无数据','暂无风险','无','未知 / 暂无','没有.暂无','⚠','警告：暂无','注意：没有']){
  const x=mobileSummary({body:value});assert.equal(x.risk,'',value);assert.equal(x.warning,false,value);
 }
});
test('marked placeholders are omitted',()=>{
 for(const value of ['没有','暂无','未知 / 暂无','没有.暂无','无风险'])assert.equal(mobileSummary({body:'⚠️ 警告：'+value}).risk,'');
});
test('unmarked delisting and transfer suspension retain full context',()=>{
 for(const value of ['BITGET EPICUSDT 将下架合约 · 10/20 15:00 UTC+8','BITGET ILY 在 BASE 网络将暂停充值 · 10/17 16:55 UTC+8'])assert.equal(mobileSummary({body:value}).risk,'注意：'+value.replace('BITGET','BG'));
});
test('deduplicates warnings while retaining independent warnings',()=>{
 assert.equal(mobileSummary({body:'警告：Bitget 将下架 EPIC\n⚠ 警告：Bitget 将下架 EPIC\n警告：Bybit 4h 成本计算不同\n注意：暂无'}).risk,'警告：BG 将下架 EPIC；BY 4h 成本计算不同');
});
test('warning lookup metadata is omitted but exchange and status remain',()=>{
 assert.equal(mobileSummary({body:'Gate【官方｜16:53:39｜有现货】：充关/提关 ETH'}).risk,'注意：GT：充关/提关 ETH');
});
test('keeps a following timestamp line when the source wraps its warning',()=>{
 assert.equal(mobileSummary({body:'⚠ 警告：BITGET EPICUSDT 将下架合约 · 10/20\n15:00 UTC+8'}).risk,'警告：BG EPICUSDT 将下架合约 · 10/20 15:00 UTC+8');
});
test('replaces V2 convergence with the observed buy-to-sell exchange route',()=>{
 assert.equal(mobileSummary({title:'EPIC｜SF｜V2收敛｜R0 +0.37%',body:'买 Gate 现货 → 卖 Bitget 永续'}).title,'EPIC｜SF｜GT→BG｜R0 +0.37%');
 for(const [buy,sell,route] of [['OKX','Binance','OK→BN'],['Bybit','Aster','BY→AS'],['Gate.io','Hyperliquid','GT→HY'],['HL','Bitget','HY→BG']])assert.equal(mobileSummary({title:'SPACE｜FF｜V2收敛｜R5+ +0.44%',body:`买 ${buy} 永续 → 卖 ${sell} 永续`}).title,`SPACE｜FF｜${route}｜R5+ +0.44%`);
});
test('strong signals retain each route and its own yield, without activity statistics',()=>{
 const x=mobileSummary({title:'🚨🚨 强信号聚集｜EPIC｜3 组同时 ACTIVE',body:'涉及4所 · 已持续0s\n最近180秒净收益均值最高 +0.28%\nR1｜SF｜买 GATE → 卖 BITGET\n净均 +0.28% · ACTIVE 1s\nR0｜FF｜买 BYBIT → 卖 BITGET\n净均 +0.17% · ACTIVE 59s\nR0｜FF｜买 BYBIT → 卖 BINANCE\n净均 +0.24% · ACTIVE 22s\n⚠ 警告：BITGET EPICUSDT 将下架合约及相关服务 · 10/20 15:00 UTC+8'});
 assert.equal(x.title,'强信号｜EPIC｜3组');
 assert.equal(x.signals,'R1｜SF｜GT→BG｜+0.28%\nR0｜FF｜BY→BG｜+0.17%\nR0｜FF｜BY→BN｜+0.24%');
 assert.equal(x.risk,'警告：BG EPICUSDT 将下架合约及相关服务 · 10/20 15:00 UTC+8');
});
test('strong signals accept inline yields and do not borrow another route yield',()=>{
 const x=mobileSummary({title:'强信号｜TOKEN',body:'R6+｜FF｜买 OKX → 卖 BINANCE 净均 -0.12% · ACTIVE 7s\nR1｜SF｜买 GATE → 卖 BITGET\nR0｜FF｜买 BYBIT → 卖 BINANCE 净均 +0.24%'});
 assert.equal(x.signals,'R6+｜FF｜OK→BN｜-0.12%\nR1｜SF｜GT→BG\nR0｜FF｜BY→BN｜+0.24%');
});
test('never invents a route for announcements or a missing buy/sell direction',()=>{
 assert.equal(mobileSummary({title:'公告风险',body:'BITGET 暂停提现'}).title,'公告风险');
 assert.equal(mobileSummary({title:'EPIC｜V2收敛',body:''}).title,'EPIC｜V2收敛');
});
test('spread row reads the observed spread without confusing yield, index or P75',()=>{
 assert.equal(mobileSummary({body:'均值：净收益0.120%｜盘口差+0.316%｜指数差-0.054%\n盘口差P75：+0.378%'}).spread,'盘口差 +0.316%');
 assert.equal(mobileSummary({body:'盘口差：-0.025%'}).spread,'盘口差 -0.025%');
 assert.equal(mobileSummary({body:'盘口差0.000%'}).spread,'盘口差 0.000%');
 for(const body of ['盘口差未知','盘口差P75：+0.378%','净收益+0.28%',''])assert.equal(mobileSummary({body}).spread,'');
});
