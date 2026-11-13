# 报警备用现货源多选

## 行为

只把新增/编辑表单的备用源单选改成复选框，电脑横排、手机3+2换行；没有增加说明或启用复选框。其他布局和CSS规则保留。保存fallbackExchanges明确名单，空数组关闭备用；主交易所不能列入，固定优先级Binance/OKX/Bybit/Bitget/Gate/Aster，健康备用保持，主源恢复规则不变。

旧规则不做数据库迁移，旧auto映射原五所范围（排除主所、不额外加入Aster）、指定映射单项、off映射空数组。编辑后多选名单权威优先，后端校验非法值/重复/主交易所。老页面没有名单字段时不能覆盖已多选的规则，要求刷新，防止旧客户端扩大备用范围。兼容单选字段对多选保存为off，回滚旧后端时宁可停止备用，不会扩大到未选源。

## 验收

93项Python及14项JS通过。六主交易所×32种子集，依次模拟所选源失效；未选源始终健康也不会被采用。真实Market.poll超时→Store.tick→队列：仅选Bybit/Gate，主源断流先Bybit，其失效后Gate，两者都失效则暂停，即使OKX等未勾选源正常。发送前重查和改勾选取消旧排队事件覆盖。多选名单下0/30/60秒真实send_event到Bark HTTP边界mock通过（未向真实手机发送）。

Store六所×BTC/ETH/SOL新增、编辑、数据库重新打开验证多项/空项/单项/全选保存。3号浏览器隔离真实Store/API共12次保存，覆盖Binance/OKX/Bybit/Bitget/Gate/Aster及BTC/ETH/SOL/PEPE。手机393px实际新增、编辑、刷新回显OKX/Gate，3+2换行无横溢；这是浏览器视口验收，非实体iPhone。正式规则和设备未用于测试。

发布脚本scripts/deploy-alarm-multi.py，仅替换4个静态文件并更新报警后端；保留其他线上文件、用户配置、设备及无关服务。健康版本11，fallbackMultiSelect=true。

## 正式发布

源码4c30f93c35dabc0da2306fb0668c92a66a5a60ee，网页/opt/funding-radar-web/releases/20261113-alarm-multi-1794540390144446058，后端/opt/radar-alarms/releases/4c30f93c35dabc0da2306fb0668c92a66a5a60ee。回滚网页/opt/funding-radar-web/releases/20261113-alarm-form-1794539603043523314、后端/opt/radar-alarms/releases/535c9bccfa8439c983239962d8e5dd1237579b3c。服务器两轮93项测试通过；仅重启报警服务，3557其他静态文件、无关服务、用户配置及设备绑定保持。

正式3号浏览器新增和编辑均显示正确勾选，旧auto未扩张到Aster；电脑横排、393px手机3+2无横溢，关闭无确认。截图outputs/alarm-multi-live-desktop.png、outputs/alarm-multi-live-mobile.png。正式已有2条报警仍启用监控，实际保存流程在隔离真实Store完成12次，未修改真实规则或发送测试通知。视口恢复、隔离服务停止。GitHub PR70待合并。

## 线上同版发送链路复核

用户再次要求确认备用不仅显示切换。新增可重复的隔离验收脚本scripts/verify-selected-backup-delivery.py，并在正式服务器导入current指向的4c30f93全部实际模块运行；核对7个模块SHA与发布源码一致。12种场景（Binance/OKX主源 × BTC/ETH/SOL × 涨到/跌到）全部通过。

脚本使用临时SQLite和虚拟时间，真实Market.poll→Store.tick→claim→send_event→begin_send→Bark POST构造→finish；仅模拟交易所行情和Bark外部HTTP。仅勾Bybit/Gate，主源超时后首次Bybit；Bybit超时后Gate；首次触发后0、30、60秒各一次请求，29/59秒不发，载荷包含实际备用来源和触发价格及critical/volume5/call1。价格恢复停止，排队后行情失效取消，所有勾选备用失效时不使用仍健康的未选源。报告work/selected-backup-delivery-live.json，生产规则/绑定摘要及服务PID前后保持。未重启或部署业务代码。

边界：这是正式代码的隔离发送链路验证，Bark响应模拟200；不能把此结果称为真实Bark已接收或用户手机已收到/响铃。

## 实体手机实际验收（2026-11-13，北京时间）

用户明确授权真实推送3次、间隔30秒、模拟主源断流且不得动原报警。使用scripts/accept-selected-backup-phone.py，导入正式4c30f93模块，在临时数据库内复制规则和加密接收绑定；生产库仅只读。模拟Binance主源超时，按该规则允许名单OKX/Bybit/Bitget/Gate切到OKX现货，测试价65999达到跌到66000条件。每条通知明确标记“断流验收n/3”和非实时价格，真实send_event向Bark HTTPS发送，每条一次，无重试。

- 1/3：12:19:36.655，Bark accepted。
- 2/3：12:20:06.680，间隔30.025秒，Bark accepted。
- 3/3：12:20:36.718，间隔30.038秒，Bark accepted。

用户随后明确回复“三条都收到并响铃，间隔约30秒”，因此本轮具有实体手机收件/响铃确认，不只是接口成功。12:20:37恢复模拟行情，12:20:41切回Binance主源，继续观察32秒，恰好3条事件、没有第4条。临时规则/数据库已自动清理；前后生产规则、配置、设备绑定摘要完全一致，原报警未改，未部署或重启服务。实际报告work/actual-phone-acceptance.jsonl；该文件含发送时间与匿名测试状态，不含设备Key。测试脚本仅显式--send-three运行，单次标记阻止盲目重复。

## 多币种和六交易所完整发送链路扩展

再次核对正式current 4c30f93的7个模块哈希并导入运行扩展脚本，84场景全部通过：Binance/OKX/Bybit/Bitget/Gate/Aster六主源 × BTC/ETH/SOL/DOGE/XRP/PEPE/JCT七资产 × above/below两条件。每组包含勾选两备用、主源超时→第一备用→备用再次超时→第二备用，实际send_event构造0/30/60秒Bark请求、29/59秒无重复、价格恢复停止、发送前行情失效取消和禁止未勾选源。报告work/multicoin-delivery-live.json。使用临时DB/模拟行情和BarkHTTP，无新手机通知或生产改动。

这是通用路由/报警链路验证，不证明上述每个币都真实上架每家交易所，也不表示各组合均实体手机收件。实际可切换仍需官方交易对身份一致、同USDT价格单位、有效现货、3次校验、12秒新鲜度等条件。倍率币如1000PEPE不能自动当PEPE，身份歧义/无合格现货时暂停判断。实体手机三次收件的确认仍对应前述BTC单场景；发送模块为共用模块。
