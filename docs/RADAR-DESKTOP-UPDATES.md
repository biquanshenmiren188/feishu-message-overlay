# 雷达桌面发布运维

## 固定边界

- 源码基线：origin/main 1860765（2026-11-05 fetch 后全部远端分支中最新）。
- 公共更新端点 `/desktop-updates/` 独立于 `/radar/` 和网站 current，网站回滚不会覆盖客户端包。
- 安装包本身可公开下载，私有仓库不改可见性；包内不含用户连接、DPAPI、手机绑定或账户配置。
- 服务端数据 `/var/lib/radar-desktop-updates`，root-only 签名私钥 `/etc/radar-desktop-update/signing.pem`，程序 `/usr/local/sbin/radar-update-receiver`。
- 公钥固定在 `src/Overlay.Core/RadarDesktopUpdates.cs`。发布权限信任边界是仓库 Actions 与受限发布密钥、服务器 root 管理权。签名私钥不进入仓库、CI或客户端。

## 初次配置（已执行）

生成3072位RSA私钥（已有时不可覆盖），权限0600；把公钥写入客户端并测试。安装 `scripts/radar-update-receiver.py` 为 root-owned 0755 的 `/usr/local/sbin/radar-update-receiver`。使用 `scripts/setup-radar-update-server.py` 增加 nginx 独立静态路径；脚本备份原配置、nginx -t 后 reload，失败恢复配置。无需重启消息或推送服务。

GitHub Actions 的三个仓库 secrets：

- `RADAR_UPDATE_SSH_KEY`：专用 ed25519 发布私钥。
- `RADAR_UPDATE_SSH_TARGET`：SSH 用户和主机。
- `RADAR_UPDATE_KNOWN_HOSTS`：已核对的服务器主机密钥，严格匹配，不在 CI 盲目信任 ssh-keyscan。

服务器 authorized_keys 为该公钥绑定 `restrict,command="sudo -n /usr/local/sbin/radar-update-receiver"`；不允许交互命令、SFTP或端口转发。接收器不执行 SSH_ORIGINAL_COMMAND、不接受上传路径或 shell 参数，输入只接受有大小上限的单个包。专用密钥已验证无法执行替代 shell 命令。维护者原 SSH 登录独立保留。

## 原子发布与恢复

接收器对发布加 flock；限制 header、上传体、ZIP 条目数和解压总量；校验逐文件清单、禁止用户配置与危险路径。版本目录不可覆盖，低于 current 的发布被拒绝。同包同提交重试幂等；包内容或提交改变必须递增版本。

包验证后才签名，并写入 `vYYYY.MM.DD.N/`；该目录包括 ZIP、`release.json` 和 `SHA256SUMS.txt`。最后 fsync 并原子替换 `latest.json`，保留 `previous.json`。上传中断、校验失败不会改变 latest。签名清单和静态包不存在需长期运行的额外服务。

发布故障先检查 CI 与 receipt，不能为了重试覆盖已有包。新包导致业务问题时，首选发布更高版本的修复包；已有客户端拒绝降级。紧急停止继续推广时可由维护者备份 latest 后原子恢复 previous（这仅停止新安装，不把已升级客户端降级）。旧程序仍在每台电脑的安装备份目录，必要时单机维护恢复。

## 本地应急发布

适用于托管CI资源不可用：先从确定提交构建并完整验证，将同一ZIP归档到对应GitHub正式Release，核对GitHub asset digest，再运行：

```powershell
./scripts/publish-radar-update.ps1 -Package artifacts/FeishuMessageOverlay-win-x64.zip -Version vYYYY.MM.DD.N -SourceCommit <完整提交SHA> -UseAdminConnection
```

默认现有 `radar-tencent` 管理连接。CI使用受限key，传入 `-SshTarget`、`-IdentityFile`、`-KnownHostsFile`，不使用 `-UseAdminConnection`。无须复制私有GitHub凭据到服务器。应急发布后必须运行真实公开HTTPS下载校验，并核对服务器包、GitHub包与安装文件哈希。

若GitHub已发布但雷达上传失败，重跑工作流会复用GitHub首次包，不重新替换它。若雷达已成功而最后公网验收临时失败，确认当前版本及包哈希后重跑即可；旧版本工作流不能覆盖服务器新版本。

## 密钥轮换

发布SSH key可独立轮换：新增受限公钥、更新对应GitHub secret、验证发布入口后移除旧专用公钥，不动其他登录。签名key不能直接替换：须先用旧key发布信任新key的过渡客户端并完成迁移，再切换签名；保留旧key安全备份，避免客户端更新链中断。

## 验证记录

完整构建验证报告在本工作副本 `artifacts/verification`，真实子进程回退报告在 `artifacts/update-process-*`。服务器7组隔离测试不访问正式包目录。最终发布与本机安装结果另记录在本文件后续章节。

## Cloudflare Access 前置条件（2026-11-05）

该域名的主站受 Access 登录保护；最初公网验收收到 HTTP 200 的登录HTML，新客户端拒绝该响应，工作流如实失败。经用户明确确认，仅新增 Leida signed desktop updates 自托管应用，目标 leida.shenmiren.work/desktop-updates/*，使用专用 Everyone/Bypass 策略 Leida public signed update files only。

原主站邮箱登录策略与 signed desktop control 应用保持独立。未经登录的公网请求现返回签名JSON和 Cache-Control: no-store, max-age=0，主站仍返回 Access 登录页。不得为了修复下载而取消全站保护，也不在客户端嵌入 Access service token。

GitHub正式包 v2026.11.05.1 来源提交 265d5d7089a2e5e974228ee8cc7b33f375e87645，72,806,308 bytes，SHA256 400c7966a6dcbbd73cea3af682f421e3267b3266ceea36d473e928cbf4019508。GitHub资产digest、服务器签名清单和下载包三方一致已验证。后续源码提交1b3af99仅补齐既有cloud-reader工作流缺少requests依赖，修复后相关云端CI通过，不改变安装包。

## 本机安装验收（2026-11-05）

通过新版客户端 --verify-update-source 从公开雷达域名完成真实下载：signatureVerified=true、checksumVerified=true、filesVerified=656。随后安装该已验签下载包，健康回执版本 v2026.11.05.1；逐文件核对安装目录与正式清单一致，连接配置/DPAPI/原偏好字段/开机项保持。诊断显示 Connected、isVisible=true、desktopRulesConnected=true、opportunitySourceConnected=true、recoveryState=watching。

安装前原小窗已由用户通过托盘退出（生命周期记录），此次启动新版后消息连接正常。未发人工通知、未写入真实屏蔽或手机规则。窗口自动化工具无法定位该桌面浮窗，因此未声称代点了真实托盘菜单；实际更新通道下载、手动更新UI契约测试及安装后进程诊断均通过。

完整本地构建：612核心检查、20 bridge检查、WPF/云窗口/布局/消息/规则/推送码及桌面恢复验证、12下载通道检查、四类真实安装成功与回退场景。Linux接收器7组隔离测试通过。GitHub Windows构建与补齐requests后的云端授权回归均成功。PR #58 保留待评审，不自动合并；正式版本标签指向265d5d7。

发布工作流 [42002619111](https://github.com/biquanshenmiren188/feishu-message-overlay/actions/runs/42002619111) 第二次运行全部成功（首次被Access登录页阻断，补齐独立更新路径后重跑）。重跑复用同一GitHub正式ZIP，服务端幂等发布成功，最终公网客户端验签/下载/逐文件校验步骤通过，验证了未来发布与失败重试链路。
