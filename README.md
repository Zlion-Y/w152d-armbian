# W152D / S905L4 Armbian

在中兴 W152D（GXLX4）上使用原厂 U-Boot 启动基于 Linux 6.12 的 Armbian。当前 ophub 适配使用 Armbian Bookworm ARM64、systemd 和标准 initramfs。实机已验证 USB3 和三个 USB2 口，以及从原厂 Android 安装到 eMMC 后的拔盘冷启动。

## ophub 适配

- USB 版已验证首次启动、U 盘自动扩容、百兆有线、5 GHz Wi‑Fi、串口和双色 LED。[接入与验证状态](contrib/ophub/README.md)
- Mali-450 MP2 GPU（`lima` `/dev/dri/renderD128` + `125~800 MHz` 动态调频）与 HDMI 显示输出（`/dev/dri/card0` Atomic KMS + `/dev/fb0` `tty1` 控制台）已完成驱动开发与实机点亮验证。[GPU 与 HDMI 驱动安装](gpu-hdmi-driver/README.md) · [硬件适配说明](docs/GPU_AND_HDMI.md)
- eMMC 安装已在一台 64 GB W152D 上走完。安装盘从 USB 启动，使用通用 `armbian-install` 写入 eMMC。安装后插盘优先启动 USB，拔盘启动 eMMC，三码密钥区和有线、Wi‑Fi MAC 均通过比对。[eMMC 安装与验收](docs/EMMC_INSTALL.md)
- USB 内核源码、stable 6.12 构建配置和 SC2355 固件**已合入 ophub**。[内核源码 #10](https://github.com/ophub/linux-6.12.y/pull/10) · [内核配置 #51](https://github.com/ophub/kernel/pull/51) · [固件 #9](https://github.com/ophub/firmware/pull/9)
- USB 板型、eMMC 设备树和无线日志补丁正在上游审阅，eMMC 安装 PR 为草稿。eMMC 候选已通过标准打包、USB3 启动和 eMMC 重装。[USB 板型 #3796](https://github.com/ophub/amlogic-s9xxx-armbian/pull/3796) · [eMMC 设备树 #11](https://github.com/ophub/linux-6.12.y/pull/11) · [无线日志 #12](https://github.com/ophub/linux-6.12.y/pull/12) · [eMMC 安装 #3798](https://github.com/ophub/amlogic-s9xxx-armbian/pull/3798)

## 本仓库的 USB 预览版

历史预览版使用自定义 BusyBox PID 1，适合复现早期 USB 启动研究。预览版的 SSH、首启配置和制盘说明适用于该系列镜像。[预览版下载与发布记录](releases/README.md)

- [构建内核与根文件系统](docs/BUILD.md)
- [生成整盘镜像并用 Etcher 制盘](docs/ETCHER.md)
- [USB 预览版首启、SSH 和实机记录](docs/MAINLINE_USB.md)
- [原厂 U-Boot 的 USB 入口与恢复](docs/USB_BOOT_AND_RECOVERY.md)
- [第三方来源](docs/THIRD_PARTY.md) · [隐私与附件](docs/PRIVACY_AND_ARTIFACTS.md)
