# 2026-11-06 Duo 切换与紧凑字号复查

用户明确要求紧凑小字。消息与报警页在 1024px 以下统一输入/选择文字 13px、主要标题 14px、按钮 12px，保留原有点击区域与缩放能力。宽屏电脑原样保留。没有写入规则、保存报警或发送测试推送。

组合图表跨越 900px 时原 effect 会把 index/constituents 选择清为 chart。改为保留 requestedView，仅派生宽屏当前显示的 chart；折回恢复原选择，用户主动选择其他标签仍生效。保持现有图表 autoSize 和 ResizeObserver。

验证：线上旧版消息/报警草稿在 382→669→951→594→385→382 切换中保留，弹窗无横向溢出且可滚动。新版两页真实 HTML/CSS（移除联网脚本、打开测试弹窗）在上述五尺寸及 320/1440 共 14 组检查中无横向溢出，13px 输入、14px 标题生效。当前线上图表模块的候选增量在本地 Chrome 验证宽屏组合视图、折回恢复指数价格/指数成分；不是实体 Duo/Safari 验收，本地历史数据接口不可用，未声称验证真实曲线内容。后段线上浏览器登录过期，交付依赖服务器文件哈希复核。

主站 655 项 Node 测试、TypeScript 和 Vite 构建通过。部署仅更新两页样式与对应样式链接、图表状态模块及受影响的模块引用，不整体覆盖构建产物。线上消息页额外脚本版本/头部差异从当前线上保留。发布脚本检查当前目标、基线哈希、文件白名单、其他文件、服务 PID 和 PWA fallback，并保留回滚路径。

图表候选构建：funding-radar/scripts/prepare-duo-chart-view.mjs BASELINE STAGE；发布：scripts/deploy-duo-compact.py STAGE [--apply]。CSS 输入与静态 HTML 版本来自 feishu-message-overlay/web/robot-push/{settings,alarms}。部署和 PR 信息在完成后补入。
