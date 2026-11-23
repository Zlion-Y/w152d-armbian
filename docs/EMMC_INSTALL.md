# W152D eMMC 安装与验收

2026 年 11 月 23 日，单台 64 GB 中兴 W152D 从恢复后的原厂 Android 11 出发，用 Linux 6.12.118 与 Armbian Bookworm 的安装盘完成了 eMMC 安装。后续用标准打包产物从 USB3 冷启动，在已有 Armbian 的 eMMC 上再次执行安装，并通过拔盘冷启动。这是 fork 的候选版本，上游安装 PR 仍为草稿。[fork 构建验收](https://github.com/Zlion-Y/amlogic-s9xxx-armbian/actions/runs/45189785474) · [上游安装草稿 #3798](https://github.com/ophub/amlogic-s9xxx-armbian/pull/3798)

## 安装盘和原厂 U-Boot

使用带 eMMC 安装支持的 W152D 专用镜像。打包时预选 `meson-gxlx4-w152d-emmc.dtb`，从 U 盘启动时就能识别内置 eMMC。刷盘后无需编辑 `uEnv.txt`。本项目早期 USB 预览镜像的制盘和登录方式见[发布记录](../releases/README.md)。

安装会覆盖原 Android 系统和用户数据。安装前在设备之外保留该盒子的原厂完整备份。实测沿用原厂 U-Boot 2019.01，并通过 921600、8N1、无流控的 TTL 串口设置启动环境。

1. 在原厂 U-Boot 输入 `printenv bootcmd storeboot`，记录原值。实测原厂启动项是 `run storeboot`。
2. 把下面的 `setenv` 整行输入 U-Boot。用 `run bootcmd` 先验证插盘启动，回到串口后再核对并用 `saveenv` 持久化。
3. 从安装盘启动，完成 Armbian 的首次设置。以 root 执行 `armbian-install`，选择 **602（ZTE-W152D）** 和 **ext4**。
4. 安装完成后正常关机。保持串口连接，拔盘断电后重新通电，确认盒子自动进入 eMMC 上的 Armbian。

```text
setenv bootcmd 'gpio set GPIOAO_11; gpio set GPIOC_2; gpio set GPIOC_3; gpio set GPIOC_4; gpio clear GPIOH_6; if usb start; then if fatload usb 0:1 0x03000000 aml_autoscript; then source 0x03000000; fi; fi; if fatload mmc 1:2 0x03000000 /boot.scr; then source 0x03000000; fi; run storeboot'
run bootcmd
```

此启动项先打开四个外置 USB 口的供电，再尝试 U 盘和 eMMC。安装前拔盘会回到 Android。完成安装后，插盘可优先进入 USB 救援系统，恢复 Android 要使用此前保存的原厂备份。

## eMMC 布局

| 用途 | 布局 |
| --- | --- |
| `/boot` | 108–408 MiB，300 MiB FAT32，与原厂 Amlogic 表的 `cache` 区间重合 |
| `/` | 1280 MiB 至盘尾，ext4，以 UUID 挂载 |
| 原厂引导与设备数据 | 通用安装器备份并回写本机 bootloader。原厂 Amlogic 分区表、`reserved` 和 `env` 位于保留区域 |

安装器使用通用 MBR 建表、格式化和复制流程。原厂 U-Boot 按 Amlogic 分区表用 `fatload mmc 1:2` 读取 FAT32 上的 `/boot.scr`，Linux 按 MBR 识别两个分区。eMMC DTB 采用本机实测的 4 MHz 上限。

## 实机结果

- 从原厂 Android 冷启动后保存环境，拔盘仍能进入 Android，插盘能自动进入安装镜像。
- 完整执行通用 `armbian-install`，核对分区边界、引导文件、启动参数及 `fstab`。安装后从 USB3 和第二个 USB2 口通过 USB 优先启动，拔盘从 eMMC 自动冷启动。
- eMMC 上的 `/` 和 `/boot` 正常挂载，Wi‑Fi 与 SSH 可用，systemd 为 `running`，`dpkg --audit` 无输出。
- 安装前后确认原厂引导数据、三码密钥区、有线及 Wi‑Fi MAC 一致。完整备份和原始设备标识保留在本地。[发布资料范围](PRIVACY_AND_ARTIFACTS.md)
