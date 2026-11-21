# W152D Linux 6.12 U 盘启动

W152D / GXLX4 (S905L4) 已实测用原厂 U-Boot 2019.01 的 `recovery_from_udisk` 入口直接启动带板级补丁的 Linux 6.12.0。下述流程以一只已能启动原厂内核版 Armbian 的 U 盘为起点，全部更新落在 U 盘的 FAT 分区。原机 U-Boot 二进制和持久环境沿用设备现状，原机 eMMC 无需写入。Linux 上游尚未接纳这套板级适配。

## 实机验收

记录日期为 2026-11-21 UTC。速率单位为 Mb/s，链路协商和应用吞吐分别列出。

| 项目 | 结果 |
| --- | --- |
| 无人值守软重启 | 连续两次从原厂 U-Boot 进入 6.12.0，SSH 监听后自动设好下一次主线启动标记 |
| 无人值守冷启动 | 物理断电再上电，串口全程只读。自动进入主线，SSH 恢复，两路网络均能访问网关 |
| 根文件系统 | FAT 上的 `w152d/rootfs.ext4` 经 loop 以读写方式挂载。软重启前后测试文件哈希一致 |
| 百兆有线 | 协商 100 Mb/s 全双工，DHCP 和网关通过。整合内核对同一局域网电脑传输 16 MiB，下载 90.1 Mb/s，上传 92.1 Mb/s |
| SC2355 Wi-Fi | 5 GHz 关联、DHCP、网关和公网下载通过，SDIO SDR104 实际时钟 192 MHz。相同 AP 和下载节点的单流中位数约 246–250 Mb/s，四流快照约 274–300 Mb/s。该公网测试只反映测试当时的端到端吞吐 |
| USB3 | 实测启动盘以 5 Gb/s 协商，读写通过 |
| 三个 USB2 外口 | 同一测试盘轮换插入，逐口以 480 Mb/s 枚举并读取验证 |
| 回退 | 主线脚本返回后自动执行原有 U 盘脚本，原脚本备份哈希复核一致 |

## U 盘上的启动链

1. 原厂 U-Boot 执行 FAT 根目录的 [分流脚本](../usb/mainline/w152d-usb-dispatch.cmd)。`w152d/mainline/boot.arm` 内容为四个字节的 `BOOT` 时，脚本先清除标记，再加载 `w152d/mainline/boot.scr`。标记缺失、清除失败或主线脚本返回时，分流脚本执行原有的 `w152d/aml_autoscript.usb-stock.bak`。
2. [主线脚本](../usb/mainline/w152d-usb-mainline.cmd) 用 `fatload` 装载并核对 Image、initramfs 和 DTB 的字节数，依次使用 `0x08600000`、`0x0b800000` 和 `0x0d000000`，避开板上的固件保留内存。脚本执行 `powerset 8 0` 打开 USB3 PHY 电源域，并设置 SDIO pinmux 与 `GPIOX_6` 无线供电，随后执行 `booti`。
3. initramfs 初始化 USB、有线和无线驱动后，[持久根接管脚本](../usb/mainline/w152d_usb_root) 识别启动盘、挂载现有的 ext4，并 `switch_root` 至现有 Armbian。旧版 PID 1 和 Wi-Fi 加载脚本的兼容处理落在 tmpfs。存在 `continuous` 文件时，SSH 在 2222 端口开始监听后才重新写入下一次的 `BOOT`。

验收版 initramfs 识别 USB VID:PID 为 `0781:55a3` 的启动盘，并核对 FAT 上的 `w152d/USB_ID`。板级初始化依赖已验证的原厂固件接口与寄存器状态。支持其他 U 盘前，需要更换启动盘匹配方式并重新做冷启动和多盘验收。

## 源码和构建边界

- [DTS](../mainline/dts/meson-gxlx4-w152d-integrated-probe.dts) 包括实机 RAM 布局、CPU/PSCI、串口、RMII、USB 和 SDIO。它沿用原厂 DT 的 `amlogic,gxlx4-s905l4-w150d` 兼容串。仓库内的 DTS 用 Linux 6.12 的 `include/dt-bindings` 预处理后，经 `dtc` 编译得到与实测件字节一致的 DTB。
- [内核补丁](../mainline/patches) 包括 W152D 内置 PHY 模拟初始化和 RMII RX 时钟修正，以及 SDIO 重枚举、WCN GPIO 供电和固件接管。五份补丁均在实测内核树中做过反向适用检查。两份 WCN 补丁依赖已移植的 UWE5622 及其 Amlogic `aml_hooks.c`。
- [USB 驱动](../mainline/drivers) 是实测树中放在 `drivers/clk/` 并编入内核的 W152D 专用时钟和 PHY 初始化代码。局部内核补丁仍依赖实测树的 GXLX4 时钟、Amlogic USB CRG、头文件和构建适配。已核对的供体包括 [Khadas common_drivers](https://github.com/khadas/common_drivers/tree/3a11a86a02e759fc57fc79410215f7c0c3a0d8e0) 和 [Armbian UWE5622](https://github.com/armbian/uwe5622/tree/d2d6bc45c5ef9cefdd53e6c51cec3ba948b84972)。
- [实测内核配置](../mainline/kernel.config) 来自生成实测 Image 的工作树，工具链为 AArch64 GCC 15.2.0 / Binutils 2.46。完整供体改动和 initramfs 组装仍待补齐，当前仓库可独立复现 DTB 和启动脚本，整套内核及 initramfs 仍需要已有适配产物。

无线使用同机原厂固件，以下为验收样本的来源与校验值。使用现有的 [本地提取流程](BUILD.md) 获取，按兼容驱动要求放入 initramfs 的 `/lib/firmware/`。该构建还需要匹配的 `regulatory.db`、`regulatory.db.p7s` 和与 Image 同次构建的内核模块。

| 原厂 vendor 中的路径 | initramfs 文件名 | SHA-256 |
| --- | --- | --- |
| `/firmware/wcnmodem.bin` | `wcnmodem.bin` | `2515a0a09d8e94da63aa2769b6457eee3c56c300641675da3aeb5ede09dacfaf` |
| `/etc/wifi_board_config.ini` | `wifi_56630001_3ant.ini` | `4c95dac0bf3681e1af31e89d6bd54494ce183839cf4a2e19c5953e2b243398f7` |

用接近实测版本的 `cpp` 和 `dtc` 编译 DTB，以下命令从仓库根目录运行。

```sh
mkdir -p outputs/mainline-dtb
cpp -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
  -I "$LINUX_612_INCLUDE" mainline/dts/meson-gxlx4-w152d-integrated-probe.dts \
  -o outputs/mainline-dtb/integrated-probe.dts
dtc -I dts -O dtb -o outputs/mainline-dtb/integrated-probe.dtb \
  outputs/mainline-dtb/integrated-probe.dts
```

`LINUX_612_INCLUDE` 指向已解包 Linux 6.12 源码的 `include`。实测 DTB 的 SHA-256 为 `cab62bb66cc133cca3dbe3b6a6a08baa167bbee3ed7adc50bf22525a8f57feaa`。

## 为已有构建产物生成 U 盘文件

输入目录必须包含同一套 `Image`、`integrated-probe.dtb`、`initramfs.cpio.gz`、`kernel.config` 和覆盖这四个文件的 `SHA256SUMS`。initramfs 需要包含主线板级启动逻辑及匹配的模块。打包器核验哈希和装载窗口，生成带实际文件长度与 U-Boot 脚本 CRC 的 U 盘文件。

```sh
python tools/package_mainline_usb.py --artifacts outputs/mainline-build --output outputs/mainline-usb
(cd outputs/mainline-usb && sha256sum -c SHA256SUMS)
```

首次升级在电脑上挂载已能启动原厂内核版 Armbian 的 U 盘，按以下顺序复制。

1. 保留 FAT 根目录现有的 `aml_autoscript` 到 `w152d/aml_autoscript.usb-stock.bak`，核对两份文件一致。已有备份时确认它确实是原厂内核版的可用脚本。主线分流脚本本身不能用作备份。
2. 将输出中的 `Image`、`integrated-probe.dtb`、`initramfs.cpio.gz` 和 `boot.scr` 放到 `w152d/mainline/`。现有的 `w152d/USB_ID`、`w152d/rootfs.ext4` 和原厂内核版启动文件供两个启动路径继续使用。
3. 将生成的 `aml_autoscript` 复制到 FAT 根目录。首次验证只在 `w152d/mainline/boot.arm` 写入四个字节的 `BOOT`（无换行），安全弹出 U 盘，再接入盒子 USB3 口启动。完成单次启动验证后，可在 `w152d/mainline/` 创建空的 `continuous` 并重新写入 `BOOT`，启用后续主线自动启动。

## 返回原厂内核版

去掉 FAT 上的 `w152d/mainline/continuous`，将 `w152d/mainline/boot.arm` 写为四个字节的 `STOP`，同步后重启。Linux 主线运行时 FAT 挂载在 `/media/w152d-usb`。要恢复原入口文件，把 `w152d/aml_autoscript.usb-stock.bak` 复制回 FAT 根目录的 `aml_autoscript`。若内核卡住，断电后可在电脑上恢复 U 盘文件再上电。拔掉 U 盘时，设备沿用原有的 Android 启动路径。

## 整盘镜像与 ophub

当前打包产物是 FAT 文件集合。适合用 balenaEtcher 写入的整盘镜像还需要定义分区、整理首次启动配置、按 USB 卷标或 UUID 识别启动介质，并在新 U 盘上验收冷启动与回退。已测用户空间为仓库现有的 Armbian Bookworm；移植到 ophub 时，可从板型记录、`bootfs/rootfs` 和内核补丁接入。板级初始化继续随 U 盘交付。 [ophub 新增板型说明](https://github.com/ophub/amlogic-s9xxx-armbian/blob/main/documents/README.md#1215-how-to-add-new-supported-devices)
