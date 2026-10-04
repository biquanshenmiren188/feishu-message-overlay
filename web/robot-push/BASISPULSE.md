# BasisPulse 只读机会同步

入口：`/radar/robot-push/?source=basispulse`。机器人消息入口及原 Feishu 接收链路继续保留；新来源不伪装成飞书消息，不向群发消息，也不执行交易。

## 数据链路

独立 `basispulse.service` 使用提供方批准的 `https://basispulse.yielding.pro/openapi/v1/opportunities`，每次请求结束后等待 5 秒，上限 12 次/分钟，低于提供方 20 次/分钟限制。`flock` 防止重复进程。全部访客读取同一份原子缓存，不会触发额外上游请求。

Cloudflare 服务令牌只放 `/etc/robot-push/basispulse.json`，root:robot-push、0640；没有写进仓库、网页、URL 或响应。HTTP 重定向不跟随，避免把鉴权头转发到其他目的地。前端读取同源 `/radar/robot-push/basispulse.json`，仍受网站原有 Cloudflare Access 保护；没有新增绕过规则。缓存采用字段白名单，不转发鉴权头或原始错误响应。

请求超时 10 秒；错误按 5/10/20/40/80/120 秒重试，429 的 Retry-After 优先。进程崩溃由 systemd 重启。缓存保留上次成功数据及其真实时间，错误期间不把旧数据计为活跃。源时间或缓存接收时间落后超过 20 秒也退出活跃状态。

## 展示规则

- 展示所有 active 项，没有 R1 过滤或额外阈值；同一市场组合去重，重新进入的 span 替换旧卡，旧快照不覆盖新快照。
- 名称升序、稳定 R 级别降序、活跃开始时间降序；15 秒排序，级别变化须稳定 15 秒，新项先追加。
- 完整快照中消失的项目，或到达源 validUntil 的项目，变灰保留 30 秒。非完整快照缺项不会直接删除，仍遵守项目原始有效期。
- 币种、方向、两边资金费及周期、成交额、持仓、净收益/盘口差/P75/指数差、充提原文和源更新时间均来自接口。bps 转百分比除以 100；资金费小数转百分比乘以 100，保留四位小数。未知显示横杠，现货不显示合约持仓。
- 手机完整展开，无卡片分页或折叠。可搜索币种/交易所，跳转真实雷达链接。
- 同步的是接口数据和卡片生命周期，不是嵌入源站。源站专用 Astro/GC 交易复制协议不在提供接口中，没有自行生成交易指令；可由“查看原站”使用原站功能。
- 源站 SSE 每秒更新；此授权接口按 5 秒拉取，网页每秒读缓存，正常情况下可能相差约一个到两个刷新周期，不承诺逐秒一致。

## 验证与发布

运行 `node --test web/robot-push/*.test.mjs`：51 项通过。运行 `python -m unittest discover -s web/robot-push/publisher -p basispulse_test.py`：5 项通过；同样的 Python 测试已在生产 Linux 上通过。

Chromium 390×844：全部卡片展开、搜索筛选通过，页面 scrollWidth=390，无横向溢出。桌面布局检查通过。隔离测试接口 503 后页面退出 ACTIVE；恢复接口后无需刷新自动恢复。未进行实体 iPhone/微信测试。

2026-10-04 发布：服务器已成功读取完整快照，凭证未出现在缓存，服务无重启，原 robot-push 服务仍 active。未登录访问缓存返回 Cloudflare 302，保持邮箱验证。随后已在用户指定的 3 号浏览器完成正式页面验收：真实卡片、源时间持续更新，原机器人入口显示“消息源已连接”且 4 个消息卡片；390×844 正式页面 scrollWidth=390，卡片无横向溢出。修复了生产 nginx 未识别 .mjs 的加载问题，浏览器模块使用 .js；没有修改全局 MIME 配置。

发布脚本 `publisher/deploy-basispulse.sh` 会核对原 index SHA256 并备份，备份目录 `/opt/robot-push/backups/basispulse-20261004`。代码上传 GitHub 不自动部署。此变更基于尚未合并的源代码同步 PR #2，使用独立分支和叠加 PR，未合并任何 PR。

回滚：停止并禁用 `basispulse.service`，恢复备份 index.html 和 robot-push.conf，nginx -t 通过后 reload。恢复页面入口和路由即可，不需要改动现有 Feishu 接收器。凭证轮换时仅更新服务器私有配置并重启新 sidecar。
