# W152D / S905L4 USB Armbian

在 W152D 上用原厂 U-Boot 的 USB 入口启动以 Linux 6.12 为基础的板级适配内核。系统使用 Armbian Bookworm ARM64 用户空间、自定义 BusyBox PID 1 和 U 盘上的持久 ext4 根文件系统。启动适配、内核、设备树和 initramfs 都随 U 盘交付。

此前的 6.12 板级构建已通过断电后无人值守启动、100 Mb/s 全双工、5 GHz Wi‑Fi 和四个 USB 外口验证。当前源码加入独立的主线启动流程与前面板 LED 支持。详细的验收状态见 [U 盘启动与验证](docs/MAINLINE_USB.md)。

- [构建内核启动件和 Armbian 根文件系统](docs/BUILD.md)
- [生成整盘镜像并用 Etcher 制盘](docs/ETCHER.md)
- [准备 U 盘、配置 SSH 和首启](docs/MAINLINE_USB.md)
- [原厂 U-Boot 的临时 USB 入口与恢复](docs/USB_BOOT_AND_RECOVERY.md)
- [第三方来源](docs/THIRD_PARTY.md) · [隐私与附件](docs/PRIVACY_AND_ARTIFACTS.md)

当前提供源码与本地构建工具。内核仍需要已移植的 GXLX4、USB CRG 与 UWE5622 供体代码。Linux 上游板级支持尚未合入。
