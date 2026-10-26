# ASTER OI 筛选误屏蔽修复

## 根因与最终行为

2026-10-26 BULLA 的 ASTER→BINANCE、ASTER→GATE 卡片在币种设置正常、OI 门槛 50 万 USDT 时被隐藏。真实屏蔽记录为「aster 左腿 OI 缺失或过期」。统一 OI reader 对所有交易所请求 `127.0.0.1:8787/api/open-interest`，但该 relay 只支持 Binance、Bybit、Bitget、OKX、Gate；ASTER 请求返回 400 后变成空数据。

主站早已有独立 market-stats 服务，`127.0.0.1:8792/api/market-stats` 的 `asterOI` 存放官方批量持仓标准化结果。此次让共享 reader 的 ASTER 分支直接读取它。已有五家交易所路线保持；电脑消息、网页/桌面卡片、手机筛选共用修复。无需更改用户规则或升级客户端。

不从卡片显示数字反推筛选值。主站定义为 `double-v1` 双边 USDT；官网批量字段已按该口径，直接沿用，不再次乘 2。保留缓存的 `time`、`timeBasis: observed`、`sourceTime: null`，不以读取时间给旧数据续期。无数据、过期、错误口径、错误币对仍按既有缺失策略；真实零按零判断。

官方来源为 [Aster 官网批量市场数据](https://www.asterdex.com/bapi/future/v1/public/future/aster/ticker/pair)。既有来源定义及解析见 funding-radar 仓库 `docs/MARKET-STATS.md`、`lib/market-stats.ts`。没有重新引入逐币 V3 openInterest 轮询；该接口的源时间曾在部分币种上长期不更新。

同类检查：Binance/Bybit/Bitget/OKX/Gate 均成功返回新鲜标准化数据。Hyperliquid 的 relay 请求也为 400，但其原生计价/身份需独立处理，本次不擅自改成 USDT 或放行缺失值。

## 验证与发布

- Python 后端全套 102 项通过（含新增 7 项 ASTER 来源、金额、过期、失败恢复、精确币对和其他交易所回归）。
- 生产候选使用原服务器代码副本、替换单个 reader，再运行上述检查和真实缓存的隔离 BULLA 双组合判定；不调用发送通知，不写真实规则。
- 仅发布 `advanced_rules.py`，部署脚本 `scripts/deploy-aster-oi.py` 在 guard.lock 内验证旧/新哈希并备份；只重启 `radar-webpush-test`。静态 current、PWA、客户端、其他服务保持。
- 发布前后校验各码规则、绑定和配置摘要；失败仅回滚代码，不回滚用户数据。部署记录保存在服务端备份目录的 result.json。

实际部署源码 `76f21cad03324c12ee24bb54f8d769d149b89ae6`，安装文件 SHA256 `dec3312fff2f2d0f728b6720a4a91c069a81871035931a1813040f8283a09776`。

回滚备份 `/opt/funding-radar-web/backups/20261026-aster-oi-1793013039/advanced_rules.py`；仅停止 radar-webpush-test、按现有权限原子恢复该文件并启动服务、检查 health，不恢复状态数据。静态版本仍为 `20261026-empty-combination-1792994284`。发布前后各码规则/绑定摘要一致，其他运行服务 PID 一致。

服务器候选 102 项再次通过；已安装正式模块的隔离真实缓存检查确认 BULLA 两组 allow、桌面无阻挡、模拟过期 hide、恢复 fresh 后 allow。正式 Chrome 已刷新用户原 BOT 页并确认两张 BULLA 卡片回到正常列表、卡片入口显示「已屏蔽 0 张」。卡片当时仍为源站「待确认」，没有将其声称为活跃信号或可执行报价；这是行情源状态，与本次规则误屏蔽修复独立。没有发送测试通知、修改门槛或发布客户端安装包。
