# 手机 BOT 阅读位置回归

这个诊断复用抓取的生产 HTML、CSS、JavaScript 依赖图，仅在页面运行前注入合成行情、消息和规则响应。它不重建旧页面、不连接生产 API、不发送通知，也不使用真实推送码。源文件和报告中的 `SYNTHETIC-LOCAL-FIXTURE` 只属于本地服务。

## 启动相同 fixture 的基线与候选

从仓库根目录执行（Python 3.10+）：

```powershell
python scripts/mobile-reading-fixture/serve.py --baseline ../mobile-reading-live-baseline --port 8099
python scripts/mobile-reading-fixture/serve.py --baseline ../mobile-reading-live-baseline --overlay ../mobile-reading-draft-01 --port 8100
```

分别打开：

- 基线：`http://127.0.0.1:8099/radar/robot-push/`
- 候选：`http://127.0.0.1:8100/radar/robot-push/`

候选优先读取 overlay 中的文件，其他资源仍来自同一基线。更换候选目录后重启对应服务，避免已读取的入口 HTML 继续引用旧文件。服务只监听回环地址；脚本拦截合成 API，拒绝其他域的 fetch，CSP 另外限制连接、worker、图片和媒体来源。除写入明确的本地合成报告外，服务器只读文件，无部署、外部发送或服务重启操作。

将浏览器设为手机宽度，例如 393×852。超过 900px 时手机场景会明确跳过，不能把电脑独立滚动面板的结果判成手机问题。页面底部的诊断控制台使用固定定位，不占据文档高度。

## 操作与覆盖

选择场景后点击“定位并开始”。fixture 会定位到 `pair-4`，等待 600ms，再运行相同合成动作。每个独立场景后点击“重载基线”重置。可选择新消息、30条裁剪、置顶增高、新卡排序、卡片 replaceWith 增高、同 pair 更换 ID、上方卡过期、消息/卡片规则屏蔽与回流。

“卡片规则503清空→下一轮恢复”让下一次真实 `card-decisions` 调用返回503，再等待原有3秒轮询成功。它覆盖临时删除全部卡片引发的文档高度收缩，不把仅发送规则事件或短暂延迟当作已经发生删除。

“合成touch活跃+规则503/恢复”产生确定性的非 trusted touch 及 scroll 事件，用于检验 gate 活跃时的 DOM 几何变化。这是程序事件回归，不代表系统触摸惯性。

“真实触摸惯性+规则回流”先定位并等待用户在卡片区域实际滑动；松手后32ms触发规则失效/回流。实际手势会正常改变 scrollY 与卡片 top，因此此场景只提供完整轨迹，不套用静止阅读通过标准。

“批量9例静止场景”依次运行并重载页面，约80–95秒。进度存入当前本地 origin 的 sessionStorage；每例完成后先递增索引再重载，最后清除进行中状态并在 DOM 输出全部汇总。选择框可能显示默认选项，执行场景以状态文字和报告 `scenario` 为准。

## 证据与判断

每个 rAF 都记录 scrollY、原 pair 的位置或不存在状态、文档高度、消息框和卡板高度、VisualViewport、gate 状态与输入版本。不存在卡片的帧不会丢弃。MutationObserver 另外记录原页面 DOM 修改后的几何状态；没有改写页面的 DOM 原型方法来强制每次修改中途布局。

- 普通静止场景：实际动作必须发生，目标卡每帧位移不超过2px，且没有缺失帧。
- 503类：必须观察到503和缺失帧，验证规则失效立即移除内容；缺失期间及其他帧的 scrollY 偏差不超过2px，恢复后的卡片位置也不超过2px。
- 同时报告 `maxFrameScrollDelta`、`missingScrollRange`、`maxRootHeightDrop`，不能只看最终 scrollY 恢复便判定没有跳动。
- 上方正常插入/移除可能需要调整 scrollY 来维持卡片位置，所以普通场景不一概要求 scrollDelta 为零。
- 页面错误保留 stack/source 并影响结果；仅明确来自 `chrome-extension://` 的错误单列为 `excludedExtensionErrors`，不隐去原记录。

点击“下载逐帧JSON”保存单例完整帧和事件。批量完成后同一按钮保存全部单例 summary，包含几何极值、动作验证、错误和基线/候选 provenance；如需某一例完整帧，单独运行并下载。下载文件属于本地合成诊断证据，建议放到任务 `outputs/` 目录，不提交抓取的生产资产、原始 API 数据或用户凭据。

当前脚本不能证明实体 iPhone/Safari 的触摸惯性或地址栏行为已验收。Chrome 手机视口和程序 touch 均须据实标注；实体 iOS 应另外执行真实手势场景并记录设备/系统版本。


每个已完成案例还会 POST 到同一回环服务的 `/__fixture-report`，保存完整合成帧；批量运行每一例之后保存 `suite-progress`，最后保存 `suite`。因此页面后续失联不影响之前完成的证据。默认写入基线目录旁的 `mobile-reading-fixture-evidence/<端口>/`；可用 `--out <目录>` 指定，文件名包含唯一时间和场景名，日志打印实际路径。该接口只接收标记为合成诊断的 JSON，大小限制10MB，不接收生产 API 数据；这些报告是本地测试产物，不进入生产，也不提交到仓库。

若服务尚未更新而页面使用了新增上报脚本，报告中的 `evidenceError` 会明确说明保存失败；静止几何结论仍由逐帧证据决定。重启服务后重新运行需要留档的案例。服务启动时读取入口 HTML，因此候选更新后不能只刷新页面，须重启对应端口服务。
