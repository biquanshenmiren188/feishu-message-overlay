# BOT 进入页面等待规则校验：资源预算修复

功能提交：`0eb376536ff7804b9b3e3d27caf4a8b043703ee5`。本次仅调整运行服务预算，未发布静态页面或修改业务 Python/JS。

## 实测原因

Chrome 3号已连接推送码的真实 BOT 首次打开，message-decisions 和 card-decisions 都在约 919 ms 发起，约 7004 ms 后超时。下一次分别在页面打开后 11776 / 12176 ms 完成。静态政策模块下载只需 3–4 ms，延迟主要不在页面样式或模块体积。

原服务限制是 CPUQuota=20%、MemoryMax=128M、TasksMax=16。当前已有16个方案状态，后台和网页请求共享同一进程。5秒线上采样：50个CPU周期中48个限速，累计限速4.54秒，memory.events max增加14。主机2核，约2 GB可用内存。服务器回环接口12次读取耗时502–2504 ms；隔离副本同一判定代码约133 ms，支持服务资源争用的判断。

## 修改

- 服务预算改为 CPUQuota=100%、MemoryMax=256M、TasksMax=64，仍有明确上限。
- `systemctl set-property` 同时持久化配置和更新运行中的 cgroup，所有服务PID不变。
- 原鉴权、规则、指纹匹配、10秒判定有效期、OI真实性/新鲜度、失败时不展示未校验内容均保持。
- 前端文件、PWA身份、绑定、报警规则、备用源、自定义内容、30秒多设备报警均没有改动。

## 验收

| 检查 | 修复前 | 修复后 |
| --- | --- | --- |
| 回环规则请求12次 | 502–2504 ms | 3–50 ms |
| 桌面浏览器首次复查，两条判定完成 | 11776 / 12176 ms | 1238 / 1235 ms |
| 手机393px首次复查，两条判定完成 | 未单独采样 | 785 / 811 ms |
| 393px连续刷新两次，消息/卡片完成 | 未单独采样 | 410/376、334/353 ms |
| 1440px连续刷新两次，消息/卡片完成 | 未单独采样 | 399/398、334/346 ms |
| 8并发24次读取，3个方案、4个只读接口 | 未单独采样 | 全部成功，14.69–224.93 ms，中位90.94 ms |

浏览器值为导航开始到接口完成，后续确认30条普通消息和6张卡片正常渲染，等待提示隐藏；不是跨用户p75，也不是实体iPhone测量。连续刷新属于热缓存。窗口已恢复原尺寸。未发送人工手机通知、未改真实规则。

修复后5秒采样：仅约2 ms限速，内存上限事件增量0。无效凭据仍返回401。报警健康接口version15、multiDevice=true、repeatIntervalSeconds=30，后台版本和PID原样保留；本次没有再次触发实际30秒通知。

## 发布与回滚

执行脚本：`scripts/deploy-bot-resource-budget.py`，执行前后比较推送绑定/规则、报警数据库配置、三服务PID、静态和报警后端软链，均相同。

备份：`/opt/radar-webpush-test/backup-resource-budget-1794797863378574247`。

静态版本仍是 `/opt/funding-radar-web/releases/20261115-mobile-header-1794750061757059419`；报警后端仍是 `/opt/radar-alarms/releases/470e731715cf77e228e2c32e966f237c534df474`。

持久设置位于 `/etc/systemd/system.control/radar-webpush-test.service.d/50-{CPUQuota,MemoryMax,TasksMax}.conf`。后续调整必须同时核对有效值与这些override；不要只编辑基础unit并误以为覆盖已更新。

必要时确认当前配置仍是本次100%/256M/64后，执行 `systemctl set-property radar-webpush-test.service CPUQuota=20% MemoryMax=128M TasksMax=16` 可恢复旧预算，无需重启。不恢复或覆盖用户数据。旧预算存在已复现的首屏等待问题。

代码及记录同步PR70，未合并。
