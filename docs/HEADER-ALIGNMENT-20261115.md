# 页头对齐修复 · 2026-11-15

报警页在共享 `scrollbar-gutter: stable` 之外使用了 `stable both-edges`，使桌面页头和导航比主站、BOT、消息设置右移一个滚动条宽度。改为单侧 stable；手机断点原规则保留。消息设置本身与共享页头一致，不改其 UI。

仅发布报警 compact.css 与 index.html/history.html 的 CSS 缓存版本。没有修改应用 JS、后台、设备绑定、报警规则或发送队列。

## 验收

使用 3 号浏览器验证服务器实际页面 HTML/CSS 的本地静态副本（去掉脚本，防止通知或配置操作）。生产域名的浏览器会话已过期，未声称通过登录后的在线交互验收；发布后通过 SSH 回读三个资产并逐项校验 SHA-256。

- 1440、1920 CSS px：主站、BOT、消息设置、报警设置的页头 x=0，导航 x≈18；图片 Logo 的 x≈18，报警记录一致。
- 393、867 CSS px：导航 x≈12，各页对应 Logo 横向基准一致，没有横向溢出；手机规则未改变。
- 刷新后定位保持。修复前报警 Logo/导航 x≈33.14，其他页面 x≈17.99；修复后一致。
- 部署守卫验证绑定和报警配置摘要不变、三个服务 PID 不变、后台版本和 PWA fallback 不变；其他 3579 个静态文件保留。
- 后台健康检查正常，version 15、multiDevice、fallbackMultiSelect、denominationConversion、repeatIntervalSeconds=30 保持。
- 本次没有发送真实通知。

## 发布

{
  "release": "/opt/funding-radar-web/releases/20261115-header-align-1794723893607048616",
  "previous": "/opt/funding-radar-web/releases/20261114-alarm-preview-1794667551331093060",
  "backend": "/opt/radar-alarms/releases/470e731715cf77e228e2c32e966f237c534df474",
  "source": "81b80bc9ad4a1ef6a68ec4a117cbecb9ef0e4d54",
  "allServicesUnchanged": true,
  "rulesAndBindingsPreserved": true,
  "preservedFiles": 3579
}

回滚：将 /opt/funding-radar-web/current 原子切回 previous；无需重启服务。GitHub PR #70 保持未合并。
