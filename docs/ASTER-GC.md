# Aster 合约 GC 复制（2026-10-20）

桌面与 BOT 卡片的复制 GC 新增 `gc-aster`，只转换 Aster 合约，不能转换其现货。

FF 支持 Aster 位于任意一侧；SF 仅卖出的 Aster 合约转换，买入 Aster 现货保持普通平台；FS 买入 Aster 合约转换，借币现货腿保持普通平台和 `spotMarginType: cross`。不放开 Aster 现货借币卖出。绿色按钮依据最终双 GC 载荷判断。

验证：135 项 BOT 测试，420 项核心检查，桌面 WPF 真实复制按钮/剪贴板及 GC 边框契约通过，覆盖中文、倍率、买卖方向和 SF 现货保护。网站候选 bundle 与两侧源码 441 组逐字段一致。

本机安装版本含尚未归入 main 的既有消息摘要等功能，因此本机候选基于已安装源码 `f360caa` 仅应用本次 OpportunityBoard / OpportunityContract 改动，版本 `v2026.10.20.1`。本 PR 从 main 创建，仅包含此次改动。未发布正式 GitHub Release，未合并 PR。

网站定点发布脚本保存在 funding-radar 的 `scripts/deploy-aster-gc.py`，发布记录同时保存两仓功能提交。
