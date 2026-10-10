# 最新版安装与云端配置（2026-10-10）

当前使用 **main**。它包含原 `codex/push-page-low-traffic` 的桌面、网页和雷达卡片代码，以及多电脑只读接入支持。旧日期文档是历史记录，当前安装方式以本文为准。

## 数据到底从哪里来

```text
飞书已授权群里的机器人消息
  → 腾讯云 robot-push 服务（唯一飞书长连接接收器）
  → leida.shenmiren.work / Cloudflare / Nginx
  → 网页机器人推送、Windows 飞书消息小窗
```

飞书提供消息事件，腾讯云运行接收服务，Cloudflare 提供域名入口和网页访问控制。它们不是三种互斥的数据源。另一台电脑关机不会影响云端收消息；本机需要开机联网才能显示小窗。最新版 v2026.10.10.1 将雷达卡片同时接入桌面，不需要另选分支。

本次电脑安装位置是桌面 `GPT/FeishuMessageOverlay`，入口是 `GPT/飞书消息小窗.lnk`。不要把快捷方式和程序目录分开删除。程序是独立 Windows 应用，不是 Chrome 扩展，三号浏览器只用于管理和访问网站。

## 桌面卡片：全部同时展示

云端已有 BasisPulse 缓存 `basispulse.json` → 签名只读 `state` 响应中的 `opportunities` → 桌面右侧卡片。飞书文字消息仍在左侧，两边同时展示，无须切换。复用现有云端采集，不增加上游轮询，也不需要在电脑填写飞书 Secret。

- 卡片展示币种、买卖交易所、现货/永续、费率/周期、24H 成交量、OI、四项收益/价差指标、R 等级、风险提醒和充提信息。
- 全部有效卡片均可滚动查看，不截取前几张；协议最多接受 1000 张，使用虚拟列表。刷新保留滚动位置。
- 数据超过 20 秒未更新标为待恢复；完整快照中消失的卡片标为已失效，保留 30 秒。未知充提状态显示问号，不推测为开放。
- “复制”生成策略文本，不能识别的策略复制卡片文字；“雷达”打开对应网页。不会自动交易。
- 首次进入云端模式自动展开左右布局，归位按钮恢复适合双栏的尺寸。手动拖动窗口边缘可调整大小。
- 卡片空白时先看右侧是否显示“当前没有活跃机会”；这是源端空快照，不是配置丢失。等待源端出现新机会即可。若“正在连接”，检查服务健康和缓存更新。

## 已验证的配置

- Windows x64 自包含构建，最新版 v2026.10.10.1；附带 .NET 运行时。安装时另放置 Node 24.19.0 于 `runtime/node.exe`；云端模式本身不启动本地飞书 SDK。
- 腾讯云东京现有服务 `robot-push.service` 持续接收飞书消息；本次没有重新创建飞书应用或替换飞书凭证。
- 本机开启云端读取，用独立 ECDSA 公钥授权，私钥由当前 Windows 用户 DPAPI 加密保存在本机。旧电脑的主公钥保持原样。
- 2026-10-10 14:37（UTC+8）运行中诊断确认 `Connected`、`cloudSource=true`、已接收 23 条机器人消息和 1 张卡片、左右窗口可见、卡片源连接正常。此数量是当时验收结果，不是固定条数，也不证明每个群均产生过新消息。
- 新电脑只有读取权限。能显示云端已有置顶内容，但不能更改云端置顶群、发布消息或重配飞书凭证。设置中的置顶群修改会被服务端拒绝。

## 在另一台 Windows 电脑安装

优先从 [最新版下载页](https://github.com/biquanshenmiren188/feishu-message-overlay/releases/latest) 下载 Windows x64 ZIP，完整解压到目标程序目录。它是已构建的软件，不需要再编译；云端模式可直接使用。包内含本文和 `scripts/install-desktop-launcher.ps1`，从下面第 3 步继续。发行包不包含任何电脑的授权私钥，新电脑仍须完成第 4 步与服务器公钥授权。只有下载源代码时才执行第 1–2 步。

1. 从 main 下载源代码，安装 .NET 10 SDK 和 Node 22 或兼容版本。在源代码根目录执行：

   ```powershell
   npm ci --prefix bridge --ignore-scripts
   npm test --prefix bridge
   ./scripts/build.ps1 -SelfContained
   ```

2. 将完整 `artifacts/app` 复制到目标文件夹，例如桌面 `GPT/FeishuMessageOverlay`。不要只复制 EXE。自包含包无需另装 .NET；如需要本地 SDK 模式，另安装 Node 或将官方 Node 可执行文件放入 `runtime/node.exe`。
3. 用仓库脚本创建入口：

   ```powershell
   ./scripts/install-desktop-launcher.ps1 `
     -Directory "$env:USERPROFILE/Desktop/GPT/FeishuMessageOverlay" `
     -Shortcut "$env:USERPROFILE/Desktop/GPT/飞书消息小窗.lnk"
   ```

4. 在程序目录打开 PowerShell，以日常使用软件的 Windows 用户执行以下命令，每条执行完成后再进行下一条。先从托盘退出已运行的小窗，避免旧会话继续使用旧配置：

   ```powershell
   Start-Process ./FeishuMessageOverlay.exe -ArgumentList '--configure-web-publisher','desktop-public.pem','key-result.json' -Wait
   Start-Process ./FeishuMessageOverlay.exe -ArgumentList '--cloud-source-mode','on' -Wait
   Start-Process ./FeishuMessageOverlay.exe -ArgumentList '--enable-auto-joined','joined-result.json' -Wait
   Get-Content ./key-result.json
   ```

   回执必须是 `configured: true`，记下 `keyId`。重复生成命令会复用现有私钥并重新导出公钥，不会自动换钥。仅将 `desktop-public.pem` 交给服务器管理员；不要复制 `publisher-signing.dpapi` 到其他电脑，也不要将飞书 App Secret 发到聊天或提交 GitHub。

## 服务器授权新电脑

以下操作适用于现有云端接收服务，不是从空白服务器安装整套雷达网站的脚本。

1. 部署本仓库的 `web/robot-push/publisher/server.py` 和 `desktop_cards.py`。2026-10-10 已上线通用多电脑只读授权及卡片缓存读取。没有公钥文件的电脑仍不能接入。
2. 在已有服务器暂存新 `server.py` 和 `desktop_cards.py`，语法检查、备份后更新：

   ```bash
   # 在包含已审查 server.py 和 desktop_cards.py 的暂存目录执行
   python3 -c "import ast,pathlib; ast.parse(pathlib.Path('server.py').read_text())"
   backup="/opt/robot-push/backups/reader-$(date +%Y%m%d-%H%M%S)"
   sudo install -d -m 0700 "$backup"
   sudo cp -a /opt/robot-push/server.py "$backup/server.py"
   sudo install -o root -g robot-push -m 0644 desktop_cards.py /opt/robot-push/desktop_cards.py
   sudo install -o root -g robot-push -m 0644 server.py /opt/robot-push/server.py.new
   sudo mv /opt/robot-push/server.py.new /opt/robot-push/server.py
   sudo systemctl restart robot-push
   sudo systemctl is-active robot-push
   curl --fail --silent http://127.0.0.1:18883/health
   ```

   如果启动或健康检查失败，立即用备份恢复 `server.py` 并重启。保留原来的服务单元、云端私有配置、`publisher-public.pem` 和所有 `desktop-reader-*.pem`。
3. 将新电脑导出的**公钥**上传到服务器的管理暂存目录，检查 keyId 与 Windows 回执一致：

   ```bash
   set -euo pipefail
   key_id=$(openssl pkey -pubin -in desktop-public.pem -outform DER | sha256sum | cut -c1-16)
   printf 'keyId=%s\n' "$key_id"
   # 核对回执后执行；默认服务的主公钥目录为 /etc/robot-push
   test ! -e "/etc/robot-push/desktop-reader-${key_id}.pem"
   sudo install -o root -g robot-push -m 0640 desktop-public.pem "/etc/robot-push/desktop-reader-${key_id}.pem"
   ```

   不覆盖 `/etc/robot-push/publisher-public.pem`，它属于旧电脑/管理员。通用实现每次请求检查读者公钥文件，新增或撤销公钥不需要重启。撤销时将相应公钥移到受限备份目录；下一次读取就会被拒绝。
4. 启动 Windows 快捷方式，等待连接。无需在“飞书官方连接”窗口重新输入 App ID、App Secret 或逐个群 ID；那是本地直连流程，当前用的是云端模式。

读者只允许 `POST /radar/api/robot-push/control` 且正文恰为 `{"action":"state"}`。仍验证 P-256 签名、60 秒时间差和随机码防重放；每个读者每分钟最多 30 个已接受请求，独立于主公钥额度。授权文件所在目录必须仅允许管理员写入。

## 飞书与群范围

使用现有企业自建应用，启用机器人并发布；需要 `im:chat:read`、`im:message.group_msg.include_bot:read` 等应用权限，订阅 `im.message.receive_v1`，事件接收方式为长连接。已有可用应用无需重建。本次未修改既有已审核权限。

云端接收器通过官方 SDK 核实机器人当前加入的群，只接收其中的机器人消息。加入新群后，等待成员列表刷新并用群里自然产生的新机器人消息验收。退出群或成员核实失败时收紧接收范围；普通成员聊天不展示。网页登录飞书不等于消息 API 授权。

云端私有应用配置位于 `/var/lib/robot-push-private`，接收代码在 `/opt/robot-push`，服务以 `robot-push` 用户运行。不要把这些私有配置复制到源码仓库。现有服务启动参数见 `web/robot-push/publisher/cloud-mode.service.conf`。旧 `/configure` 和 `/publish` 客户端代码保留了历史 IP，**本次新电脑安装不使用这两个入口**；不要照旧部署文档向历史 IP 提交凭证。

## Cloudflare 和连接排查

小窗读取地址是 `https://leida.shenmiren.work/radar/api/robot-push/control`。该精确路径现有配置允许请求到达后端，由服务端强制验证签名；网站其他页面仍有 Cloudflare 登录验证。不要扩大为全站免验证，也不要删除后端签名校验。GitHub 拉取代码不会自动创建 Cloudflare/Nginx 配置。

- `401`：公钥未安装、keyId 不匹配、签名失败或电脑时钟偏差超过 60 秒。
- `403`：只读电脑尝试修改云端置顶/配置；检查是否仍是网页访问控制拦截。
- `429`：短时间请求过多，停止重复开进程或诊断，等待后重试。
- 登录重定向、HTML 代替 JSON：检查精确 control 路径的 Cloudflare/Nginx 路由，程序不会跟随登录重定向。
- Connected 但没新内容：检查云端飞书连接、机器人是否在目标群、目标群是否实际产生机器人新消息。不要将缓存误当作新消息。

导出运行状态（含私有群 ID，仅本机排查，不上传 GitHub）：

```powershell
Start-Process ./FeishuMessageOverlay.exe -ArgumentList '--export-diagnostics','diagnostic.json' -Wait
```

看 `state=Connected`、`cloudSource=true` 和 `realBotMessages`。本机配置默认在 `%LOCALAPPDATA%/FeishuMessageOverlay`；更新程序时保留该目录。更改模式后必须退出旧进程并重新启动。

## 验证与版本维护

本次安装之前通过 45 项核心检查、20 项 bridge 检查及 WPF/窗口契约；运行中连接验收如上。此次服务端通用读者补丁新增 20 项合成授权检查，并回归云端配置和接收器测试；离线测试使用 cryptography 适配 OpenSSL 命令，不冒充真实飞书群端到端测试。此前上线的单公钥补丁另经过真实 OpenSSL 的 14 项隔离授权检查。

```bash
python3 web/robot-push/publisher/reader_auth_test.py
python3 web/robot-push/publisher/cloud_config_test.py
python3 web/robot-push/publisher/cloud_receiver_test.py
```

测试依赖 Python `cryptography`，仅合成密钥。运行服务仍使用 OpenSSL CLI。本次 GitHub Actions 曾因 artifact 存储配额上传失败，所以采用本机成功构建安装；不要将 artifact 上传失败解释成程序编译失败。

main 是后续下载和更新入口。旧开发分支合并后删除；有独立旧历史的 `feature/feishu-overlay-v13` 以 `archive/feishu-overlay-v13-20261010` 标签留档，不作为最新版。旧主分支位置由 `archive/main-before-cloud-20261010` 标签留档。源码不包含真实私钥、飞书凭证、群消息、用户诊断和音频。
