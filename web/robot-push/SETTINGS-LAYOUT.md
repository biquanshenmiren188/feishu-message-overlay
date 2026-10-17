# 手机推送设置：紧凑布局与滚动修复（2026-10-17）

用户截图显示旧版大弹层和不齐的BOT工具栏；截图中的“最新在最下面”“接收真实BOT消息”也表明页面仍加载旧设置模块。原弹层只有max-height与flex布局，缺少确定高度的中间滚动轨道。新适配层使用明确可用高度与grid的auto / minmax(0,1fr) / auto三行，标题/关闭和保存固定，正文独立滚动。

- 弹层上限620px，左右留10px，字段和辅助说明收紧；输入仍16px、主要触控44px。
- VisualViewport变化时重算高度与顶部位置，适应工具栏和键盘占用。监听仅在弹层打开期间工作。
- “通知与推送码”折叠管理，保留已有开启通知、绑定及新建独立推送码的DOM和处理器。常用设置更靠前。
- BOT工具栏统一44px垂直对齐；360px以下设置按钮独立成行，避免挤压。
- 未改消息区域的行高或JS内联高度，未改通知内容/排序、筛选、订阅或任何API逻辑。

## 发布

新增 `settings-layout.css/js`，只追加到现有BOT与PWA fallback HTML；提高选择器优先级使动态加载的旧CSS不会覆盖修复。为现行notification-settings.js添加内容hash缓存参数，保持文件内容不变。

`web/push-test/deploy_settings_layout.py --expected-release <已检查的完整release路径>` 持维护锁、校验基线、复制current、追加资源与引用、校验其他文件hash、同步PWA fallback、原子切换；失败回滚。不会从当前分支覆盖线上设置模块，因为线上包含独立发布的新功能。

正式版：`20261017-compact-settings-1792206185`；此前：`20261017-push-profiles-1792205891`。保留2,633个其他文件，现行设置模块hash不变，两个服务PID不变。备份 `/opt/funding-radar-web/backups/20261017-compact-settings-1792206185` 含旧PWA HTML和摘要；回滚持同一锁恢复fallback并切回旧current。

## 验证

91项BOT/通知Node测试和JS语法检查通过。Chrome手机模拟393×852、320×640检查无横向溢出；真实触摸事件使正文滚动到底部445px，最后一个交易所可见，保存按钮仍在640px视口内，页面背景scrollTop保持0。模拟393×420可用空间，关闭和保存仍在视口内。保存按钮仍关联ns-form，未点击保存或新建推送码，未发测试通知。没有实体iPhone Safari验证，不能把Chrome模拟当真机证明。
