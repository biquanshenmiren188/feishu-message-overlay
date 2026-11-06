# 消息设置页移除右上角返回 BOT · 2026-11-06

按用户截图，仅删除 `web/robot-push/settings/index.html` 页头中的 `a.preview-pill` 返回 BOT 链接；品牌和六项导航保留。

功能源码：655e4c0f10a5ca0064046f7240a67fa56d316bec。线上从当前 HTML 精确移除唯一匹配的链接，移除之外逐字节保持；没有用仓库完整旧页面覆盖。发布脚本 scripts/deploy-settings-return.py 默认 --check，校验源码/候选哈希、基线、全量静态文件、进程和订阅，锁内克隆后原子切换，异常回滚。

发布版本：20261106-settings-return-1793929216743012912。
前版/回滚：20261105-navigation-shell-1793870747709456836。
备份：/opt/funding-radar-web/backups/20261106-settings-return-1793929216743012912。
目标 robot-push/settings/index.html SHA256：bad57f5ac30edb769c9e80db56240402645457636b007656644adcd7668a53d3。

3516 个其他文件、所有服务和容器进程、消息规则/订阅及 PWA fallback 保持。正式浏览器确认返回按钮数量0、导航6项、桌面页头58px，截图通过。未增加针对此单个链接删除的机械单元测试，也未执行无关交易/推送测试。
