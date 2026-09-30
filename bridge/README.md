# 本地官方长连接适配器（已集成，默认未连接）

使用飞书官方 `@larksuiteoapi/node-sdk` 1.74.0，依赖版本和完整性在 package-lock.json 中固定。需要 Node 22 或兼容运行时；当前便携包含WPF和桥接依赖；Node22需本机现有安装，不会自动安装或改变系统配置。此适配器已经连接到 UI，用户在本机受保护输入界面提交已授权应用和指定群后才能建立真实连接。

`main.mjs` 仅通过父进程匿名 stdin 管道接收 appId/appSecret 和一至五个核验过的 chat_id。不得从终端直接传密钥、不得写配置文件、不得将 stdout 重定向到日志。stdout 是私有进程间协议；SDK 所有日志被关闭。没有发送消息 API，也没有公开监听端口。

`filter.mjs` 在读取 content 前检查群 ID、group 类型、sender_type=bot、发送者 ID、消息时间。去重记录保留在内存，官方 SDK 重连期间保持同一个 gate，重启/重新启用以当前时间作为新基线。去重窗口30分钟、最多10000条；超限或 IPC 拥堵停止连接而非驱逐近期 ID 导致重复报警。限制消息体最大524288字符。

`OfficialBotSource.cs` 启动上述进程，凭证不进入命令行/环境变量/文件，队列最多100条，状态使用官方 onReady/onReconnecting/onReconnected/onError。连接成立不代表消息权限已通过。该类已由主界面调用；用户明确提交已授权应用和准确群ID后启动，不默认建立连接。

纯合成测试：`npm test --prefix bridge`，无需凭证/网络。官方 SDK已下载并静态核对回调 API，真实握手、权限撤回、其他机器人的卡片格式、五群现有机器人（包括自定义webhook机器人）覆盖均未实测。

权限依据：[接收消息](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive?lang=zh-CN)。需 `im:message.group_msg.include_bot:read`，接收其他机器人和用户消息，排除监听机器人自己。本软件在本机再次筛选机器人，普通用户不显示/不提醒。不要仅用 `im:message.group_msg` 代替。
