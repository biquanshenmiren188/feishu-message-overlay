# 报警页测试推送（2026-11-11）

“管理设备”旁新增测试推送，复用 alarms-api/change 的 action=test，由后台当前推送码绑定的 Bark 设备发送。未绑定或请求中禁用；队列处理中禁用重复发送。最近测试结果随既有五秒状态轮询更新，显示排队、发送、接受、失败、未知、过期和取消。Bark 接受不等于手机已显示。测试仍为普通提醒；强提醒及表单简化属于用户后续方案讨论，本次未实现。

验证：35 项后台单元测试；1440/393/320px 合成 API 浏览器验证，包括生产样式、禁用、状态反馈、错误、限流、幂等请求重试、切码清理和无横溢出。未向真实手机发送测试消息。

部署源码：4ca2dc0fc2e58e1b62f906d01f9146577526a2c1。
上线目录：/opt/funding-radar-web/releases/20261111-bark-test-1794402075579567925。
前版：/opt/funding-radar-web/releases/20261106-duo-compact-1793979688292156498。

仅修改 robot-push/alarms/index.html、app.js、style.css；HTML/CSS 在实时基线上增量应用，保留已有紧凑样式，app.js 发布前与仓库基线哈希一致。deploy-bark-test-button.py 在 guard.lock 下校验基线和候选哈希、克隆当前 release、原子切换并保留其他文件；原服务 PID、用户设置订阅摘要及 PWA fallback 保持不变，未修改后台或数据库。部署后再次读取 current 和三文件 SHA256，全部匹配候选。

GitHub PR #64 待合并。回滚时原子切回前版静态目录，不恢复用户数据。
