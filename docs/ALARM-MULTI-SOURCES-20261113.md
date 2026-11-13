# 报警备用现货源多选

## 行为

只把新增/编辑表单的备用源单选改成复选框，电脑横排、手机3+2换行；没有增加说明或启用复选框。其他布局和CSS规则保留。保存fallbackExchanges明确名单，空数组关闭备用；主交易所不能列入，固定优先级Binance/OKX/Bybit/Bitget/Gate/Aster，健康备用保持，主源恢复规则不变。

旧规则不做数据库迁移，旧auto映射原五所范围（排除主所、不额外加入Aster）、指定映射单项、off映射空数组。编辑后多选名单权威优先，后端校验非法值/重复/主交易所。老页面没有名单字段时不能覆盖已多选的规则，要求刷新，防止旧客户端扩大备用范围。兼容单选字段对多选保存为off，回滚旧后端时宁可停止备用，不会扩大到未选源。

## 验收

93项Python及14项JS通过。六主交易所×32种子集，依次模拟所选源失效；未选源始终健康也不会被采用。真实Market.poll超时→Store.tick→队列：仅选Bybit/Gate，主源断流先Bybit，其失效后Gate，两者都失效则暂停，即使OKX等未勾选源正常。发送前重查和改勾选取消旧排队事件覆盖。多选名单下0/30/60秒真实send_event到Bark HTTP边界mock通过（未向真实手机发送）。

Store六所×BTC/ETH/SOL新增、编辑、数据库重新打开验证多项/空项/单项/全选保存。3号浏览器隔离真实Store/API共12次保存，覆盖Binance/OKX/Bybit/Bitget/Gate/Aster及BTC/ETH/SOL/PEPE。手机393px实际新增、编辑、刷新回显OKX/Gate，3+2换行无横溢；这是浏览器视口验收，非实体iPhone。正式规则和设备未用于测试。

发布脚本scripts/deploy-alarm-multi.py，仅替换4个静态文件并更新报警后端；保留其他线上文件、用户配置、设备及无关服务。健康版本11，fallbackMultiSelect=true。上线记录待补。
