# v0.2.0-preview · W152D USB Linux / Wi-Fi

这版将早期 RAM/kexec 研究整理为可复现的 USB 直接启动预览：原厂 5.4.210 内核、Armbian Bookworm ARM64 用户空间、BusyBox PID 1、持久 ext4、5 GHz WPA2/DHCP、密钥 SSH/SFTP 和持续监听的状态页。

## 附件

- **w152d-rootfs-bookworm-v0.2.0-preview.ext4.gz**：约 204 MiB 压缩文件，解压为 2 GiB ext4。全新构建，未包含使用中的设备密钥、网络凭据或原始日志。
- **w152d-usb-bootstrap-v0.2.0-preview.zip**：无凭据 initramfs、aml_autoscript、USB_ID 与第三方许可说明。
- **SHA256SUMS / release-manifest.json / packages.tsv**：附件校验和、构建来源、实际验证范围和软件包版本。

原厂 Image/DTB、模块与无线固件由 `tools/extract_stock.py` 从使用者自己的同机备份提取，附件不包含这些厂商文件。完整制盘步骤见仓库 README；此包按文件放入已有 FAT32 分区，**不是整盘烧录镜像或 eMMC 线刷包**。

## 首次启动

使用 `tools/prepare_usb.py` 填入自己的 ED25519 公钥和可选 Wi-Fi 配置。密码通过交互读取，不写命令行或日志。设备首次启动生成独立 SSH 主机密钥，SSH 端口 2222，没有通用密码；状态页为 `http://设备DHCP地址:18080/`。

USB 优先激活有默认干运行、完整 env 备份、两份 CRC 独立保留和写后核验。不要复制别人设备的 env。U-Boot 阶段先打开 GPIOAO_11，内核加载地址为 0x01080000；不会写 bootloader 或 boot/vendor_boot。

## 实测

干净发布镜像的副本已在 W152D 上从 U-Boot 原生启动，完成首次配置、唯一主机密钥、ARM64 用户空间、USB 根目录、5 GHz 无线 DHCP、SSH、状态页、HTTPS 200 和首次配置幂等检查。完整 e2fsck、已知设备凭据扫描和附件 SHA256 检查通过。此前同板卡已验证持久 USB 自动启动与缺少引导入口时 Android 回退。

保持为实验预发布：HDMI/桌面、硬解、蓝牙、容器、systemd PID 1、Wi-Fi 6/AP、其他固件/型号以及长时间稳定性尚未验证。仓库仍维持原来的私有可见性。
