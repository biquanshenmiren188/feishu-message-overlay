# 报警页测试推送（2026-11-11）

“管理设备”旁新增测试推送，复用 alarms-api/change 的 action=test，由后台当前推送码绑定的 Bark 设备发送。未绑定或请求中禁用；队列处理中禁用重复发送。最近测试结果随既有五秒状态轮询更新，显示排队、发送、接受、失败、未知、过期和取消。Bark 接受不等于手机已显示。测试仍为普通提醒；强提醒及表单简化属于用户后续方案讨论，本次未实现。

验证：35 项后台单元测试；1440/393/320px 合成 API 浏览器验证，包括生产样式、禁用、状态反馈、错误、限流、幂等请求重试、切码清理和无横溢出。未向真实手机发送测试消息。

部署源码：4ca2dc0fc2e58e1b62f906d01f9146577526a2c1。
上线目录：/opt/funding-radar-web/releases/20261111-bark-test-1794402075579567925。
前版：/opt/funding-radar-web/releases/20261106-duo-compact-1793979688292156498。

仅修改 robot-push/alarms/index.html、app.js、style.css；HTML/CSS 在实时基线上增量应用，保留已有紧凑样式，app.js 发布前与仓库基线哈希一致。deploy-bark-test-button.py 在 guard.lock 下校验基线和候选哈希、克隆当前 release、原子切换并保留其他文件；原服务 PID、用户设置订阅摘要及 PWA fallback 保持不变，未修改后台或数据库。部署后再次读取 current 和三文件 SHA256，全部匹配候选。

GitHub PR #64 待合并。回滚时原子切回前版静态目录，不恢复用户数据。

## 2026-11-11 后续：简化报警与统一强提醒（已上线）

用户确认所有 Bark 报警及测试均强提醒、直接上线。表单缩为交易所、币种、涨到/跌到、目标价格和提醒次数；记住上次交易所。新保存参数：future/last、hold=0、immediate=true、recovery=false、cooldown=300、hysteresis=0、长期有效。已有规则不重写数据库；编辑保存前提示按简化设置重置高级参数。所有实际发送统一 level=critical、volume=5，包括旧规则、旧客户端和已排队载荷。无需迁移设备，手机必须授权“重要警告”。本节取代上文测试普通提醒的历史状态。

源码 76d5464b36af55af289e123eba0df9132eaa1f13；静态 release 20261111-simple-critical-1794402399205899748；后台 /opt/radar-alarms/releases/76d5464b36af55af289e123eba0df9132eaa1f13。
前版静态 20261111-bark-test-1794402075579567925；前版后台 c08f64e1ae1fe72a07c9399a62199a55833bf4c6。回滚只切换两处 current 链接并重启 radar-alarms，不回滚用户数据库。

38 项后台测试本地及生产隔离候选均通过；1440/393/320px 真实 Chrome 合成 API 测试覆盖简化表单保存参数、测试请求、错误、幂等重试、状态及切码。手机视口截图已检查。部署仅重启 radar-alarms，未重启 BOT、Web Push、桌面；其他静态文件、PWA fallback 和现有设置保持。部署后全部目标文件哈希匹配，运行健康接口 version=2、notificationLevel=critical。未人工发送手机通知，不宣称实体手机响铃已验收。PR #64 同步，待合并。

## 2026-11-11 循环响铃 30 秒（已上线）

用户明确要求所有报警与测试均强提醒并循环响铃30秒。统一发送层强制 level=critical、volume=5、call="1"，覆盖旧规则、旧队列和测试入口；不靠浏览器选择参数。页面同步告知循环时长。依据 Bark 官方 docs/params.md 的 call 参数约定；未额外发送人工通知，实体设备播放时长未代用户确认。

本地和服务器候选38项测试通过，测试请求和旧载荷均断言 call="1"；旧载荷即使 call="0"也由发送策略覆盖。部署源码 411a6c05ffba1f24ea45fa4ba6bd785674357635；静态 release 20261111-bark-ring30-1794402886784921208；后台 /opt/radar-alarms/releases/411a6c05ffba1f24ea45fa4ba6bd785674357635。前版静态 20261111-simple-critical-1794402399205899748，后台 76d5464b36af55af289e123eba0df9132eaa1f13。仅重启报警服务；其他服务、绑定、用户规则保持。部署后静态及后台所有目标文件哈希匹配，健康接口 version=3、notificationLevel=critical、ringingSeconds=30。PR #64 已同步，待合并。
