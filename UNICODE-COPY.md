# 中文币名策略复制修复（2026-10-15）

“龙虾” Gate 现货 / Binance 永续卡片原先被 ASCII-only 币名校验拒绝，CopyStrategy 返回 null，按钮退回复制整张卡片文本。桌面和 BOT 现改为允许 Unicode 字母及十进制数字，保留原币名；两腿标的一致、合约倍数、USDT 计价、市场方向、支持交易所的检查仍然有效。GC 仍仅支持两边均在既有白名单内的 FF，不增加交易所。

实际输出：

```text
ASTRO-QUICK-COPY:
{
  "type": "SF",
  "name": "龙虾",
  "buyEx": "gate",
  "sellEx": "binance"
}
```

## 验收

- 22 项 BOT 卡片测试通过，包括中文 SF/FS/FF、OKX 格式，以及不同币名、倍数、空格/换行/脚本标记拒绝。
- 95 项核心检查、WPF 冒烟、72 项桌面机会卡片检查、云端读取/窗口契约和四种更新流程通过。
- 真实 WPF 卡片按钮 Click 事件写入系统剪贴板，再读回并严格比较上述内容；验收使用与用户截图同币名和方向的合成卡片。恢复原剪贴板遇到短暂占用时有界重试，最终完整报告通过。
- 构建脚本增加机会卡片报告 passed 校验，避免进程提前 Shutdown(0) 掩盖报告失败。
- 已核对已有 Astro 前端导入器：ASTRO-QUICK-COPY 前缀和 JSON name 字段支持中文。未在交易账户内创建策略或下单。
- 正式站“龙虾”推送消息可见，但活跃卡片已过期；没有声称重新点击了消失的线上卡片。下载已发布模块回放同组合，输出正确。

## 发布

桌面安装 v2026.10.15.1，替换 EXE/PDB/manifest 四个文件，完整文件清单 SHA256 校验通过。旧程序短暂文件锁释放后重试成功。原配置保留，重启诊断确认 updateVersion=v2026.10.15.1、state=Connected、opportunitySourceConnected=true、isVisible=true。原文件备份在工作区 work/unicode-before-v20261015。

腾讯云 BOT 定点发布 /opt/funding-radar-web/releases/20261015-unicode-card-copy，前版 /opt/funding-radar-web/releases/20261015-combination-load-cache-v2。新命名空间 robot-push/web-session-unicode-copy-20261015，只改币名正则与入口引用；验证 1422 个其他文件未变，保留组合页加载优化。模块 SHA256：340ae16295993d9cb16bd8db33f54d3a77243879b1210c344be25ef5c208b39b。

回滚网站须确认 current 仍为本版，在 /var/lib/funding-radar-storage/guard.lock 内原子指回前版；桌面退出安装程序后恢复备份四文件。代码依赖 PR12 的 OKX GC 修复，独立 PR 以该分支为基线。

## 合并前 CI 复核

首次 GitHub Windows 检查暴露旧机会布局测试依赖宿主显示器高度：云端原生窗口被小屏幕限制，无法达到假设的 1100 DIP。改为在 Canvas 中提供明确的逻辑测试视口，继续严格验证 1100 高度两列、600 高度三列及窄屏滚动；真实窗口检查依据可用屏幕列数验证边界与消息区宽度。失败报告直接进入控制台，不依赖已达配额的 GitHub artifact 存储。剪贴板测试读回增加有界占用重试；业务复制逻辑不变。本地 72 项卡片检查再次通过。
