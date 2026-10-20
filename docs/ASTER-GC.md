# Aster 合约 GC 复制（2026-10-20）

桌面与 BOT 卡片的复制 GC 新增 `gc-aster`，只转换 Aster 合约，不能转换其现货。

FF 支持 Aster 位于任意一侧；SF 仅卖出的 Aster 合约转换，买入 Aster 现货保持普通平台；FS 买入 Aster 合约转换，借币现货腿保持普通平台和 `spotMarginType: cross`。不放开 Aster 现货借币卖出。绿色按钮依据最终双 GC 载荷判断。

验证：135 项 BOT 测试，420 项核心检查，桌面 WPF 真实复制按钮/剪贴板及 GC 边框契约通过，覆盖中文、倍率、买卖方向和 SF 现货保护。网站候选 bundle 与两侧源码 441 组逐字段一致。

本机安装版本含尚未归入 main 的既有消息摘要等功能，因此本机候选基于已安装源码 `f360caa` 仅应用本次 OpportunityBoard / OpportunityContract 改动，版本 `v2026.10.20.1`。本 PR 从 main 创建，仅包含此次改动。未发布正式 GitHub Release，未合并 PR。

网站定点发布脚本保存在 funding-radar 的 `scripts/deploy-aster-gc.py`，发布记录同时保存两仓功能提交。

## 发布与验收

- 主站功能提交：6a58e11bf6590f0332e325ddd85199b5645e7ee1；BOT/桌面功能提交：bb1b1db419b68f11407162e5eaada2c27f048697。
- 线上：/opt/funding-radar-web/releases/20261020-aster-gc-1792494716；回滚：/opt/funding-radar-web/releases/20261020-hourly-markers-1792468170。
- 17 个入口/模块版本化，其他 3194 个文件逐一哈希确认保留；服务 PID、独立 PWA 文件不变。
- 三号 Chrome 正式 JCT Bitget→Aster 组合点击复制 GC，剪贴板为纯 JSON：buyEx=bitget，sellEx=gc-aster，type=FF，name=JCT。
- 本机 v2026.10.20.1 安装器退出码 0，健康回执版本匹配；已安装 EXE 与包哈希一致，外观设置和消息源配置哈希不变。WPF 契约 179 项通过。
- PR 待合并，未发布正式 Release；未做实体 iPhone 验收。

## 全面颜色复核（2026-10-20，用户追加检查）

本轮未发现功能缺陷，无需追加生产逻辑或样式发布：上一版 Aster 支持已覆盖颜色分类。

- 正式 Chrome 组合弹窗实测 FF Binance/Aster、Bitget/Aster、Aster/Binance：剪贴板与 data-gc-both、最终计算背景色一致。双 GC 深绿（默认 #008561 / hover #006d4f），混合腿保持浅色。
- 393×852 手机视口逐张读取 JCT 的 20 张机会卡片：12 张双 GC 深绿，8 张包含 Bitget 的单 GC 浅色；Aster 双向分类均正确，无横向溢出。
- SF Aster现货/Binance合约为 aster→gc-binance，非双GC；SF Binance现货/Aster合约为 gc-binance→gc-aster，双GC。FS Aster合约/Binance借币现货为 gc-aster→binance、cross，非双GC。
- SF Aster现货/Bitget合约无可转换腿，不显示GC按钮；FS Binance合约/Aster现货不显示GC按钮，普通策略复制禁用并明确显示不支持全仓杠杆卖出。
- 正式BOT当时3张卡片：OKX/Binance、Binance/Gate绿框，Bitget/Gate普通边框。当时无Aster实时卡片，Aster组合由441组源码/生产bundle回放及已安装版本对应的179项WPF契约覆盖，不声称当时有Aster实时BOT卡片。
- 当前生产17个已部署文件哈希再次核对一致；本机EXE哈希与通过契约的候选相同。未新增测试交易、修改Astro策略或发消息，仍未做实体iPhone验收。
