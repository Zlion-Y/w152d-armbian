# Linux 6.12 与 Armbian 的本地构建

## 内核与 initramfs

构建基线为 Linux 6.12.0，实测工具链为 AArch64 GCC 15.2.0 / Binutils 2.46。[DTS](../mainline/dts/meson-gxlx4-w152d-integrated-probe.dts)、[内核配置](../mainline/kernel.config)和[板级补丁](../mainline/patches)属于同一板型适配。当前仍需要已适配的 GXLX4 时钟、Amlogic USB CRG、对应头文件及 UWE5622 构建接线。供体参考见 [Khadas common_drivers](https://github.com/khadas/common_drivers/tree/3a11a86a02e759fc57fc79410215f7c0c3a0d8e0) 和 [Armbian UWE5622](https://github.com/armbian/uwe5622/tree/d2d6bc45c5ef9cefdd53e6c51cec3ba948b84972)。

- 板级 USB 时钟和 PHY 源码放入内核的 `drivers/clk/` 并编入内核。
- LED 使用 `drivers/gpio/w152d-ao-gpio.c`，将[该驱动](../mainline/drivers/w152d-ao-gpio.c)复制到内核树并应用 [Kbuild 补丁](../mainline/patches/w152d-ao-gpio-kbuild.patch)，配置启用 `GPIO_W152D_AO` 和 `LEDS_GPIO`。
- 从同一内核树构建 ARM64 的 `Image` 及 xHCI、SMSC、Meson PHY、MDIO mux、rfkill、cfg80211 和 sprdwl_ng 模块。

打包需要 Linux 上的 Bash、Python 3、C 编译器、binutils、dtc、kmod、gzip，以及一份 ARM64 静态 BusyBox。用本机取得的无线固件准备以下文件，固件仅进入本地生成的 initramfs。

| 文件 | 输入来源 | 验收样本 SHA-256 |
| --- | --- | --- |
| `wcnmodem.bin` | 同机 vendor 的 `/firmware/wcnmodem.bin` | `2515a0a09d8e94da63aa2769b6457eee3c56c300641675da3aeb5ede09dacfaf` |
| `wifi_56630001_3ant.ini` | 同机 vendor 的 `/etc/wifi_board_config.ini` | `4c95dac0bf3681e1af31e89d6bd54494ce183839cf4a2e19c5953e2b243398f7` |
| `regulatory.db` 和 `regulatory.db.p7s` | 与内核无线监管签名匹配的一组文件 | — |

```sh
mkdir -p outputs
bash tools/build_mainline_artifacts.sh /path/to/w152d-linux /path/to/busybox /path/to/firmware outputs/mainline-build
python tools/package_mainline_usb.py --artifacts outputs/mainline-build --output outputs/mainline-usb
(cd outputs/mainline-usb && sha256sum -c SHA256SUMS)
```

构建脚本用内核头文件预处理并编译 DTS，从同一内核树取出匹配模块，打包为 gzip initramfs。U 盘打包器验证 SHA-256 和各件的装载窗口，再生成带长度和 CRC 的 U-Boot 脚本。

## Armbian 用户空间

需要 ARM64 Linux、root、loop、mke2fs/e2fsck、tar、zstd 和可用网络。[Armbian 镜像来源](armbian-rootfs-source.json)固定到 ARM64 Bookworm OCI manifest。

```sh
mkdir -p outputs
python -m pip install -r requirements.txt
python fetch_armbian_rootfs.py --download
python tools/build_release_overlay.py --output outputs/overlay.tar
sudo sh tools/build_rootfs.sh /path/to/downloaded-armbian-base.tar.zst outputs/overlay.tar outputs/rootfs.ext4
```

脚本新建 ext4，安装 Debian Bookworm 软件包和 W152D 用户空间，清除构建期状态和共享密钥，最后运行 e2fsck。用同一次构建生成的软件包列表记录具体版本。输出为本地普通文件，接下来按[制盘说明](MAINLINE_USB.md)复制到 U 盘。

## 源码检查

```sh
python -m unittest discover -s tests -v
python -m compileall -q tools
```
