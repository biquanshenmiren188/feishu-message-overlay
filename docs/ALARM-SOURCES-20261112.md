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

## 新增/编辑选择器补齐（2026-11-12）

用户发现新增报警原生 datalist 仍显示 BTC-USDT-SWAP。此次补齐 options value、输入值及编辑回填统一 BASE/USDT；保存时通过当前交易所目录唯一解析回原始交易对 q.symbol。支持精确基础币、统一币对及旧原始代码输入；多个品种同一显示身份时不静默取第一条。不同计价/包装币/倍率币不合并。

五项精准匹配/解析测试和 JS 语法检查通过。隔离浏览器实测 OKX 输入 BTC → 选项 BTC/USDT → 保存请求仍为 OKX BTC-USDT-SWAP；编辑回填 BTC/USDT，393px 弹窗无横溢。纯静态部署脚本 scripts/deploy-alarm-picker.py 只修改 app/search/index，不重启报警和消息服务、不打开或更新软件、不修改真实报警或测试推送。

选择器补丁已发布：源码 `36d9a28c05799810b38b5e84499945a8d873f982`，网页 current=`20261112-alarm-picker-1794494633098765897`，回滚=`20261112-alarm-sources-1794494007889713504`；后端仍为 3754023，三个服务 PID 均未变，保留3556其他静态文件。
正式已登录页面确认加载 picker1，OKX 搜索 BTC/ETH 的 datalist value 分别为 BTC/USDT、ETH/USDT，393px 弹窗无横溢。截图 outputs/alarm-picker-live-desktop.png。编辑统一回填和原始交易对提交由隔离环境验证；正式编辑入口追加检查受浏览器控制超时影响，不计为完成。未保存真实规则、未发送通知、未操作桌面软件。

## 新增、编辑可选备用源（2026-11-12）

- 原表单只增加一项「备用现货源」：自动选择、关闭备用切换、指定其他交易所。自动保持原优先级；指定支持 Binance、OKX、Bybit、Bitget、Gate、Aster，排除与主源同所。没有同币种现货或合格新鲜数据时暂停判断，指定模式不私自改用第三家。倍率币、包装币及歧义保护仍生效。
- `fallbackExchange` 随规则新增、编辑、保存、重启持久化；旧规则缺省为 auto，不批量改用户配置。切换主交易所与已选备用相同时恢复自动选项。
- 关闭按钮、取消和 Esc 直接丢弃未提交编辑，不再弹「放弃尚未保存的修改？」；正在提交时仍防止误关。离开网页及切换账号的未决请求保护保持。
- 81 项 Python、5 项 JS 测试通过。Store 矩阵覆盖六所 × BTC/ETH/SOL/PEPE/1000PEPE/WBTC 六种合成身份，各自新增及全部可选备用编辑保存；不宣称每家真实上市全部测试资产。
- 浏览器使用真实 Store 的本地隔离表单：六所分别新增保存，共六条；六条逐一编辑回填指定备用并再次保存，手机另保存一次，共 13 次成功写入。原始代码保持 OKX `ETH-USDT-SWAP`、Gate `1000PEPE_USDT` 等；未保存的三种关闭操作无对话框，重开保持原阈值。
- 393px 和 320px 手机视口无横溢，选择、保存、回填及关闭通过；CSS 未改。没有操作真实规则、发送通知或打开桌面软件。部署使用 `scripts/deploy-alarm-choice.py`，健康版本 9 / same-asset-spot-v2。

### 可选备用源正式发布

- 功能源码 `8fd8060ca8d890756b30cc833cc2942654a89637`，网页 `/opt/funding-radar-web/releases/20261112-alarm-choice-1794495596818070394`，后端 `/opt/radar-alarms/releases/8fd8060ca8d890756b30cc833cc2942654a89637`。
- 回滚网页 `20261112-alarm-picker-1794494633098765897`，后端 `3754023e0d80a5b100f8edce26beeada756a5503`。仅重启报警服务，3556 个其他静态文件、消息服务 PID、报警配置、设备绑定及推送设置均保持。
- 正式 Chrome 已登录页加载 fallback-choice1：编辑旧规则回填 BTC/USDT 和 auto，改选后 X 直接关闭，重开原设置未变；新增 Bybit ETH/USDT 取得当前行情，可选 OKX 现货。取消及 Esc 均无二次确认，未提交真实修改。
- 桌面 1991px、手机 393px/320px 页面与弹窗无横溢，截图 outputs/alarm-choice-live-desktop.png、alarm-choice-live-mobile.png。手机为浏览器视口检查，非实体 iPhone。
- 只读验收 version 9 / fallbackSelection=true；两条启用规则均为新鲜主源行情、监控中，每条已有四个合格备用。日志未见运行异常。GitHub 分支及 PR #70 同步，待合并。
