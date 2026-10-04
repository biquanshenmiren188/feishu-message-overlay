# 专用签名发布协议

采用.NET原生ECDSA P-256/SHA256，RFC3279 DER签名；服务器Python标准库HTTPServer调用系统OpenSSL验签。正式私钥只在本机程序内部生成、当前用户DPAPI加密保存，解密后不输出。服务器只接收SPKI公钥。测试钥独立临时生成，私钥不导出。

签名原文为UTF8以下各行，以LF连接，无末尾换行：协议标识`robot-push-v1`、`POST`、固定路径`/radar/api/robot-push/publish`、Unix秒、32位小写十六进制nonce、请求原始body的SHA256小写hex。请求头为X-Publish-Key（SPKI DER SHA256前16位hex）、X-Publish-Time、X-Publish-Nonce、X-Publish-Signature（DER Base64）。

服务验证时间偏差60秒、签名、固定字段schema、群范围、senderType=bot、安全HTTP(S)链接。nonce保存SQLite防重放125秒；每分钟最多30个成功请求。512KiB请求上限，每批最多8条，每条正文16000字符。nginx另有限流与请求体限制。签名证明发布者身份，不独立证明源飞书事件真实性；本机接收器先按官方sender type与已授权群筛选。

本机批量发送最小间隔2.1秒，空闲20秒签名心跳，网络错误指数退避至60秒，不在UI线程发送。服务器返回ackIds/pinAck；消息ID去重，公开ID为本机群/消息ID摘要，不输出原始sender ID。普通100条/30分钟，置顶独立1条，快照上限2MiB。服务器原子替换公开快照，不记录正文日志。完整保留与离线边界见DEPLOYMENT.md。

仅精确发布POST与公开快照GET暴露在原HTTPS站点。服务绑定回环，专用低权限账户，MemoryMax96MiB、CPUQuota10%、TasksMax8；没有新公网端口、Feishu App Secret迁移或额外飞书长连接。

`contract_test.py`在服务器使用真实OpenSSL；`contract_local.py`仅供已具备Python cryptography的开发环境交叉验签，不属于生产依赖。两者不接收私钥。`install.sh`针对已有明确审核路径的首次部署，拒绝覆盖现有服务，备份后修改；部署前应审阅目标站点路径，不应对陌生服务器直接执行。
