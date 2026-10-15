# 单边 GC 与双边绿色边框

2026-10-15，v2026.10.15.2：桌面机会卡片和 BOT 网页卡片在 SF/FF 任意一腿支持时显示「复制 GC」。Binance、Bybit、Gate、OKX、Hyperliquid 按腿加 GC 前缀；Aster、Bitget 保持普通代码。两腿均为 GC 时外框绿色；单腿沿用残差等级原边框，等级徽章、背景和普通复制保持原样。

例如 BYBIT / ASTER → gc-bybit / aster；BITGET / HL → bitget / gc-hl。未知平台、缺失身份、不同标的和合约倍率仍不生成可执行代码。FS 沿用 Astro 的 GC 全仓杠杆限制，不展示 GC。没有新增账户请求或交易操作。

验证：87 项 BOT Node 测试；完整 scripts/build.ps1 成功，包括核心95项、WPF运行烟测、机会卡片/诊断/云源/云窗口契约以及4种更新进程检查。20组单边交易所与方向组合覆盖；真实 WPF 按钮点击验证两种方向剪贴板。WAL、BLUR 双 GC 绿框，ZERBRO 单 GC 原边框，150%渲染无按钮裁切。一次 Windows 剪贴板占用导致恢复失败，重跑完整构建通过。浏览器隔离样例实际点击验证单/双 GC 内容和无 GC 隐藏，验收后已清除样例。

腾讯云 BOT 增量目录 `robot-push/web-session-gc-one-leg-20261015`，页面追加该目录 gc-border.css，其他网页功能不覆盖。统一前端发布 `20261015-gc-one-leg`，回滚 `20261015-funding-badge-aligned`。

本机原安装目录已更新到 v2026.10.15.2，全部清单文件 SHA256 一致，存储路径文件未改动。备份位于本任务 outputs/gc-one-leg/desktop-before-v20261015-2。未发布 GitHub Release、未改手动更新机制；正式 Release 应在合并后按既有流程发布。
