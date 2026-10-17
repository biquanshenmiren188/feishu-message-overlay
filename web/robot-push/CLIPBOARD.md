# 2026-10-17 BOT 手机复制

用户反馈 BOT 卡片“复制 / GC 复制”在手机上粘贴不可用、代码混乱。线上卡片仍直接写带 `ASTRO-QUICK-COPY:` 前缀的旧文本，未同步主雷达在 2026-10-12 上线的纯 JSON 剪贴板处理；原生接口拒绝时仅显示 pre 文本。

`clipboard.js` 在剪贴板边界去除前缀并输出纯 JSON，保留原策略类型、币名、买卖方向、逐腿 GC 平台代码和 FS 借币字段；普通卡片文字原样。卡片构造器、行情与交易逻辑未改。原生调用直接发生于点击手势内；拒绝时在当前弹层内使用隐藏 textarea、完整选择和 text/plain 回退，清除其他格式并恢复焦点。旧请求不能覆盖之后点击的新代码。失败不显示成功，提供带只读文本框的弹窗，可重试、选择全部或长按复制。

前缀触发 iOS 格式识别是基于历史问题的兼容性推断，并非本次已在实体手机确认的唯一根因。纯 JSON 已由主雷达历史导入器验证支持。本次没有执行任何策略导入、下单、通知推送或账号变更。

参考：[WebKit Clipboard API](https://webkit.org/blog/10855/async-clipboard-api/) 说明纯文本写入、用户点击手势要求和旧选择复制方式。实现无需额外剪贴板读取权限。

## 发布

`deploy_clipboard.py --baseline <已检查的线上快照>` 读取实际加载目录，仅将 source-entry、basispulse、card、clipboard 四个模块放入新目录，并更新 BOT/PWA 入口。旧模型、GC 单腿与 FS 支持、中文币名规则、样式、SharedWorker 及其 URL 身份原样保留。部署持维护锁、验证当前release及SHA、备份PWA fallback、逐文件核对并原子切换。不得以仓库main旧页面或旧卡片模型覆盖线上。

`--prepare <目录>` 生成同一候选图供本地浏览器验收；尚未提交部署不会更改服务器。

## 验证

86项网页Node测试通过，包含新增7项剪贴板回归：普通/GC、Unicode/倍率/FS、同步调用、原生拒绝、无API、失败清理、并发点击。浏览器验证候选模块实际普通与GC复制、JSON粘贴、SIREN Binance→Aster及中文币名；模拟双接口拒绝后320px弹窗完整选取83个字符。自动化浏览器的虚拟剪贴板不作为实体iPhone跨应用粘贴验收。


上线：提交 `ecc9143`，release `/opt/funding-radar-web/releases/20261017-bot-clipboard-1792226158`，前版 `20261017-apple-ui-1792208068`；备份 `/opt/funding-radar-web/backups/20261017-bot-clipboard-1792226158`。2,637个原文件保持SHA不变，两个服务PID不变。实际线上加载新入口，消息源连接、消息区及卡片区运行正常，无站点脚本错误；验收时没有活跃机会，卡片复制用相同候选模块的本地样例验证。723组现行模型载荷逐字段一致验证通过，含普通/GC、SF/FS/FF、混合交易所、Unicode与倍率币。

回滚：持维护锁，恢复backup的PWA HTML，并原子切换current至previous；有后续发布时先检查差异。实体iPhone最终跨应用粘贴未代验；已打开旧页需要刷新。
