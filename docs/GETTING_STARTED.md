# W152D Armbian v0.4.2 入门教程

本教程适用于中兴 W152D（Amlogic S905L4 / GXLX4）和本仓库发布的 Armbian Bookworm USB 镜像。USB 试用保留 eMMC 上的系统和用户分区。需要写入内置 eMMC 时，请使用 [eMMC 安装教程](EMMC_INSTALL.md)。

## 1. 下载和写盘

准备一只可清空的备用 U 盘，一台有 HDMI 输入的电视或显示器，以及 USB 键盘和网线。原厂启动顺序的盒子还需要 USB 转 TTL 串口适配器，用于进入 U-Boot。

从同一个发布页下载 `.img.gz` 和 `SHA256SUMS`。[v0.4.2 发布页](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.2)

Linux 在下载目录运行：

```sh
sha256sum -c SHA256SUMS
```

Windows PowerShell 在下载目录运行下面的命令，比较两行开头的 64 位十六进制哈希：

```powershell
Get-Content .\SHA256SUMS
(Get-FileHash .\Armbian_W152D_Bookworm_6.12.119_v0.4.2.img.gz -Algorithm SHA256).Hash.ToLowerInvariant()
```

1. 校验通过后解压 `.img.gz`，得到 `.img`。
2. 在 Etcher 选择 **Flash from file**，打开 `.img`，按容量核对目标 U 盘。刷写会清空整只 U 盘。[balenaEtcher](https://etcher.balena.io/)
3. 等刷写和校验结束后安全弹出。镜像包含 FAT32 引导分区和 ext4 根分区，Windows 提示格式化 ext4 时选择取消。

## 2. 从 U 盘启动

盒子断电时接好 HDMI、键盘和网线，只插这一只 USB 存储设备。第一次试用优先使用 USB3 口。已经配置为 USB 优先的盒子可直接上电。

仍用原厂启动顺序时，通过 TTL 串口连接。串口使用 `921600` 波特率、8N1、无流控。先确认板上的串口焊盘与逻辑电平，接 GND，并交叉连接 TX/RX。盒子用自己的电源供电。上电时中断 U-Boot 倒计时，在原厂 U-Boot 输入：

```text
gpio set GPIOAO_11
run recovery_from_udisk
```

这两条命令用于本次临时启动。若希望以后自动启动，先按[USB 优先与恢复教程](USB_BOOT_AND_RECOVERY.md#一次性配置-usb-优先)备份原 `bootcmd` 并验证插盘和拔盘两条路径，再保存环境。

## 3. 完成首次登录和连接 SSH

1. 在 HDMI 控制台或 TTL 串口等待 Armbian 首次设置提示，按提示进入设置。设定自己的 root 密码，并按需创建普通用户。首次初始化和扩容需要一点时间。
2. 在盒子控制台运行 `ip -br -4 addr` 查看 `eth0` 的 DHCP 地址，也可以从路由器的设备列表查找。
3. 在盒子控制台运行 `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`，记下主机指纹。换盘或重刷后会生成新指纹。
4. 在电脑上用 SSH 登录，首次连接时核对屏幕上显示的指纹。下面的示例地址需要换成盒子的实际 IP，创建了普通用户时可用其账号连接。

```sh
ssh root@192.168.1.100
```

SSH 端口为 22。若同一地址曾用于旧系统，先在盒子控制台核对新指纹，再用 `ssh-keygen -R 192.168.1.100` 清理电脑上对应地址的旧记录，重新连接。

## 4. 核对启动结果

```sh
uname -r
findmnt -no SOURCE,FSTYPE /
findmnt -no SOURCE,FSTYPE /boot
df -h /
systemctl --failed --no-pager
tr ' ' '\n' </proc/cmdline | grep '^w152d\.hdmi_handoff='
ls -l /dev/fb0 /dev/dri/renderD128
```

v0.4.2 使用 `6.12.119-ophub`。只插一只启动盘时，常见结果为 `/dev/sda2` 挂载 ext4 根分区，`/dev/sda1` 挂载 FAT32 `/boot`。例如 `w152d.hdmi_handoff=edid-2160p60hz` 表示固件选择了 4K60，实际输出可在电视的信号信息页确认。控制台缓冲区使用 1080p，实测 4K 电视的文字显示比例正常。`renderD128` 用于确认 Lima 渲染节点已注册。

## 5. 常见问题和恢复

| 现象 | 处理 |
| --- | --- |
| 直接进入 Android | 先检查 U-Boot 的 USB 启动顺序。改用 USB3 口，只留一只启动盘，通过串口查看 `usb storage`。 |
| 电视无画面或比例异常 | 先选对 HDMI 输入，接好电视再冷启动，让原厂 U-Boot 读取 EDID。通过网线或串口确认系统是否已启动，记录电视型号、信号分辨率和 `w152d.hdmi_handoff`。 |
| HDMI 无声 | HDMI 音频当前不可用。可通过 `cat /proc/asound/cards` 查看本机声卡。 |
| SSH 连不上 | 先在本地控制台确认首次设置已完成、`eth0` 已取得 IP，再检查 `systemctl status ssh --no-pager`。 |
| 要回到设备原系统 | 在 Armbian 执行 `sudo poweroff`，关机后拔出 U 盘再上电。若曾修改启动顺序，可通过串口恢复已记录的原 `bootcmd`。[恢复步骤](USB_BOOT_AND_RECOVERY.md#一次性配置-usb-优先) |

发布版的 HDMI 和 GPU 使用与内核匹配的外置模块。更换内核时需要同时准备匹配模块和设备树，并保留原启动入口。[6.12.119 升级试验](GPU_AND_HDMI.md#612119-ophub-跨版本升级试验)

如果仍遇到问题，请提供镜像版本、USB 端口、显示设备型号，以及 `uname -r`、`systemctl --failed` 和相关脱敏日志。[提交问题](https://github.com/Zlion-Y/w152d-armbian/issues/new) · [隐私说明](PRIVACY_AND_ARTIFACTS.md)
