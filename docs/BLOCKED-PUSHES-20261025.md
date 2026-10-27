# 已屏蔽推送查看入口

BOT 机器人推送工具栏显示「已屏蔽 N 条」，点击按电脑和手机分别查看当前推送码保存的历史信号摘要、时间、规则版本及屏蔽原因。桌面 history 仅统计 channel=desktop/action=hide，卡片和 mute 不计入；手机读取 blockedHistory。两渠道分别计数，最多各 200 条。历史不代表当前规则仍屏蔽；后端没保存的全文不伪造。未绑定时入口禁用，查看不改变任何规则或补发通知。

复用鉴权 GET desktop-settings/status，8 秒超时，关闭时 30 秒轮询；打开是带读取时间的快照，手动刷新。切码/解绑清空并关闭弹窗，异步响应校验身份及请求代次。失败清空记录，不将读取失败显示为零。原生 dialog 支持 Escape/焦点恢复，文本使用 textContent。

## 发布

- 功能源码：`3fa06cd8776a333b558c5896a4f52e8b2628ad39`；[PR #49](https://github.com/biquanshenmiren188/feishu-message-overlay/pull/49) 待合并。
- 当前发布：`/opt/funding-radar-web/releases/20261025-blocked-pushes-1792921873-fd0cc9`。
- 前版：`/opt/funding-radar-web/releases/20261025-quote-label-1792912560`。
- 回滚备份：`/opt/funding-radar-web/backups/20261025-blocked-pushes-1792921873-fd0cc9`，其中 pwa-index.html 是旧 PWA fallback。只回滚代码与入口，不回滚用户数据。
- 新增 blocked-pushes.js/css，只向实际线上 BOT HTML 和 PWA fallback 追加 module；未覆盖源仓库旧整页。既有 PR #48 卡片查看 bundle `bot-cards-bad2bcae5dcc.js` 保留。
- 全部 3351 个非目标文件、规则、绑定、订阅及运行服务 PID 保持；未重启服务，未发送测试消息。

## 验证

216 项网页 Node 检查通过；实际候选 Chromium/WebKit 在 1440/393/320px 无横向溢出，入口 44px。已验证分渠道、排除静音/卡片、Escape/焦点、拒绝访问清空、空列表、文本注入无效、迟到响应/切码隔离、解绑、PWA、卡片入口保留和零 POST。

部署后所有目标资产和 PWA fallback 哈希与测试候选一致。现有鉴权接口实际返回两类数组；匿名请求拒绝，推送服务健康。正式 Chrome 访问仍停在 Cloudflare Access 登录页，未绕过登录；已登录正式页面的人工视觉复核未完成，不把隔离浏览器验证描述为真实账户 UI 验收。

可复现：scripts/prepare-blocked-pushes.py、scripts/verify-blocked-pushes.cjs、scripts/deploy-blocked-pushes.py。候选以新取的实际静态快照为输入，发布守卫核对基线与测试哈希，复制当前 release 并保留其他文件，再原子切换；源码和部署记录分别提交。
