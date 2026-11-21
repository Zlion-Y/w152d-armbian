# 第三方组件来源

- 用户空间：Armbian 官方 rootfs cache，固定 OCI digest 见 BUILD.md。镜像内保留各包 `/usr/share/doc/<package>/copyright` 与 `/usr/share/common-licenses/`。
- Debian 软件包：Debian Bookworm main，来源为 https://deb.debian.org/debian/ 与 https://deb.debian.org/debian-security/。Release 同时提供实际安装包版本表；相应源码可从 Debian 的 Sources 索引、https://sources.debian.org/ 和包内 copyright 指向的位置获取。
- 引导包 BusyBox：Debian busybox-static ARM64，包版本与 SHA256 见 debian-busybox-source.json。对应源码在 Debian `pool/main/b/busybox/`；附件保留该包 copyright 和 GPL-2 文本。其许可证不覆盖为本机自行提取的厂商组件。
- OpenSSH、chrony、e2fsprogs、wpa_supplicant 等保留各自原始许可，不以本仓库的文档声明替代第三方许可。
- Linux 基线、内核供体、W152D 设备树与无线固件输入见[构建说明](BUILD.md)。本地生成的 initramfs 使用同机无线固件。

本项目是板级实验适配；不代表 Armbian、Debian、Amlogic 或设备厂商官方背书。许可信息与构建输入、软件包版本一同保存；不要将其他盒子的二进制或来源不明的完整固件混入附件。
