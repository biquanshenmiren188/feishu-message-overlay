# 聚宝扫描手机图标

2026-10-18 按用户确认的金元宝、铜钱、扫描回波定稿替换 PWA 192/512px 图标，并添加 180px Apple Touch Icon；BOT 和 PWA HTML 引用网站新品牌层与 favicon。

manifest 只改变 icons 的版本化 URL，保留 id、start_url、scope、名称和所有其他字段。worker 仅增加缓存版本后缀 `20261018-treasure1`；数据库 KIND、配置、订阅、通知显示和回执逻辑不变。更新现有回执测试中的版本预期，5 项 worker 协议测试通过。

部署由 funding-radar 的 `scripts/deploy-treasure-brand.py` 统一协调。对线上完整 HTML 增量修改，禁止使用本仓 HTML 覆盖已有 overlays；不执行完整后端 deploy，不触发测试推送，不更改用户设置或订阅，不重启服务。

已有 iPhone 主屏幕图标可能由系统继续缓存；新安装会读取更新后的 Apple Touch Icon。保留原安装身份，不要求删除应用或重新订阅。实体 iPhone 的桌面图标更新不由 Chrome 视口验收代替。

## 已发布

配套源提交 `823594e85bd6d0ff2d5b0b9180d9539bb5124fd4`，主站 `ed97d60f36889f8a377ee7ec638f19616102938d`；release `20261018-treasure-brand-1792293929`，备份位于 `/opt/funding-radar-web/backups/` 同名目录。PR #37 与主站 #129 发布时未合并。

并发 worker 更新被基线锁定检查发现并保留，包括正文哈希与 display-settled 诊断；实际发布只修改最新在线 worker 的缓存 VERSION，不以本分支 worker 全量覆盖。生产 PWA 安装身份及服务 PID 保持，手机 320–414px 无横向溢出，图标资源返回 200 且哈希匹配。

## 紧凑透明页头

品牌 CSS 引用升级为 `20261018-treasure2`，由主站共享透明底元宝与字标，手机 138×42px，去除深色方框。此次 header-only 发布保留已选定的网站及手机图标，不改 manifest、worker 或订阅；仅增量更新现有线上 HTML 的品牌引用。
