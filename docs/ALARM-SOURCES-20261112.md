# 报警币种统一与同币种现货备用行情（2026-11-12）

用户授权所有币种统一识别后断流自动切换，保留原界面。此变更只涉及云端报警及共用报警网页；Windows 消息小窗没有独立价格报警引擎，不替换其已安装的 v2026.11.12.3。

## 行为

- 原交易所/市场/交易对/价格类型和阈值全部保留。官方品种元数据提供 base、quote、unit，展示为 BASE/USDT；交易所及现货/永续仍显示在原位置。原交易对用于 API 请求和编辑。
- 主源有效且 12 秒内时使用主源。异常或超过 12 秒时，只选另一交易所同基础币、USDT 计价、同价格单位的现货最新成交价，优先 Binance、OKX、Bybit、Bitget、Gate。
- 所有币种走同一路由，不限 BTC；预热备用组。备用资格要求主备同时新鲜、三个不同请求样本、价格差在 5% 内。这是单位/异常行情保护，不是链上身份认证；依据交易所官方代码匹配，不能保证发现所有未知同名代币冲突。已知歧义代码拒绝自动备用，异名代币、数字前缀倍率合约、杠杆代币及股票类不自动转换；没有可确认备用时暂停价格判断。
- 原合约每张数量（OKX ctVal、Gate quanto_multiplier）不能当成价格倍率；1000PEPE 不删前缀映射成 PEPE。不会改变原阈值来伪装可比。
- 健康备用保持到主源连续三个不同的有效请求后切回；若备用也失败但主源已新鲜，则立即回主源。其他备用故障时依次寻找可用源。资格随规则状态持久化，初次加载需要三次主备样本，资格未形成时不会盲切；首次切换资格最长 24 小时。
- 切换不重置 lastFire / lastDispatch，仍遵守 30 秒持续提醒。一次性报警仍仅一次。发送前复核行情及排队事件来源；失效的尚未发送一次性事件重新进入等待，不永久锁死。
- 备用状态在原价格下增加一行实际来源，通知也明确现货来源和原交易对，不冒充永续或标记价。全源失效显示行情中断/—；本次未增加独立断流通知。
- 来源选择在服务端进行，各端不各自计算，不依赖浏览器/小窗打开。没有改动 BOT 置顶区、卡片、规则配置、设备密钥、订阅或旧 UI CSS。

## 官方依据

- Binance exchangeInfo：https://developers.binance.com/docs/binance-spot-api-docs/rest-api/general-endpoints
- Bybit instruments-info（分页/baseCoin/quoteCoin）：https://bybit-exchange.github.io/docs/v5/market/instrument
- OKX instruments（baseCcy/quoteCcy/uly/ctValCcy）：https://www.okx.com/docs-v5/en/
- Bitget symbols：https://www.bitget.com/legacy-docs/classic/spot/market/Get-Symbols
- Gate pairs/contract 计价：https://www.gate.com/docs/developers/apiv4/en/spot/

## 验证

- 77 项 Python 用例及 3 项精准搜索用例通过，JS 语法检查通过。
- 六所、现货/永续共十二组官方接口只读请求成功。BTC/ETH/SOL 的元数据和单位通过，PEPE 与 1000PEPE 保持分离。
- 真实现有 CSS、候选 JS、隔离合成规则：Chrome 手机 320/393px 无页面/卡片横溢，备用来源和全源失效正确。无真实推送、规则写入或生产断流注入。
- 发布使用 scripts/deploy-alarm-sources.py：锁内基线校验、只替换 3 个静态文件，克隆现行后端；只重启 radar-alarms，校验报警配置和设备哈希完全未变。支持原子回滚，不恢复覆盖用户数据库。

正式发布与三端回归结果在完成后追加。

## 正式发布与验收

- 功能源码 `3754023e0d80a5b100f8edce26beeada756a5503` 已推送。正式网页 `/opt/funding-radar-web/releases/20261112-alarm-sources-1794494007889713504`；后端 `/opt/radar-alarms/releases/3754023e0d80a5b100f8edce26beeada756a5503`。
- 回滚网页 `/opt/funding-radar-web/releases/20261112-pin-scroll-1794469624371215264`；后端 `/opt/radar-alarms/releases/efbbf93d051d31d0202e3430fead4e7400354c90`。保留其他 3556 个静态文件，未动无关消息服务；用户报警配置和绑定哈希完全一致。
- 线上健康版本 8，same-asset-spot-v1；只读核验两条启用规则均已统一币种、价格新鲜、正常主源监控，每条已有 4 个合格备用。日志无报警服务运行异常。
- 正式已登录 Chrome：app.js?sources1 加载，BTC/USDT 两条显示正确。1440px 桌面、393px/320px 手机视口无横溢，截图留在任务 outputs/alarm-sources-live-desktop.png 与 alarm-sources-live-mobile.png。页面布局/CSS未改；用户在此期间自行调整过其中一条阈值，发布保留真实配置，不恢复旧截图阈值。
- 手机检查是浏览器手机视口，不是实体 iPhone 实测。切源故障验证在隔离数据上完成，没有中断生产行情、发送测试通知或改真实规则。
- 桌面小窗无独立价格报警引擎，云端更新不要求安装或打开。为核验主动启动过现有软件，用户认为多余；已解释并停止窗口操作。此后仅静态核对版本和代码，不声称已完成本次原生窗口视觉验收。
- PR #70 已推送更新，尚未合并。已安装小窗版本不变。
