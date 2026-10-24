# 手机 BOT 卡片阅读位置

2026-10-24：手机向下阅读卡片时，新行情带来的上方卡片替换、重新排序或过期删除，会改变正在阅读卡片的屏幕位置。此前的 240ms 手势门控只保护触摸和惯性期间，无法覆盖手指离开屏幕后继续阅读的场景。

使用实际线上 HTML、CSS 和 bundle、合成消息与行情隔离复现：仅新增机器人消息、5 秒自动推进均不改变整页位置；上方 BBB 卡片过期删除后，CCC 卡片的 viewport top 从 90.256px 变为 -194.271px，上移约 284.5px，消息框高度保持 409.356px。浏览器关闭文档原生 scroll anchoring 的对照用于定位，不能代替实体 iPhone 验收。

真实 WebKit 的第二次对照确认：仅同高度行情卡片 `replaceWith` 更新，也会将 document.scrollY 从 1785px 拉回 107px，正在阅读的卡片顶部从 160.828px 变为 1838.828px，下移 1678px（无缺失资源或脚本错误）。因此保护需要包住完整同步 DOM 提交，并根据最终卡片位置修复中间布局收缩造成的文档滚动截断，不能只处理过期删除或只检查最终高度。

修复在每次手机卡片 DOM 提交前记录可见卡片的位置，提交后根据仍存在的卡片补偿实际位移。浏览器已经完成位置保持时不重复滚动；触摸、惯性、弹窗、缩放及电脑双栏不受补偿干扰。接收消息、机会失效、个人推送码规则和消息区内部自动滚动保持原有行为。

## 验证和发布

- `node --test web/robot-push/mobile-scroll.test.mjs` 验证阅读锚点与手势门控。
- `scripts/verify-mobile-feed-scroll.cjs` 使用真实部署静态资源与虚构数据在本地浏览器回放，比较卡片 viewport top 和 document scrollY，不向线上发测试推送。
- `scripts/prepare-card-scroll.py --baseline <snapshot> --out <candidate>` 校验原 bundle 哈希，修改四个明确位置，输出带内容哈希的新模块和 bundle，同步 BOT 与 PWA fallback 引用。
- `scripts/deploy-card-scroll.py <server-stage> <source-sha>` 在发布锁内验证实际基线，复制当前整套静态资源，只更改 BOT 入口并新增模块；校验其他文件完整保留、服务 PID 不变，并记录可回滚版本。不重启服务或桌面程序，不读写订阅及用户规则。

网页单元测试 163 项通过（其中阅读位置/手势 18 项）。Chromium 与 WebKit 的 12 种回放场景均有通过记录，加上 320/414 手机宽度与 1440 电脑历史阅读共 30 条有效场景；最终 helper 增加重复 key 排除后，普通行情刷新、同 pair 换 ID、上方卡过期的双引擎 6 项核心复验通过，最大位移 0.140625px（亚像素取整）。使用本地合成数据，未向线上发送通知，不声称实体 iPhone 已验收。

首次部署前的基线保护检测到另一轮手动保存更新已切换 current，故在任何线上变更之前退出。随后重新抓取 `20261024-card-manual-save-1792851483-014cf6`，确认新 BOT bundle `68efcd61ca2a` 与原 `8d81b8292063` 仅有 card-policy import 版本变化，完整保留新的 card-policy、card-manager 和 CSS；在新基线上重新构建并复验。部署结果在完成后补记。
