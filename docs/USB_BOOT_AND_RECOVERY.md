# U-Boot USB 入口与恢复

适用于 W152D / GXLX4 BT203 上验证过的原厂 U-Boot 2019.01。按下文配置 USB 优先后，原厂 U-Boot 会先打开 USB3 和三个 USB2 口的供电，再扫描 U 盘并执行 FAT 根目录的 `aml_autoscript`。Linux 启动脚本和系统均在 U 盘上。

本文的供电和启动顺序也适用于 v0.4.1。该版脚本从 `usb 0:1` 读取 `uEnv.txt`、内核和设备树，首次试用时请只插一只 USB 存储设备。[v0.4.1 入门教程](GETTING_STARTED.md)

## 临时启动

串口参数为 921600、8N1、无流控。若盒子尚未配置 USB 优先，插好盘后中断 U-Boot 倒计时。以下是 USB3 口已实测的临时启动方法。

```text
gpio set GPIOAO_11
run recovery_from_udisk
```

`GPIOAO_11` 打开 USB3 口外部供电，必须在 `usb start` 之前执行。主线脚本负责 Linux 接手所需的 USB3 PHY 电源域、SDIO 复用和无线供电。临时启动只改动本次会话中的寄存器和环境。已配置 USB 优先的设备沿用现有入口。

## USB2 Hub 和三个外置口

三个 USB2 口共用板载 Hub。在扫描前拉高 `GPIOC_2`、`GPIOC_3`、`GPIOC_4` 使能端口，拉低 `GPIOH_6` 使 Hub 可见。实机使用同一个 U 盘，三个口都在这组供电设置下成功冷启动。

```text
gpio set GPIOAO_11
gpio set GPIOC_2
gpio set GPIOC_3
gpio set GPIOC_4
gpio clear GPIOH_6
usb reset
usb tree
usb storage
```

先检查 `usb storage` 能否看到启动盘。如果启动盘是第 0 块 USB 磁盘，可在同一会话加载 v0.4.1 镜像入口。

```text
fatload usb 0:1 0x03000000 aml_autoscript
source 0x03000000
```

v0.4.1 的启动盘若被枚举为其他编号，拔掉其他 USB 存储后重新扫描。早期 USB 预览版支持变量 `w152d_usbdev`，可按 `usb storage` 的编号选择 `N:1` 并设置 `w152d_usbdev=N`。只有 `fatload` 成功读到脚本后才执行 `source`。

## 一次性配置 USB 优先

适用于带 `gxlx4_bt203#` 提示符的 W152D 原厂 U-Boot 2019.01。通过 TTL 连接串口，记录原始 `bootcmd`，并核对以下启动变量和保存命令。设备的启动链不同则先确认其恢复流程。

```text
printenv bootcmd recovery_from_udisk common_dtb_load storeboot
help saveenv
```

1. 刷好镜像并只插一只启动盘。在串口输入下面的 `setenv`，再执行 `run bootcmd`，先验证一轮临时启动。第一条命令整行粘贴。

```text
setenv bootcmd 'gpio set GPIOAO_11; gpio set GPIOC_2; gpio set GPIOC_3; gpio set GPIOC_4; gpio clear GPIOH_6; setenv w152d_bootargs "${bootargs}"; run recovery_from_udisk; setenv bootargs "${w152d_bootargs}"; setenv w152d_bootargs; run common_dtb_load; run storeboot'
run bootcmd
```

2. 关机拔盘，再次中断原厂倒计时，输入同一条 `setenv` 后执行 `run bootcmd`，确认没有 U 盘时可以回到内置 Android。USB 尝试返回后会恢复原参数、重新加载内置设备树，然后执行 `storeboot`。
3. 两条路径确认后，再进入 U-Boot，重新输入同一条 `setenv`，执行 `printenv bootcmd` 核对，随后执行 `saveenv`。等待串口确认环境保存成功，然后关机并拔掉串口。以后在四个外置 USB 口任选一个，先插盘再通电。

`saveenv` 写入原机的持久 U-Boot 环境区。上述命令只调整 `bootcmd`，U-Boot 二进制、Android 启动镜像和系统分区沿用原件。需要完全保留 eMMC 原状的设备，可沿用既有 USB 优先入口或每次通过串口临时启动。

已用原厂 U-Boot 保存该命令并复位，实机自动从 USB2 启动到 Armbian systemd。

要恢复修改前的启动顺序，在 U-Boot 用 `setenv bootcmd '原先记录的完整命令'` 恢复原值并执行 `saveenv`。

## 回到设备自带启动路径

1. 关闭设备并拔掉 U 盘，然后重新上电。
2. 早期 USB 预览版可在电脑上删掉 `w152d/mainline/continuous`，把 `boot.arm` 写成四字节 `STOP`，再安全弹出。下一次 U 盘脚本将返回原厂 U-Boot，后续由设备启动顺序决定。
3. 从串口临时进入设备自带系统可运行 `run storeboot`。启动过程中若内核挂起，需要先复位或断电才会回到 U-Boot。可引导时先同步 U 盘数据。

U 盘只包含 Linux 引导文件和用户空间，不作为整机恢复介质。
