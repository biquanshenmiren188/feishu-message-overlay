# OKX GC 卡片复制修复（2026-10-14）

桌面与 BOT 网页的 FF GC 白名单遗漏 OKX，导致 WAL（买 OKX / 卖 Binance）、BLUR（买 HL / 卖 OKX）不显示“复制 GC”。雷达现有 GC 映射已包含 `gc-okx`；本次让两个卡片入口保持一致。沿用 FF、同币种、同计价单位验证，不扩大到未核实的交易所或现货模式。

复制输出分别为 `WAL / gc-okx / gc-binance`、`BLUR / gc-hl / gc-okx`，均使用 `ASTRO-QUICK-COPY:` 和 `type: FF`。普通复制保持原格式。待确认、已失效等展示状态不影响合法策略的 GC 复制。

## 验收

- 网页 85 项测试通过，覆盖 OKX 位于两条腿、全部已支持交易所配对、WAL/BLUR 输出及异币种/合约倍数/币本位拒绝。
- 桌面 95 项核心检查、64 项卡片检查通过；WPF smoke、诊断、云端窗口和协议、更新成功及失败回滚检查通过。
- WPF 实际渲染的合成 WAL/BLUR 卡片均显示按钮，保存 `artifacts/verification/opportunity-contract.json-okx-gc.png`。
- 线上 BOT 新模块用合成 WAL/BLUR 卡片验收，实际点击两个 GC 按钮，均显示“GC 已复制”，剪贴板逐字段吻合。测试页已关闭，不向生产数据写入合成卡片。

## 安装与发布

本机从 v2026.10.12.1 更新至 v2026.10.14.1，全部安装文件通过 manifest SHA256 验证。仅替换 exe、两个 PDB 和 manifest，保留 bridge、音频、配置和存储位置；更新后连接为 Connected，字号 13、透明度 1、背景透明度 0.95、自动更新关闭均与更新前一致。更新前后即时诊断均没有机会卡片，因此 WAL/BLUR 的视觉验收使用合成卡片，不冒充现场数据。

首次替换遇到退出进程暂未释放文件锁，确认进程已退出、原 exe 哈希未变后重试成功。旧文件备份于本次维护工作区 `work/gc-before-v20261014`。

BOT 发布为 `/opt/funding-radar-web/releases/20261014-gc-okx-cards`，从现行 `20261014-history-cache-recovery-v2` 完整复制，新增独立模块目录 `robot-push/web-session-gc-okx-20261014`，只改其中 GC 白名单和 BOT HTML 入口。发布锁内校验 1220 个其他文件未变后原子切换 current。新目录使浏览器不会继续命中旧模块缓存。服务、登录保护和订阅逻辑未变。

回滚时持 `/var/lib/funding-radar-storage/guard.lock`，确认 current 仍指向本次 release 后原子恢复上一 release。本机可恢复备份的四个文件。PR 依赖卡片续列分支，避免撤回用户已验收的布局。
