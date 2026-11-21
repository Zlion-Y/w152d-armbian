# U-Boot USB 入口与恢复

适用于 W152D / GXLX4 BT203 上验证过的原厂 U-Boot 2019.01。测试机已有 USB 优先入口，所以可以自动执行 FAT 根目录的 `aml_autoscript`。板级启动逻辑和 Linux 均在 U 盘上。

## 临时启动

串口参数为 921600、8N1、无流控。若设备没有可自动发现 U 盘的入口，可以中断 U-Boot 倒计时，在当前会话运行：

```text
gpio set GPIOAO_11
run recovery_from_udisk
```

`GPIOAO_11` 打开 USB3 口外部供电。主线脚本负责 USB3 PHY 电源域、SDIO 复用和无线供电。临时启动只改动本次会话中的寄存器和环境。已配置 USB 优先的设备沿用现有入口。

## 回到设备自带启动路径

1. 关闭设备并拔掉 U 盘，然后重新上电。
2. 保留 U 盘时，可在电脑上删掉 `w152d/mainline/continuous`，把 `boot.arm` 写成四字节 `STOP`，再安全弹出。下一次 U 盘脚本将返回原厂 U-Boot，后续由设备启动顺序决定。
3. 从串口临时进入设备自带系统可运行 `run storeboot`。启动过程中若内核挂起，需要先复位或断电才会回到 U-Boot。可引导时先同步 U 盘数据。

U 盘只包含 Linux 引导文件和用户空间，不作为整机恢复介质。
