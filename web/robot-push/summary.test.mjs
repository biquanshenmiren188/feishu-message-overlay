import test from 'node:test';
import assert from 'node:assert/strict';
import {mobileSummary} from './summary.mjs';
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
