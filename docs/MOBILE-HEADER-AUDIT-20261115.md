# 全导航页切换、刷新和手机页头验收 · 2026-11-15

范围：全市场费率、机会筛选、充提查询、HY限额查询、BOT、消息设置、报警设置，以及报警记录。仅处理页头对齐。

正式站桌面 1440 CSS px 逐页点击并刷新：Logo x≈18、y≈5.7、154×46；导航 x≈18、y≈68、607×40，均一致且无横向溢出。

手机检查发现：主站 Logo 138×42，其他页 150×45；主站导航 y≈62，HY y≈52、BOT/设置/报警 y≈58；账号加载前后也可能改变页头高度。

## 修复

仅 web/robot-push/mobile-compact.css 的 <=700px 页头规则：
- 独立页面页头统一 52px，应用于账号初始化前后；Logo 138×42，与主站相同。
- 独立页面与启动框架导航上边距 10px；React 导航沿用父容器间距，不叠加。
- 报警页手机滚动条预留与公共页面一致，避免导航宽度在有无滚动条时变化。
- 其他页面内容、卡片、列表、字号和桌面规则均不改。

## 证据与边界

3号 Chrome 正式站先完成电脑页切换刷新测量。浏览器连接中断后改用 Windows Computer Use，独立验收窗口，未操作其他用户标签页。

生产 HTML/CSS 静态副本（移除业务脚本）在真实 Chrome 中检查 8页×4宽度（320/393/867/1440）共32组，各宽度 Logo 与导航坐标和尺寸一致；整页刷新重跑32组，结果逐项相同。手机正式站再用400px设备视口逐页点击及刷新上述8页，观察加载前后，Logo 与导航位置一致。手机是浏览器模拟视口验收，不是实体 iPhone Safari 实测。

线上 CSS 回读 SHA256 与提交内容一致。nginx /radar/ 静态资源设置 Cache-Control: no-cache，原 URL 重新校验获取此次样式。未修改 worker/PWA身份或原 HTML。

部署守卫验证三个后台服务 PID、后台版本、设备绑定和报警配置摘要保持，保留3581个其他静态文件；未发真实通知。浏览器设备模拟已关闭，独立验收窗口关闭。

## 发布与回滚

{
  "release": "/opt/funding-radar-web/releases/20261115-mobile-header-1794750061757059419",
  "previous": "/opt/funding-radar-web/releases/20261115-header-align-1794723893607048616",
  "backend": "/opt/radar-alarms/releases/470e731715cf77e228e2c32e966f237c534df474",
  "source": "c876a4e0bbdc90873598bfbd99f9e125e1cd998f",
  "allServicesUnchanged": true,
  "rulesAndBindingsPreserved": true,
  "preservedFiles": 3581
}

回滚仅需原子切回 previous；不重启服务。PR #70 保持未合并。
