# 适配进展

## 2026-11-19：原厂内核与最小 Linux

从校验过的本机原厂备份提取 ARM64 5.4.210 内核、vendor_boot v3 设备树、静态 ARM32 BusyBox 和配套网卡模块。内核开启 COMPAT，静态 BusyBox 的 243 个 applet 在设备上核对通过。运行中内核配置与提取的 IKCONFIG 一致。

完成原生 ARM64 ELF、kexec 加载/卸载、Ubuntu ARM64 glibc chroot 验证。随后通过 kexec 独立进入 BusyBox PID 1，加载网卡模块，有线回显成功，约 90 秒后自动回到 Android。启动前同步并冻结本机七个可写 ext4 挂载点；未修改槽位或引导分区。

## 2026-11-19：Armbian 用户空间与 SSH

从 Armbian 官方 GHCR 下载固定 digest 的 Bookworm ARM64 rootfs 缓存并校验。生成包含原厂模块、自定义 init、专用 SSH 客户端/主机密钥的 RAM 根文件系统。密码认证关闭；校验 SSH 主机密钥后测试 PTY 与 SFTP。

先在 Android 的隔离挂载命名空间中完成 SSH 预检。旧 BusyBox 的 `mount -o rprivate` 在本机没有按预期隔离传播；改用 util-linux `unshare --mount --propagation private` 并核对 mountinfo。相关临时挂载随后清理，设备也已重启。

第一次直接将完整 rootfs 打成大 gzip/newc initramfs，未收到网络回显，设备提前返回 Android。缺少早期日志，根因未确认，不能直接归咎于看门狗、内存或 systemd。

改为分阶段启动：小型网络环境先工作，压缩 rootfs 作为文件放入初始 RAM 环境，随后在用户空间解包到独立 tmpfs，`switch_root` 进入 Armbian。该路径两轮通过独立 PID 1、有线网络、密钥 SSH、PTY、SFTP 和定时返回验证。

第二轮修正了重复加载模块和两个回显服务争用端口的问题。仍可看到旧引导进程使旧 `/dev`、`/run` 卸载报告 busy；未影响本轮功能，但长期运行版本需要完善子进程回收和挂载清理。

最终实测：glibc 2.36、apt 2.6.2、ARM64 用户空间，启动约 15 秒时可用内存约 1.37 GiB。最终挂载列表只有 RAM 和伪文件系统。两轮成功实验均自动返回 Android，仍为 B 槽，两槽 boot/vendor_boot 哈希与原厂一致。

## 当前路线

- [x] 原厂镜像校验、内核/DTB/模块提取。
- [x] 原生 ARM64 程序与 glibc 用户空间运行。
- [x] kexec 独立启动、小型 PID 1 与以太网。
- [x] 官方 Armbian rootfs、密钥 SSH、PTY、SFTP。
- [x] 定时返回 Android、槽位与引导哈希核对。
- [ ] USB 存储驱动、按 UUID 挂载持久根文件系统。
- [ ] 本机 BootROM USB 下载入口与恢复加载程序实测。
- [ ] 原厂 U-Boot 一次性 USB 启动。
- [ ] 有效 U 盘优先、无盘回 Android 的持久启动策略。
- [ ] init 进程管理、systemd/udev 与长期运行验证。
- [ ] Wi-Fi、显示、视频硬解与其他外设。

本仓库保存脱敏摘要；完整原始日志留在本地。没有可公开下载的板级镜像，也没有验证过 A/B 自动回退。

## 2026-11-20：USB 与无线阶段完成

后续已从 U-Boot 直接启动 U 盘 rootfs，验证文件持久化、缺少入口时 Android 回退、5 GHz 无线 DHCP、SSH/SFTP、DNS、HTTP 与 HTTPS。最终板级修正为 GPIOAO_11 供电使能和安全内核加载地址 0x01080000；未采用研究阶段 U-Boot 指令补丁。

当前推荐文档为 README.md、USB_BOOT_AND_RECOVERY.md、BUILD.md 和 VALIDATION.md。原始硬件测试镜像为设备专用；发布用户空间从官方缓存新建 ext4，首次启动再导入使用者自己的公钥、Wi-Fi 和同机原厂文件。发布附件与 Git 源码分开管理，根镜像不写入 Git 历史。
