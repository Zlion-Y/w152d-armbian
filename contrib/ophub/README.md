# W152D 接入 ophub 的补丁

维护者在 [#3770 的回复](https://github.com/ophub/amlogic-s9xxx-armbian/issues/3770#issuecomment-7071742473) 中给出了内核和镜像的提交位置。内核目标为 `ophub/linux-6.12.y`，设备树放在 `arch/arm64/boot/dts/amlogic/`。镜像目标为 `ophub/amlogic-s9xxx-armbian`。W152D 继续使用设备上的原厂 U-Boot。

提交顺序是[内核源码](https://github.com/ophub/linux-6.12.y/pull/9)、[通用 6.12 构建配置](https://github.com/ophub/kernel/pull/50)、[Armbian 板型和 USB 启动说明](https://github.com/ophub/amlogic-s9xxx-armbian/pull/3794)。配置和板型为依赖草稿。

## 内核

当前基线是 [6.12.118 的 `237b076a69ad`](https://github.com/ophub/linux-6.12.y/commit/237b076a69ad793cad84c3997645275696bbe678)，与此前验证构建的 unifreq 源码提交相同。用[构建说明](../../docs/BUILD.md)中的固定源归档运行：

```sh
JOBS=8 bash tools/build_w152d_kernel.sh --ophub /path/to/unifreq-237b076a.tar.gz outputs/w152d-ophub
```

该入口应用原有的时钟、USB、无线及板级驱动补丁，再应用 [kernel-board.patch](kernel-board.patch)。后者登记 `meson-gxlx4-w152d.dts`，将 GXLX4 时钟和 Amlogic CRG USB 的编译接线变成显式 Kconfig 选项。此 DTS 与旧测试 DTB 采用同一套板级资源，保留已实测的电源、引脚和硬件范围。`w152d.config` 列出接入通用内核配置时需核对的关键选项。使用完整 W152D 配置构建时，脚本关闭该固定基线中有 API 编译冲突的 R-Car 音频模块。

## 镜像

[armbian-board.patch](armbian-board.patch) 以 [ophub/amlogic-s9xxx-armbian 的 `f816cfcca674`](https://github.com/ophub/amlogic-s9xxx-armbian/commit/f816cfcca674a312985cb76271c9d28753d6dd76) 为基线，可在其检出目录用 `git apply` 应用。

- `BOARD=w152d` 已加入板型表和三个构建工作流，初始为 `BUILD=no`，显式选板构建。
- 原厂 `recovery_from_udisk` 加载 `aml_autoscript`，脚本依据 ophub 生成的 `uEnv.txt` 加载内核、DTB、initramfs，并把根分区 UUID 交给标准 initramfs。USB 端口供电沿用[原厂 U-Boot 设置](../../docs/USB_BOOT_AND_RECOVERY.md)。
- 标准 `mkinitramfs` 加入早期 xHCI 模块，启动后交给根文件系统的 `/sbin/init`（systemd）。镜像缺少可执行的 `/etc/rc.local` 时，启用 systemd 一次性服务，在确认 `/` 位于 USB 盘的第二个 ext4 分区后调用 ophub 自带的 `armbian-tf`。双色灯由 systemd 托管，板型配置提供 LED 名称和有线接口。
- 板型通过 `VENDOR_USB_BOOT` 声明原厂直启。镜像构建和 `armbian-update` 共用 initramfs 生成脚本，将对应内核的 `uInitrd` 控制在原厂引导脚本的 24 MiB 装载窗口内。两条路径均跳过二级 U-Boot，eMMC 安装入口在检查板型后退出。

Wi-Fi 固件按[构建说明](../../docs/BUILD.md)取得，按板型放入测试镜像的 `/usr/lib/firmware/`。核对测试机的无线固件与板级配置后再做无线关联和重启测试。

## 验收

离线试制使用 Armbian Bookworm ARM64 根文件系统和四个 ophub 格式的内核包。已运行 ophub 的分区创建、文件复制、内核替换及引导与根文件系统配置阶段。成品的 FAT32 与 ext4 检查通过，`uEnv.txt` 和 `fstab` 指向同一根分区 UUID，标准 initramfs 包含 xHCI 模块，`/sbin/init` 指向 systemd。头文件包已用 ARM64 外部测试模块验证。此轮未运行 GitHub Actions 的下载与发布阶段。

实机验收覆盖四个外置 USB 口启动、拔盘回到 Android、ext4 自动扩容、systemd、有线 DHCP、Wi-Fi、双色灯和同版本内核重装后启动。

初版试制镜像实机通过 UUID 找到 ext4 根分区，但 Meson UART 与 8250 同时注册 `ttyS0`，导致 initramfs 无法从 `/dev/console` 交接。接入补丁改用与 G12A 相同的 UART 时钟分频模式及 `ttyAML0`。只替换 U 盘引导分区的 DTB 和 `uEnv.txt` 后，第一个 USB2 口（内置 Hub 路径 `3-1.3`）冷启动已到达 systemd 的多用户目标和串口登录页。SSH、journald、WPA supplicant 与前面板 LED 服务均已启动，SC2355 固件成功加载。

同一只盘在 USB3 口也已启动。测试盘通过 `wpa_supplicant@wlan0` 和 `systemd-networkd` 接入 Wi-Fi，DHCP、网关和 SSH 公钥登录正常。常规重启后重新获得 DHCP 地址并通过无线再次登录，确认 PID 1 为 systemd、根文件系统为 USB 上的 ext4。

测试机原先保存的 USB 优先命令只打开 USB3 供电。第二个 USB2 口直接上电时，原厂 U-Boot 扫描到 0 块 USB 磁盘并回到 Android。按教程在当次 U-Boot 会话中使能三路 USB2 供电、释放 Hub 后，第二和第三个 USB2 口分别从 `3-1.2` 和 `3-1.1` 冷启动到 systemd，并通过无线 SSH 验证根分区。拔掉 U 盘后，用相同的临时启动顺序冷启动，U-Boot 扫描到 0 块 USB 磁盘并走到原厂 Android 11，串口确认 `sys.boot_completed=1`。测试期间未保存 U-Boot 环境。

最小 Bookworm 测试盘原先缺少 `/etc/rc.local`，根文件系统停在 2.0 GiB。启用扩容服务后重启，`armbian-tf` 将 7.5 GiB 测试 U 盘上的根文件系统扩至 7.1 GiB，写入完成标记，systemd 多用户目标和无线 SSH 正常。有线用 `systemd-networkd` 的临时 DHCP 配置验收，通过 DHCP、100 Mbps 全双工协商及网关 ICMP 测试。有线未连接时网络灯亮红色，建立载波后亮绿色。

使用 `armbian-update -d tar -b yes` 原地重装同版本 `6.12.118-w152d`。四个包通过 SHA-256 校验，标准 `uInitrd` 重新生成，内置与内核同版本的 xHCI 模块。自动重启后，原厂 U-Boot 从同一 U 盘进入 systemd，无线 SSH 可登录，根文件系统保持 7.1 GiB，扩容服务依据完成标记跳过执行。这个测试覆盖本地 `.tar.gz` 更新路径。`.deb` 更新和跨版本更新待实测。

按教程在测试机持久化四口 USB 优先的 `bootcmd`，串口返回 `Saving Environment to STORAGE... OK`。复位后无需串口引导命令，从 USB2（`3-1.3`）自动进入 Armbian，Wi-Fi SSH 验证通过。
