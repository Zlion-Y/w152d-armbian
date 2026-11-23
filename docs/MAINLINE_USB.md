# W152D Linux 6.12 U 盘启动

本文对应本仓库的早期 USB 预览版。基于 ophub 的 systemd 镜像和 eMMC 适配见 [ophub 接入状态](../contrib/ophub/README.md)。

W152D / GXLX4 (S905L4) 由原厂 U-Boot 2019.01 的 `recovery_from_udisk` 入口启动。整盘镜像使用第一分区 FAT32 引导、第二分区 ext4 挂载根文件系统；首次启动扩展 ext4 以使用 U 盘的剩余容量。制盘和临时启动不写入原机 eMMC。自动 USB 启动环境的设置见 [U-Boot 启动说明](USB_BOOT_AND_RECOVERY.md)。

## 制盘

可直接使用[整盘镜像与 Etcher 流程](ETCHER.md)。以下是保留单个 FAT32 分区的手动制盘方式，根文件系统以 ext4 文件挂载。

1. 按[构建说明](BUILD.md)生成主线启动包和干净的 Armbian ext4 根文件系统。使用第一分区是 FAT32 的空 U 盘。
2. 把引导文件和根文件系统复制到已挂载的 U 盘。以下用 `/media/user/W152D` 作示例，Windows 可传入盘符路径。
3. 配置 SSH 公钥。如需要测试 WPA2 Wi-Fi，可给 `configure_usb.py` 加上 `--ssid YOUR_SSID`，按提示输入密码。配置与主机公钥都保存在 U 盘的 `w152d/config/`。
4. 写入四个字节的 `BOOT`（无换行），创建 `continuous`，安全弹出 U 盘，再接入盒子 USB3 口启动。

```sh
usb=/media/user/W152D
python tools/prepare_usb.py --usb "$usb" --bundle outputs/mainline-usb --rootfs outputs/rootfs.ext4
python tools/configure_usb.py --usb "$usb" --public-key "$HOME/.ssh/id_ed25519.pub"
printf BOOT >"$usb/w152d/mainline/boot.arm"
touch "$usb/w152d/mainline/continuous"
sync
```

首次启动生成独立的 SSH 主机密钥，使用 `ssh-keygen -lf` 核对 U 盘上的 `w152d/config/ssh_host_ed25519_key.pub`，然后以 `ssh -p 2222 root@设备地址` 连接。主机地址由 DHCP 分配。状态页端口为 18080。

## 启动链和 LED

- [入口脚本](../usb/mainline/w152d-usb-dispatch.cmd) 先消费 `boot.arm`，再读取主线 `boot.scr`。跳过或加载失败时交还 U-Boot。主线脚本装载 Image、initramfs、DTB 并核对字节数，打开 USB3 PHY 电源域和 Wi-Fi 供电，配置 SDIO 引脚后执行 `booti`。
- [initramfs](../usb/mainline/init) 加载 USB 和有线模块，然后[接管 U 盘根文件系统](../usb/mainline/w152d_usb_root)。它先只读检查 USB 存储的第一分区，依据 `w152d/USB_ID` 和根文件系统定位启动盘。开机时只插一只带有该标记的启动盘。主线根文件系统的 PID 1 在 SSH 开始监听且存在 `continuous` 时，重新设置下次启动标记。
- 电源灯在 U-Boot 开始加载主线时为红色，内核接管后保持红色。Armbian 的 SSH 服务开始监听 2222 端口后，电源灯切为常亮绿色。绿灯对应 GPIOAO_4，红灯对应 GPIOAO_5。
- 网络灯按 `eth0` 的有线链路状态切换。链路连通时常亮绿色，断开时常亮红色。每秒检查一次；Wi-Fi 和公网可达性独立于有线链路状态。绿灯对应 GPIOAO_9，红灯对应 GPIOAO_7。可通过 `/sys/class/leds/` 中各灯的 `brightness` 核对状态。

## 实机记录

下表为 2026-11-21 UTC 的首轮 Linux 6.12 板级构建验收。

| 项目 | 结果 |
| --- | --- |
| 无人值守 USB 冷启动 | 物理断电再上电，串口全程只读，自动进入 6.12.0，SSH 恢复 |
| 持久根文件系统 | U 盘上的 ext4 经 loop 以读写方式挂载，测试文件跨两次软件重启哈希一致 |
| 有线 | 100 Mb/s 全双工，DHCP 和网关通过，局域网 16 MiB 下载 90.1 Mb/s、上传 92.1 Mb/s |
| SC2355 Wi-Fi | 5 GHz 关联、DHCP、网关和公网下载通过，SDIO SDR104 实际 192 MHz。单流中位数约 246–250 Mb/s，四流快照约 274–300 Mb/s |
| USB3 | 实测启动盘以 5 Gb/s 协商，读写通过 |
| 三个 USB2 外口 | 单只测试盘轮换插入，逐口以 480 Mb/s 枚举并读取验证 |

双色灯逻辑已在主线 U 盘系统上验证。软件重启时，串口记录 U-Boot 设置红灯，内核日志记录 SSH 就绪后切绿。有线接口停用和恢复时分别读回红亮与绿亮；连续 15 次网关 ping 全部返回，期间采样确认绿灯常亮。全新整盘镜像的验收见 [Etcher 四口记录](ETCHER.md#四口验收)。

要停用 U 盘入口，可在关闭设备后拔盘，或把 `boot.arm` 写成 `STOP` 并删除 `continuous`。详见[启动恢复](USB_BOOT_AND_RECOVERY.md)。
