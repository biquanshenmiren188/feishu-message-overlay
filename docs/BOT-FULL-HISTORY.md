# BOT 消息铺满与最近30条历史

2026-10-18 用户明确要求电脑和手机消息条数铺满整个消息框，随后指定仅保留最近30条。普通消息按原时间排序、自然高度连续排列，超过容器后滚动；置顶独立保留。保留精简摘要、点击原文、原操作链接及用户5秒/声音设置。

桌面旧实现只挂载3条，手机虽挂载历史但消息源每30分钟淘汰旧消息。现在两端均挂载最多30条，不用拉高消息或缩小字号填空。服务器保留最近30条已接收消息，刷新及空闲不会仅因时间而清空；接收端对迟到旧事件的30分钟拒绝规则保持，已有被清理的消息不会恢复或重发。

## 发布

- `prepare_full_history.mjs` 对已核对 SHA 的线上 bundle 做 AST 定点替换，只更新列表布局、历史上限及 HTML 文案。保留线上标题前置、摘要、复制、交易页与全部覆盖层。
- `deploy_summary.py` 持 guard.lock 克隆当前静态版本，校验全部基线、保留非目标文件，同步 PWA fallback，原子切换。
- `publisher/deploy_history.py` 校验线上 server.py SHA，只修改已接收历史的数量保留；备份源码、原子替换并重启 robot-push，核对重新连接。Web Push 服务、订阅、配置和桌面应用不改。
- 回滚静态页须同时恢复原 release 与 PWA fallback；后端从报告中的 backup/server.py 恢复并重启 robot-push，不回退业务状态。

## 验证

45项 FeedStore/CarouselReader/滚动门控测试通过；接收器历史专项验证30条、跨天、重启、独立置顶和迟到事件拒绝；现有接收器生命周期专项通过。Chrome候选393px手机及电脑：挂载30条、自然高度铺满、无横向溢出，到最新、Home、打开原文返回保持位置。实体iPhone未验证。

## 已发布记录

功能源码提交 `9f8db2cc438a9a602429e11d5d5274e5b045c5f5`，PR #38，未合并。线上静态版本 `20261017-summary-risk-1792328081`（发布器沿用历史日期前缀），前版 `20261018-trading-links-1792315937`，保留2934个其他文件。

入口 bundle `performance-20261017/bot-summary-6d71112010fe.js`；HTML与PWA fallback SHA256均为 `890f8a028f2b9feb76b0c60c553bb4737ad234346d932f4e14ab5630cb6ab306`。静态备份 `/opt/funding-radar-web/backups/20261017-summary-risk-1792328081`。后端备份 `/opt/robot-push/backups/history30-1792328072`，server.py SHA256为 `e1bcf98e358efc57fd9c9230d1d78c2d2d41a42dabd5279908788c1032fd8ba5`。

正式Chrome已验证 `full-history-20261018`、最近30条文案和消息源连接；当时服务器实际仅有8条普通消息，全部显示，置顶独立。后续消息逐步累积至30条；不能把合成30条预览称作生产已有30条。
