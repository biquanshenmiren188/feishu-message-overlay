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
