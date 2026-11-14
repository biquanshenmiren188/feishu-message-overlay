# 临时真机窗口诊断（2026-11-14）

用户确认组合详情数字遮挡已解决，但桌面“雷达”冷启动右侧白边仍存在；白边尚未验收通过。模拟浏览器无横向溢出不能替代真机证据。

在已加载于八个入口及旧 PWA 入口的 home-launch.js 增加临时几何诊断，不调整任何样式、导航规则、报警、设备、推送或服务。仅触屏设备采集：屏幕、窗口、visualViewport、文档宽度、body/main 边界、安全边距、桌面模式及固定页面类别。不读取推送码、Bark Key、消息、完整页面 URL、查询参数或用户标识；请求禁止 Referer。

使用同源静态 JS GET 查询写入既有访问日志，不新增后台接口。每页最多 3 次、每标签页会话最多 18 次；2026-11-16 00:00 UTC 自动失效，存储不可用时跳过。仅在 DOM ready、1.5 秒、5 秒取样，测量元素立即移除，不轮询或监听滚动。

验证：12 项既有导航测试及 5 项诊断范围、到期、上限、隐私与异常测试通过。发布克隆当前版本，仅替换脚本引用并新增内容哈希 JS；保留其余资产、PWA 身份与 worker、规则绑定和服务进程。实际 iPhone 数据仍待采集；这是定位步骤，不是白边修复完成。

## 发布记录

已发布 `20261114-geometry-probe-1794650200091129630`，功能源码 `53e62cfcf735ad01e885f598c60d6a7627a1efc0`，上一版本 `20261114-home-launch-1794649579662311207`。仅新增 `home-launch-f640cd35727d2c4b.js` 并更换九个 HTML 引用（八个静态入口加旧 PWA fallback）；3569 其他静态文件、三个服务 PID、后台文件、报警规则/设备绑定、PWA manifest/worker 均保持。

3 号浏览器 820×1180 触屏模拟已收到 ready/settled/late 三条几何记录，服务返回 200；浏览器宽度 820，document.scrollWidth 820，临时模拟已清理。仅证明采样链路有效，不代表实体 iPhone 白边消失。等待用户设备刷新后采集，不重复盲改 UI。

真机已请求首版脚本，但未收到几何记录。移除诊断入口的 screen 长边过滤，并兼容 maxTouchPoints：可视窗口与 screen 的尺寸不能预先假定一致。只扩大诊断覆盖，不调整布局；仍需真实回执。

诊断覆盖调整部署：`20261114-geometry-probe-1794650513983844718`，源码 `862ceef7b5cf2aef093e10bcbd23aa2b9f3f5fc4`，脚本 `home-launch-8a77aba0ceb94978.js`。18 项测试通过，3570 其他资产、服务/后台/规则/绑定/PWA 均保持。此版本取消 screen 尺寸预筛选；真实几何数据未取得前不宣布原因或白边修复。

## 真机证据（18:02）

用户刷新后的 iPhone Safari 27.2 声明，installed 与 display-mode standalone 均为 true。初始/1.5 秒/5 秒记录一致：outerWidth 951，innerWidth 与 visualViewport.width 867，document/body scrollWidth 867；body left 0 / width 867；main left 16 / width 835；安全边距上/右/下/左为 0/0/34/0。窗口外层与网页可用宽度相差 84 CSS px，DPR 3 对应截图约 252 像素的右侧系统栏。没有网页水平溢出或右侧 safe-area padding。

screen 报告 466×678，不能代替已展开窗口的 951×669，因此首版诊断按 screen 长边至少 720 的过滤漏掉本机；这是诊断逻辑失误，不是用户未刷新。

WebKit 官方说明 Safari 27.1 的网页不能延伸到 Duo 侧边系统控件背后，背景由浏览器延续，viewport-fit=cover 进入此区仍在研究：https://webkit.org/blog/18486/webkit-features-for-safari-27-1/ （Web content under the controls）。结合本次 27.2 真机测量，可确认当前大片右侧占位不在文档绘制区域。尚需对照用户所述切页后消失的现象，不能声称已经移除系统栏，不能用拉宽/裁切内容伪装修复。
