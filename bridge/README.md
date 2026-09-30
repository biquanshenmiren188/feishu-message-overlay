# 本地官方长连接桥接

主界面已集成飞书官方 `@larksuiteoapi/node-sdk` 1.74.0，版本由package-lock.json固定。默认未连接。目标电脑需Node22或更新兼容运行时；程序不自动安装运行时。

`main.mjs`通过父进程私有stdin接收应用凭证、一至五个指定群ID及可选机器人ID。stdout为内部事件协议，不应重定向到日志；SDK日志关闭。凭证不通过命令行参数或环境变量传递。没有发送消息API或公开网络监听端口。

`filter.mjs`在正文读取前检查准确群ID、group类型、sender_type=bot、机器人白名单及时间基线。去重记录只留内存，30分钟窗口、最多10000项；过期清理、重连基线及容量/队列保护避免无限增长和历史重复报警。单个事件正文最大524288字符。

`OfficialBotSource.cs`负责子进程、100条有界队列与连接状态。传输就绪不证明消息权限或目标告警源已通过验收。普通成员消息被过滤。`im:message.group_msg.include_bot:read`覆盖机器人消息的应用身份事件；不能以只含用户消息的普通group_msg权限替代任务要求。

`register.mjs`提供官方用户确认流程，Secret仅通过私有IPC进入程序。用户显式选择保存并提交后，应用凭证由当前Windows用户DPAPI加密；源码和包不携带用户凭证。已有应用无需重复创建。

`discover.mjs`现在仅提供bot-only元数据诊断，不枚举群或读取消息。C#对协议做严格字段类型、应用身份、大小与时间限制，并只返回机器人名称、应用ID、启用状态及非敏感状态码。额外字段不会落盘。`diagnostic-fixture.mjs`只用于无凭证契约测试。

合成检查：`npm test --prefix bridge`。构建脚本还运行WPF私有管道测试和25项诊断契约。真实群事件、自定义webhook机器人、卡片解析与声音仍须实际验收。

外部群需要适用认证、对外共享与发布/审核。可入群不证明其他机器人事件必达；普通群成员事件也不满足机器人告警要求。平台规则参考：[接收消息](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive?lang=zh-CN)、[外部群要求](https://open.feishu.cn/document/develop-robots/add-bot-to-external-group)。
