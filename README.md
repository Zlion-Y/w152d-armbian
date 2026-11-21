# W152D / S905L4 USB Linux

在 W152D 上从 U 盘运行 Armbian Bookworm 用户空间，使用 ext4 持久根目录与自定义 BusyBox PID 1。

- **Linux 6.12.0 板级适配**已通过物理断电后的无人值守启动、百兆全双工、5 GHz Wi-Fi 及四个 USB 外口实测。适配沿用已有的原厂 U-Boot USB 入口，板级初始化放在 U 盘上。仓库提供[主线适配源码、出包说明和验收结果](docs/MAINLINE_USB.md)，目前处于源码预览阶段。
- **原厂 Linux 5.4.210 预览版**提供下文的制盘流程，已验证 5 GHz Wi-Fi、DHCP、密钥 SSH/SFTP、HTTP 状态页及 HTTPS。

## 原厂 5.4.210 版下载与准备

下载 [Releases](https://github.com/Zlion-Y/w152d-armbian/releases) 中同一版本的：

- `w152d-rootfs-bookworm-v0.2.0-preview.ext4.gz`：新建的 2 GiB 用户空间文件系统镜像，已移除共享登录凭据。
- `w152d-usb-bootstrap-v0.2.0-preview.zip`：U-Boot 脚本、initramfs、识别标记和第三方许可说明。
- `SHA256SUMS`、`release-manifest.json`：附件校验和、来源与验证范围。

另外需要**这台盒子自己的** `boot_a.img`、`vendor_boot_a.img`、原厂 `vendor` ext4 镜像。内核、DTB、模块和无线固件由工具在本机提取，不放进发布附件。不可拿其他型号的文件代替。

准备已有 FAT32 分区的 U 盘。工具只创建文件，不格式化或重排分区；已有 `w152d/rootfs.ext4` 时会拒绝覆盖。建议至少 3 GiB 空闲空间。Python 3.10+ 和系统 OpenSSH 即可完成制盘；激活启动顺序另需 Node.js 22.15+ 与 root ADB。

```powershell
# 若没有自己的密钥，在本机生成；私钥不要上传仓库。
ssh-keygen -t ed25519 -f .\outputs\keys\client_ed25519

python tools/prepare_usb.py --usb F:\ `
  --rootfs .\downloads\w152d-rootfs-bookworm-v0.2.0-preview.ext4.gz `
  --bootstrap .\downloads\w152d-usb-bootstrap-v0.2.0-preview.zip `
  --checksums .\downloads\SHA256SUMS `
  --stock-dir C:\stock-backup `
  --vendor-image C:\stock-backup\vendor_a.img `
  --public-key .\outputs\keys\client_ed25519.pub `
  --ssid YOUR_WIFI_SSID
```

工具交互读取 Wi-Fi 密码，不显示密码。配置只写入 U 盘的 `w152d/config/`；不要提交或分享该目录。暂只配置实测的 WPA2-PSK 路径，省略 `--ssid` 可仅配置公钥并使用有线网络。

首次启动会导入你的公钥和原厂文件，并生成这份安装独有的 SSH 主机密钥。**镜像没有通用 SSH 密码。** 主机公钥会写回 U 盘 `w152d/config/ssh_host_ed25519_key.pub`，可用 `ssh-keygen -lf` 核对首次连接指纹。

## 原厂 5.4.210 版启动顺序

已设置过本项目 USB 优先环境的设备可直接启动。新设备先完成一次性 U-Boot 验证，再按 [启动与恢复说明](docs/USB_BOOT_AND_RECOVERY.md) 备份并激活。先用默认的只读/生成补丁模式审阅：

```powershell
python tools/activate_usb_adb.py --serial 192.0.2.18:5555 --output outputs/env-backup-001
```

实际写入需重新指定一个空备份目录并加 `--execute`。只修改两份 64 KiB 环境中的 `bootcmd`，保留各副本的其他变量和分区尾部，整份备份、CRC 与写回哈希验证均保留。不要将别人设备的 env 镜像写入自己的盒子。

USB3 插口保持原位：U-Boot 先拉高 `GPIOAO_11 / CURRENT_LIMIT1`，以 480 Mb/s 读引导文件；Linux 接管后同口恢复 USB3 5000 Mb/s。当前安全内核地址为 `0x01080000`；`0x05080000` 落在 secmon 保留区域，不能使用。

## 登录与状态页

DHCP 地址由路由器分配，下列 `192.0.2.18` 仅为文档示例。Linux 使用 SSH，Android ADB 是另一条连接通道。

```powershell
ssh -i .\outputs\keys\client_ed25519 -p 2222 root@192.0.2.18
```

状态页为 `http://设备地址:18080/`，使用持续监听的 BusyBox httpd，支持浏览器并发连接；`/status.txt` 提供纯文本诊断。Windows OpenSSH 如拒绝私钥权限，在 PowerShell 7 运行：

```powershell
.\tools\Fix-SSHKeyPermissions.ps1 -Path .\outputs\keys\client_ed25519
```

## 已知范围

| 项目 | 结果 |
|---|---|
| 测试板卡 | W152D / GXLX4 BT203，原厂 U-Boot 2019.01（2026-01-29 构建） |
| USB 直接启动与持久化 | 通过 |
| Android 回退 | 缺少引导入口时已实测；Linux 接管后的故障需断电拔盘恢复 |
| Wi-Fi | 原厂配套驱动，5 GHz / WPA2 / 802.11ac 已通过 |
| SSH、SFTP、DNS、HTTP、HTTPS | 通过 |
| systemd / Docker / 桌面 / HDMI / 硬解 / 蓝牙 | 未验证或未启用 |
| 发布镜像 | 从官方缓存新建，首次启动配置逻辑单独记录在发布验收中 |

[完整验证范围](docs/VALIDATION.md) · [构建说明](docs/BUILD.md) · [隐私与附件边界](docs/PRIVACY_AND_ARTIFACTS.md) · [第三方来源](docs/THIRD_PARTY.md)

## 代码与历史

- `usb/`：直接 USB 启动、持久根目录和首次启动配置。
- `wifi/`：无线加载、DHCP、时间恢复与联网校时。
- `tools/`：制盘、原厂文件提取、环境备份/修改、镜像构建与 ACL 修复。
- `src/status_service.sh`：持续监听状态服务。
- 旧的 `build_probe.py`、RAM/kexec 脚本及 [历史进展](docs/PROGRESS.md) 保留早期研究，不是当前推荐的日常启动入口。

原始工作区、设备私钥、无线凭据、完整 env 备份和未脱敏串口日志不属于仓库发布内容。
