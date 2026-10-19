# iPhone 主屏幕启动缓存优化

用户反馈从 iPhone 主屏幕每次打开 BOT 都整屏白约两秒。检查 20261019-bitget-uta-1792397258 线上版本发现：旧 worker 先等网络失败才读缓存，预缓存仍指向旧设置页；BOT 首屏四份 CSS 和主要 JS 落在 nginx 的 no-cache 路由。

## 行为

- 保留 `/radar/push-test/` 的安装 ID、start_url、scope、manifest 和原 worker 注册地址。协议仍是 v6，版本为 `radar-delivery-v6-20261019-startup1`。
- 独立 `radar-startup-v1` CacheStorage 保存空页面框架与静态资源；导航缓存命中立即返回，后台校验和更新 HTML。新版框架在下次打开使用，不强制刷新正在阅读的页面。
- 只接受含空 feed/pinned 容器的 BOT HTML；不缓存登录跳转、错误页或含消息的文档。网络鉴权返回 401/403 或重定向时清除缓存文档。
- 静态资源按完整 URL（含版本参数）匹配；带内容哈希的 CSS/JS 命中后无网络验证，其他静态资源后台更新。CacheStorage 错误/卡住有回退和时限。
- feed.json、basispulse.json、设置/账号 API、POST、外站、worker 脚本及携带非版本参数的请求不拦截。离线页面框架不表示行情仍有效。
- 安装时从实际 BOT HTML 收集资源，替换旧设置页资源清单。
- 部署脚本按线上顺序合并四份 CSS、将相对图片地址改为绝对站内路径、生成内容哈希文件。nginx 只给经实际 SHA256 校验的当前 CSS/JS 配置 private 一年 immutable 浏览器缓存。HTML、API 与 Cloudflare Access 保持现行认证和实时性。

## 保留线上叠加改动

`scripts/deploy-pwa-startup.py` 只将仓库 worker 中 `function db()` 之前的启动部分拼接到当前线上 worker，其余通知显示、正文哈希诊断、750ms display-settled 检查、订阅身份与回执逻辑逐字节保留。main 尚未包含部分独立已部署诊断，不能用仓库旧 worker 整体覆盖生产。

同样从实际 current 克隆完整 release，只替换 BOT HTML、增加合并 CSS；同步 PWA fallback。持 guard.lock 核对 current、HTML、worker、nginx 和 manifest 基线，再原子切换。记录所有原非目标文件哈希、两服务 PID 和订阅/筛选摘要，任何失败回滚静态文件及 nginx，不回退业务状态。未发人工测试通知。

## 验证

```sh
node --test web/push-test/startup-cache.test.mjs web/push-test/sw.test.mjs web/push-test/protocol.test.mjs
# 对最终生产候选运行同一启动回归：
STARTUP_WORKER=/path/to/candidate/sw.js node --test web/push-test/startup-cache.test.mjs
```

26 项源码回归通过；实际线上 suffix 拼接后的候选另通过 12 项缓存回归。涵盖暖启动在网络未返回时可用、离线、版本查询参数隔离、哈希资源零网络命中、私有 API 排除、登录失效、错误 MIME、存储异常、安装预热，以及原通知显示顺序和切码隔离。

本机 Chrome 隔离 fixture（非生产、非实体 iPhone）：HTML/CSS 人为各延迟 2000ms、HTTP no-store，三次暖导航 responseStart 旧版 2012–2020ms，中位数约 2020ms；新版 4.0–8.4ms，中位数 5.6ms。断网仍显示已缓存框架；样式计算结果一致。iframe 的 rAF/绘制受到后台调度，不用其 elapsed/FCP 推断真实手机白屏或 LCP。复现工具 `scripts/pwa-startup-browser-test.cjs` 接收含 `live-sw.js` 与 `candidate/sw.js` 的隔离目录，端口 8765。

首次无缓存访问仍需网络；已安装 iPhone 需正常打开以接收新 worker，之后的打开才享受完整缓存。不能将模拟值承诺为 iPhone 秒开。无需删除主屏幕图标、清理 Safari 数据或重新订阅。

## 发布和回滚

先准备候选、验证并推送代码，再用完整 source SHA 执行脚本 `--apply`。候选与发布信息写在暂存目录 `candidate.json`/`deployed.json`，公开的 `pwa-startup-release.json` 仅含代码/静态文件哈希与布尔验证结果，无凭据和消息。

回滚需持 `/var/lib/funding-radar-storage/guard.lock`：从本次 backup 恢复 public/sw.js、public/index.html、radar-webpush-test.conf；本次新建的 radar-startup-cache.conf 可移到备份目录；校验 nginx 并切回 previous，再 reload nginx。回滚 worker 会触发正常更新，独立的启动缓存不会删除订阅数据库。
