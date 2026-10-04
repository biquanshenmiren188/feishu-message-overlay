import test from 'node:test';
import assert from 'node:assert/strict';
import {mobileSummary} from './summary.mjs';
test('extracts only observed fields, with direction and exchange fee context',()=>{
 const x=mobileSummary({body:'买 OKX 永续 → 卖 Bybit 永续\n均值：净收益+0.29% | 盘口差+0.505% | 资金费差+0.015%\nOKX: 资费+0.338%/4h | 市值\nBybit: 资费+0.001%/1h\nOKX：充开提开\nBybit：充开提开'});
 assert.equal(x.direction,'买 OKX 永续 → 卖 Bybit 永续');assert.match(x.metrics,/净收益\+0.29%/);assert.match(x.metrics,/盘口差\+0.505%/);assert.match(x.fees,/OKX:\s*\+0.338%\/4h/);assert.equal(x.risk,'充提：充开提开');assert.equal(x.warning,false);
});
test('closed/unsupported/unknown and warnings override any open state',()=>{
 for(const warning of ['关闭','不支持','未知','暂无数据','风险','暂停','⚠']){const x=mobileSummary({body:'充开提开\n'+warning});assert.equal(x.warning,true);assert.match(x.risk,/注意/);assert.ok(!x.risk.includes('充开提开'));}
});
test('unknown types expose original prefix without invented yield or status',()=>{const x=mobileSummary({body:'系统自定义提醒\n不要自动交易\n检查原文\nmore'});assert.equal(x.preview,'系统自定义提醒 / 不要自动交易 / 检查原文');assert.equal(x.metrics,'');assert.equal(x.fees,'');assert.match(x.risk,/未提供/);});
test('empty and malformed fields never manufacture numbers',()=>{const x=mobileSummary({body:'净收益未知\n资金费率不可用'});assert.equal(x.metrics,'');assert.equal(x.fees,'');assert.equal(x.warning,true);});
