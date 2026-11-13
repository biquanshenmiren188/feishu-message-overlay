# 倍率币报警备用源（2026-11-13）

此前路由直接排除数字前缀，1000PEPE 主源断流不能使用 PEPE 现货。本次只修改后台身份/单位路由；网站、手机版和软件页面的 HTML/CSS/JS 不改，用户原规则、阈值和设备不改。

## 单位和身份

- `denominations.py` 是逐交易所、市场、原生交易对的审阅表，45 个倍率合约，17 个资产族。不是删数字前缀，不以行情价格比例猜币种，不将 ctVal、quanto_multiplier、priceScale 当价格倍率。
- 支持 1000PEPE、SHIB1000、10000SATS、1000000MOG、1MBABYDOGE、1000000BABYDOGE、1MCHEEMS 等已列入表的单位；可在表内查看完整范围。正常命名的 1INCH/0G/4 不会被剥掉数字。未审阅的名称不能凭相似字符串合并。
- 每次匹配仍要求该所实时官方 instrument 元数据存在且交易中，原生 symbol、base、USDT quote、unit 均完全一致；停牌、缺失、同名不同身份、非 USDT、包装币均不能代替。
- 公式：**用于报警的价格 = 备用现货原价 × 主规则每单位币数 ÷ 备用源每单位币数**。Decimal 80 位中间精度，无浮点转换。原行情对象不修改。
- 例如 1000PEPE 主规则：PEPE 现货 0.0000039 → 0.0039 USDT/1000PEPE，和原阈值 0.004 比较。Bybit 10000SATS → Binance 1000SATS 只乘 10；1000CAT → Binance 1000CAT 乘 1；反向从 CHEEMS → 1000CHEEMS 现货除以 1000。
- 标题/规则仍显示原生单位；事件和推送在现有来源行注明非 1 倍换算及目标单位，避免读者把换算后的价格误当单币价。没有新增 UI 帮助段落。

## 审阅依据和边界

- [Binance 官方指数成分 API](https://fapi.binance.com/fapi/v1/constituents?symbol=1000PEPEUSDT) 明确列出 `PEPEUSDT*1000`、`PEPE-USDT*1000` 等交易所/现货/倍率关系。
- [Binance SHIB 合约公告](https://www.binance.com/en/support/announcement/detail/fa934b93fea6494fb7361d45ca7cc98a) 说明 1000 SHIB 单位。
- [Bybit 指数成分文档](https://bybit-exchange.github.io/docs/v5/market/index-components) 明确给出 `spotPair` 和 `multiplier`。实时返回核对了 SHIB1000、10000SATS、1000000BABYDOGE、1000BTT（Binance 现货 BTTC）和 1000NEIROCTO（Binance 现货 NEIRO）的具体别名。
- [Bitget 指数成分文档](https://www.bitget.com/legacy-docs/uta/public/Get-Index-Components) 返回的是成分显示名和 equivalentPrice，不保证其显示名等于现货接口原生 symbol，不能盲目用 `1000BONK/USDT` 拼出现货交易对。Bitget/Aster 倍率合约采用显式审阅别名表，结合其官方 contracts/exchangeInfo 核对实际合约和原生单位；不会从另一家新增符号自动扩展。
- [Aster 官方 API 文档](https://github.com/asterdex/api-docs)、[指数说明](https://docs.asterdex.com/trading/perpetuals/fees-and-specs/mark-price-1)。其 exchangeInfo 存在 9 个本表倍率合约，未使用不存在的 constituents 接口。指数成分及倍率审阅公共快照见 `fixtures/alarm-denomination-evidence-20261113.json`；跨市场价格仅作额外合理性校验，不独立充当身份依据。
- 特别发现 Bybit 的 1000CAT 成分把 Binance 已放大的 1000CATUSDT 也标 multiplier=1000。直接套用会重复放大；这里使用审阅后的 Binance 原生现货单位 1000，所以该路径 factor=1。
- 这不是承诺任何同名币或未来新上架合约都自动可切。10000NEX 的指数成分没有返回身份资料，本次没有猜映射。需补充可核对资料后加入审阅表。

## 路由和推送

仅检查用户勾选的其他交易所现货；不回退到未勾选源。正常主源优先，候选按换算后价格进行原有三次独立样本校验；两源须新鲜且价格偏差在原有范围内。已验证候选才在断流时接管；主源恢复三次后切回。源全失效暂停，不能用 0 或过期价触发。

换算单位、倍率、资产 ID、注册表版本进入候选资格键和队列来源键。换单位/撤销勾选/更新映射不会复用旧资格或发送旧单位事件。`Store.tick`、页面 state.price、`begin_send` 和实际 Bark sender 共用同一选源和换算结果。持续报警仍按 30 秒节奏，切源不重置节奏。

## 验证

- 98 项 Python 测试通过。包括 266 个逐倍率合约 × 各可选审阅现货 × 涨/跌场景，以及 6 个反向倍率场景，共 **272 组实际 Store → sender HTTP 模拟**：新增、编辑、保存、重开数据库、主源断流、换算后触发、0/30/60 秒发送、发送前条件解除取消、全断流暂停、恢复主源、阈值和配置不变。
- 原来六所 × 七个普通币 × 涨/跌的 84 组完整测试仍通过；不只检查 BTC。
- 真实官方接口只读采样：六所十二组均成功；45 个当前挂牌倍率合约找到 133 条审阅现货候选。其中当时 94 条完成三次预热并在私有数据副本模拟断流后切换；39 条未满足预热条件，未伪装成通过。真实数据结果不替代隔离断流测试。
- Chrome “3号” profile（ID4）隔离环境：1000PEPE 新建选 OKX，阈值 0.004；主源断流后页面显示 0.0039000 和持续报警。393×852 编辑只选 Gate，保存、刷新后保持 Gate 和原阈值/倍率单位；页面无横向溢出。使用原 HTML/CSS/JS，公共样式补齐后保存截图。
- 本轮未真实发送手机消息。此前 BTC 的三次实体手机收件/响铃确认保持独立证据，不能宣称此次 272 组都实体收件。

## 发布

使用 `deploy-alarm-denominations.py` 只替换报警服务后台并重启该服务，锁定基线、检查全部静态文件哈希、配置与绑定摘要和无关服务 PID。健康版本 12 / same-asset-spot-v3。实际提交、部署路径和上线后检查在发布后补录。
