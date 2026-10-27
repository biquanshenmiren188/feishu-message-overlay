# 紧凑卡片共用样式版本

用户确认约半面积的卡片预览并授权验收后合并发布。本仓仅将 BOT、独立消息设置及 PWA 回退模板的共用样式版本从 `20261027-ui2` 更新为 `20261027-cardcompact1`。三个 HTML 除该版本字符串外字节不变；业务脚本、所有功能、规则、消息、复制与 PWA 身份保持。

卡片样式和增量部署工具由 funding-radar 仓库维护，见该仓 `docs/CARD-COMPACT-20261027.md`。宽屏三列使用已确认的紧凑尺寸；较窄电脑卡片双腿上下排布防止重叠，手机沿用原布局。

发布必须从实际线上 current 精确替换 stylesheet 版本，不能把本仓历史模板整页覆盖生产。同步独立 PWA fallback，保留 settings 目录链接与所有服务。正式发布与验收记录见下文。

## 已完成的正式发布（2026-10-27）

- 主站 [PR #152](https://github.com/biquanshenmiren188/funding-radar/pull/152) 已合并，合并提交 `1dfd1f4d50b81cd2bfc66bed50ce5c0ada7ca6ab`。
- 推送模板 [PR #53](https://github.com/biquanshenmiren188/feishu-message-overlay/pull/53) 已合并，合并提交 `42d5b8cbb31f350cbbe563b3e2190e5ed0a35433`。
- 实际部署源码：`fbb7a92bf9a7eca1143ad3d04ba00d42cf1214e7`；推送模板源码：`75dd95e14bc81b700b6cc29ff656dd3005b8c768`。
- 正式 current：`/opt/funding-radar-web/releases/20261027-ui-only-1793082678186448077`。
- 备份：`/opt/funding-radar-web/backups/20261027-ui-only-1793082678186448077`。
- 前版：`/opt/funding-radar-web/releases/20261027-ui-only-1793075960874822903`。
- CSS SHA256：`fb37f2b77169c0b8d42d85542f3ead4038d1a870d9c400b3d72f0371ef37151f`。

发布后重新遍历 3388 文件，除既有动态行情缓存外的非目标资源哈希不变。四个入口 HTML 仅替换 CSS 版本；独立 PWA fallback 与 settings 别名验证通过，候选预览未进入正式 release。robot-push（PID 1577688）及 radar-webpush-test（PID 2266340）继续 active，未重启；用户规则与订阅保持。

最终候选及正式 BOT 在 2041、1440、1200 宽电脑和 393、320 宽手机视口验收，页面无横向溢出。宽屏普通卡片约 371×228–230px；窄卡为完整显示字段自动增高。六页面在 1440/393 宽度的导航尺寸一致，正式 PWA Web 入口加载新 CSS 并显示原卡片和四个操作。

普通策略复制与 GC 复制成功，内容均可解析为 JSON，验收后恢复原剪贴板。币种管理在手机正常打开/关闭，没有保存或更改规则。额外静态样本验证 50 字符币名自动换行、-12.34% 费率/8h、+123.45% 指标及“已复制/重试复制”按钮，未溢出或删字段。

527 项现有测试、TypeScript、最终 Vite 构建及 Linux 27 项隔离部署测试通过。GitHub Windows/Cloud reader 因账户计费限制未启动，不算云端 CI 通过。手机仅 Chrome 视口验收，未进行实体 iPhone/Safari 测试；没有发通知或改交易配置。

回滚应在 guard.lock 内核对 current 与独立 fallback 仍属于本次发布，再恢复备份 fallback 和前版 current；settings 别名随 current 切换，不写穿链接，不回退业务状态。后续发布已推进时停止，不覆盖新版本。
