# 聚宝扫描手机图标

2026-10-18 按用户确认的金元宝、铜钱、扫描回波定稿替换 PWA 192/512px 图标，并添加 180px Apple Touch Icon；BOT 和 PWA HTML 引用网站新品牌层与 favicon。

manifest 只改变 icons 的版本化 URL，保留 id、start_url、scope、名称和所有其他字段。worker 仅增加缓存版本后缀 `20261018-treasure1`；数据库 KIND、配置、订阅、通知显示和回执逻辑不变。更新现有回执测试中的版本预期，5 项 worker 协议测试通过。

部署由 funding-radar 的 `scripts/deploy-treasure-brand.py` 统一协调。对线上完整 HTML 增量修改，禁止使用本仓 HTML 覆盖已有 overlays；不执行完整后端 deploy，不触发测试推送，不更改用户设置或订阅，不重启服务。

已有 iPhone 主屏幕图标可能由系统继续缓存；新安装会读取更新后的 Apple Touch Icon。保留原安装身份，不要求删除应用或重新订阅。实体 iPhone 的桌面图标更新不由 Chrome 视口验收代替。
