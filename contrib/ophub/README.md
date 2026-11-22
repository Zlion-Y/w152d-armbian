# W152D 接入 ophub 的补丁

维护者在 [#3770 的回复](https://github.com/ophub/amlogic-s9xxx-armbian/issues/3770#issuecomment-7071742473) 中给出了内核和镜像的提交位置。内核目标为 `ophub/linux-6.12.y`，设备树放在 `arch/arm64/boot/dts/amlogic/`。镜像目标为 `ophub/amlogic-s9xxx-armbian`。W152D 继续使用设备上的原厂 U-Boot。

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
- 标准 `mkinitramfs` 加入早期 xHCI 模块，启动后交给根文件系统的 `/sbin/init`（systemd）。有线和无线用常规模块加载与系统网络服务，扩容用 ophub 现有的 `armbian-tf`。双色灯由 systemd 托管，板型配置只提供 LED 名称和网络接口。
- 板型通过 `VENDOR_USB_BOOT` 声明原厂直启。镜像构建及内核更新跳过二级 U-Boot，eMMC 安装入口在检查板型后退出。

Wi-Fi 固件按[构建说明](../../docs/BUILD.md)取得，按板型放入测试镜像的 `/usr/lib/firmware/`。核对测试机的无线固件与板级配置后再做无线关联和重启测试。

## 验收

离线试制使用 Armbian Bookworm ARM64 根文件系统和四个 ophub 格式的内核包。已运行 ophub 的分区创建、文件复制、内核替换及引导与根文件系统配置阶段。成品的 FAT32 与 ext4 检查通过，`uEnv.txt` 和 `fstab` 指向同一根分区 UUID，标准 initramfs 包含 xHCI 模块，`/sbin/init` 指向 systemd。头文件包已用 ARM64 外部测试模块验证。此轮未运行 GitHub Actions 的下载与发布阶段。

对 ophub 试制镜像逐项验收 USB3 与三个 USB2 口冷启动、拔盘回到 Android、首次 ext4 扩容、systemd 服务管理、有线 DHCP、Wi-Fi 和双色灯。内核更新还需复测 `uInitrd` 与模块同版本，及更新后 U 盘引导。

初版试制镜像实机通过 UUID 找到 ext4 根分区，但 Meson UART 与 8250 同时注册 `ttyS0`，导致 initramfs 无法从 `/dev/console` 交接。接入补丁改用与 G12A 相同的 UART 时钟分频模式及 `ttyAML0`。只替换 U 盘引导分区的 DTB 和 `uEnv.txt` 后，第一个 USB2 口（内置 Hub 路径 `3-1.3`）冷启动已到达 systemd 的多用户目标和串口登录页。SSH、journald、WPA supplicant 与前面板 LED 服务均已启动，SC2355 固件成功加载。
