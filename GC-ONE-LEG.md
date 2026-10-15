# GC 逐腿复制与按钮样式

2026-10-15，v2026.10.15.4：SF/FF 任意一腿支持 GC 即显示「复制 GC」。Binance、Bybit、Gate、OKX、Hyperliquid 按腿加 GC 前缀；Aster、Bitget 保持普通代码。两腿均支持时，仅复制 GC 按钮显示 3px 绿色边框和绿色文字；单腿使用普通按钮。卡片外框保留原残差等级颜色。

例如 BYBIT / ASTER → gc-bybit / aster；BITGET / HL → bitget / gc-hl。未知平台、缺失身份、不同标的和合约倍率仍拦截。FS 沿用导入器限制，不显示 GC。

修复主窗口隐式按钮模板忽略 BorderBrush 的问题：GC 按钮使用局部模板，实际 Border 绑定边框，TextBlock 绑定绿色前景。契约加载主窗口资源后检查实际模板节点，而非只检查 Button 属性。用户已确认 3px 绿框绿字实际 WPF 预览。

验证：87 项 BOT 测试；完整构建通过核心95项、WPF烟测、卡片/诊断/云源/云窗口契约、4种更新进程检查。覆盖20组单边交易所与方向、实际按钮剪贴板。正式站真实双 GC 与单 GC 卡片显示已核对。

线上版本：20261015-gc-button-thick，BOT 追加 robot-push/web-session-gc-button-20261015/gc-border-thick.css（SHA256 3b125b5311bb82ce3a0028566514624d7b826ef8d1a3c4a843d7c4434f8bd402）。保留2401个已有文件；回滚到20261015-gc-button。

本机已安装 v2026.10.15.4，全部清单哈希匹配，存储路径未变，连接正常。旧版备份：任务 outputs/gc-button-correction/desktop-before-v20261015-4。未发布 GitHub Release；自动更新设置未改变。
