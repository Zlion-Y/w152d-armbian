# 2026-11-20 验证记录

| 层级 | 已验证结果 |
|---|---|
| 原始设备适配 | U-Boot 自动 USB 启动、持久 ext4、缺少入口时 Android 回退 |
| 无线 | 原厂匹配驱动、5 GHz / WPA2、DHCP、重启自动关联 |
| 用户空间 | Armbian Bookworm ARM64，BusyBox PID 1；SSH/PTY/SFTP、DNS、HTTPS |
| 状态页 | 持续监听 httpd，浏览器访问、24 个并发请求与空闲预连接测试通过 |
| 环境修改 | 两份 CRC 独立保持，其他变量与分区尾部保持，写后及重启后回读一致 |
| 内核/bootloader 刷写 | 本次 USB 适配没有写入这些分区 |

发布镜像从官方缓存重新构建，使用 Debian ARM64 BusyBox、首次启动配置及 chrony。该镜像副本的独立验收结果在 Release 的 release-manifest.json 中记录；上述原始设备适配证据不能代替它。

已知未验证：HDMI 桌面、音视频硬解、蓝牙、Wi-Fi 6/AP、长时间运行、Docker、systemd 作为 PID 1、其他型号或固件版本。原厂内核缺少 FHANDLE 等功能，不能将能执行 systemd --version 等同于完整 systemd 启动兼容。

早期失败的有效结论：GPIOH_6 只影响板载 USB2 Hub，不足以解释 USB3 插口供电；最终关键是 GPIOAO_11。0x05080000 是错误内核地址；改用 0x01080000 后完整读取通过。USB_ID 的 CRLF 和自制 ext4 写入工具的元数据校验和也曾阻塞挂载，均已修正；发布构建使用真实 mke2fs/e2fsck。

发布镜像副本已独立从 U-Boot booti 启动并验收：全新主机密钥生成、首次配置导入、64 位 ARM64 用户空间、USB loop15 根目录、5 GHz WPA2/DHCP、固定主机密钥的 SSH、状态页及正常证书校验的 HTTPS 200。chrony 在 _chrony 用户下运行，首次配置重复执行保留同一主机密钥。分发的 gzip 是测试前的干净文件，测试中使用的是副本；最终原始镜像哈希与附件清单绑定。
