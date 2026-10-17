# 手机有卡片时的滚动抖动修复

2026-10-17 用户报告：下方出现机会卡片后，整页滑动不顺、抖动。

原手机 `.feed-pane` 使用 60dvh，Safari 地址栏伸缩会改变上方消息区高度；`fitCards` 又按 visualViewport 裁减消息框。下方卡片的重排、替换、移除没有避让整页触摸和惯性滚动。

修复：手机叠放布局使用 60svh 稳定高度，body 不再成为额外滚动容器；消息框按所在面板计算可用高度，桌面仍按视口裁减。`mobile-scroll.js` 用被动事件观察手势和所有滚动，静止 240ms 后合并执行最新结构更新，不调用 preventDefault、不设置页面 scrollTop。卡片的连接、过期状态与计数继续更新，接收/模型处理不暂停；结构变化、消息区测量和消息列表重绘等待滚动安定。取消、多指、后台恢复、切回桌面均能清理等待状态。

84 项网页 Node 测试通过，包括 5 项新的惯性延迟、最新更新合并、取消、多指、后台恢复与面板几何测试。基于实际线上 bundle 的本地三卡片对照：11.5 秒模拟触摸期间旧版替换 3 张卡片，新版 0 张；松手后 500ms 内新版已更新 3 张。模拟 visualViewport 高度变为 450px 时，旧消息框从 345px 变 161px，新版维持 345px。这是 Chromium 模拟证据，不等同实体 iPhone Safari 手感验收。

生产当前采用 performance-20261017 合并资源，不能发布旧源文件或完整旧构建。`scripts/prepare-mobile-scroll.py` 必须验证原 bundle 的固定 SHA，只在 fit、消息列表 render 和卡片 render 三个函数中执行 10 处限定替换，并导入独立模块。其他采集、交易所模型、普通/GC 纯文本复制、通知设置和已确认 Logo 都保留。脚本遇到线上 bundle 变化应停止重新检查。

`scripts/deploy-mobile-scroll.py` 在现有维护锁内验证 release、BOT HTML 和实际 bundle/CSS 的 hash，克隆现场版本，只新增三个资源并改 BOT/PWA HTML 引用，校验其他文件全部相同，保留消息源与推送服务 PID。回滚时在同锁内切回报告 previous，并恢复 backup/pwa-index.html；有后续发布时先核对差异。
