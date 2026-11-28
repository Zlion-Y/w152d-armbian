# Linux 6.12 与 Armbian 的本地构建

## 内核与 initramfs

构建基线为 [kernel.org 的 Linux 6.12.0](https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.tar.xz)，实测工具链为 AArch64 GCC 15.2.0 / Binutils 2.46。需要 Bash、Git、GNU make、交叉工具链、C 编译器、bc、bison、flex、OpenSSL 与 ELF 开发头文件。脚本校验源码归档的 SHA-256，并在新目录解包、应用补丁、安装板级设备树和驱动。

```sh
mkdir -p outputs
JOBS=8 bash tools/build_w152d_kernel.sh /path/to/linux-6.12.tar.xz outputs/w152d-linux
```

[构建补丁序列](../mainline/linux-6.12)按文件名顺序应用，包含从实测内核树整理出的 GXLX4 时钟、Amlogic USB CRG、UWE5622 和板级接线。[单项补丁](../mainline/patches)用于独立审阅，其中的改动已经包含在构建序列中。供体参考见 [Khadas common_drivers](https://github.com/khadas/common_drivers/tree/3a11a86a02e759fc57fc79410215f7c0c3a0d8e0) 和 [Armbian UWE5622](https://github.com/armbian/uwe5622/tree/d2d6bc45c5ef9cefdd53e6c51cec3ba948b84972)。

构建产物位于 `outputs/w152d-linux/build`，含 ARM64 `Image`、W152D 集成 DTB 及启动所需七个模块。无线驱动运行时加载外置固件。6.12.0 基线在新解包的源码和空构建目录中完成编译，生成的 DTB 与 Release 实测件一致。

### ophub 候选基线

同一个脚本也接受 [unifreq/linux-6.12.y 固定提交 `237b076a69ad`](https://github.com/unifreq/linux-6.12.y/commit/237b076a69ad793cad84c3997645275696bbe678) 的 [GitHub 源码归档](https://codeload.github.com/unifreq/linux-6.12.y/tar.gz/237b076a69ad793cad84c3997645275696bbe678)。归档对应 6.12.118，构建版本为 `6.12.118-w152d`。额外的[移植补丁](../mainline/unifreq-6.12.118)合并三个 Meson 时钟文件和一个 RMII 驱动文件中的差异，保留 S4/C3 的 PLL `frac_max` 设置，并修复候选基线中通用时钟门控宏的缺参。

该候选基线已编译 Image、DTB 和七个启动模块，也通过了本项目的 USB 打包。当前用户空间沿用本项目的 Armbian Bookworm。此版还需实机验收，ophub 板型接入和其内核包格式另行处理。

标准 systemd 用户空间和 ophub 板型打包的后续改动见[接入补丁](../contrib/ophub)。

### ophub HDMI 发布镜像

使用 [v0.4.0 发布页](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.0)上的标准 ophub Bookworm 镜像作为干净输入。构建在新的 ext4、磁盘镜像和内核头文件副本中进行。需要 Linux 上的 root、loop、GNU tar、GCC、ARM64 交叉工具链、make、dtc、kmod、mkimage、pigz、dosfstools 和 e2fsprogs。

```sh
sudo bash tools/build_ophub_hdmi_image.sh /path/to/v0.4.0-base.img.gz outputs/Armbian_W152D_Bookworm_6.12.118_v0.4.1.img.gz
```

脚本验证 v0.4.0 输入镜像的 SHA-256，从随镜像提供的头文件重新构建 HDMI 与 GPU 模块，安装两份板级 DTB，并用[经冷启动验证的 USB 脚本](../contrib/ophub/w152d-hdmi-usb.cmd)沿用 U-Boot 根据 EDID 配置的输出时序。镜像中的内核仍为原基底的 `6.12.118-ophub`。新的根文件系统保留标准 Armbian 首次登录流程，SSH 服务在首次启动时生成本机主机密钥。输出前检查 FAT32 和 ext4。

HS200 测试镜像向同一脚本传入第三个参数 `w152d-6.12.119-ophub-trial.tgz`。脚本校验归档，使用实机试启动的 6.12.119 内核、initramfs 和 HDMI/GPU 模块，并在该归档的 eMMC DTB 上应用 HS200 overlay。输出默认使用 HS200 DTB。恢复低速配置时，将 U 盘 `uEnv.txt` 的 `FDT=` 改为 `/dtb/amlogic/meson-gxlx4-w152d-emmc-4mhz.dtb`。

脚本从 [W152D 温度模块源码](../thermal-driver/) 编译与镜像内核匹配的驱动，并配置 systemd 开机加载。温度可从 thermal 和 hwmon 读取。

### 主线 USB 启动包

打包需要 Linux 上的 Bash、Python 3、C 编译器、binutils、dtc、kmod、gzip，以及一份 ARM64 静态 BusyBox。给第三个参数传 `-` 可生成不含外置无线固件的 initramfs。需要无线时，把以下文件放到刷好的 U 盘 `w152d/firmware/`，或用该目录作为参数生成仅在本地使用的 initramfs。

| 文件 | 输入来源 | 验收样本 SHA-256 |
| --- | --- | --- |
| `wcnmodem.bin` | 同机 vendor 的 `/firmware/wcnmodem.bin` | `2515a0a09d8e94da63aa2769b6457eee3c56c300641675da3aeb5ede09dacfaf` |
| `wifi_56630001_3ant.ini` | 同机 vendor 的 `/etc/wifi_board_config.ini` | `4c95dac0bf3681e1af31e89d6bd54494ce183839cf4a2e19c5953e2b243398f7` |
| `regulatory.db` 和 `regulatory.db.p7s` | 与内核无线监管签名匹配的一组文件 | — |

```sh
mkdir -p outputs
bash tools/build_mainline_artifacts.sh outputs/w152d-linux/build /path/to/busybox - outputs/mainline-build outputs/w152d-linux/linux-6.12
python tools/package_mainline_usb.py --artifacts outputs/mainline-build --output outputs/mainline-usb
(cd outputs/mainline-usb && sha256sum -c SHA256SUMS)
```

构建脚本用内核头文件预处理并编译 DTS，从同一内核构建目录取出匹配模块，打包为 gzip initramfs。第五个参数指定源码目录，使用树内构建时可省略。U 盘打包器验证 SHA-256 和各件的装载窗口，再生成带长度和 CRC 的 U-Boot 脚本。

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
