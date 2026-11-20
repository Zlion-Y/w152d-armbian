# 启动架构与兼容性

Android 阶段只是 root ADB 与 kexec 的入口。chroot 预检共用运行中的 Android 内核；实际 kexec 成功后 Android 已停止，新的原厂内核运行独立 Linux PID 1。两种结果分别记录，不能把 chroot 成功当作独立启动成功。

本机为 boot/vendor_boot v3：boot 含内核与启动 ramdisk；vendor_boot 含厂商 ramdisk、设备树等。`vendor` 与 `vendor_boot` 是不同分区。保留原厂内核不意味着可以跳过 Linux 启动 init 和根文件系统的准备。

当前的 `src/init_armbian_staged` 先加载同一固件提取的原厂网络模块与 reboot 模块，设置有线网口，启动只读回显和恢复计时。将 rootfs 解包到上限 640 MiB 的 tmpfs 后，切换到 `src/init_armbian_ram`，后者启动 SSH。SSH 使用单独密钥，禁止密码认证与端口转发。

最终环境只有 RAM 根目录及 proc/sysfs/devtmpfs/tmpfs/devpts。没有挂载 Android 的持久存储，Armbian 内的临时变更重启即丢失。预检阶段在 Android `/data/local/tmp` 写过实验文件，不能把“未挂载持久存储”误读为从未创建任何设备端临时文件。

## 已知内核边界

- 原生 ARM64 `name_to_handle_at` 返回 ENOSYS（38），确认 FHANDLE 不可用；systemd v252 上游要求包含该项，实际启动影响尚未测试。
- systemd 的版本命令运行成功，不代表 systemd/udev 作为启动服务栈兼容。当前 PID 1 为 BusyBox。
- SYSVIPC、USER_NS、CGROUP_DEVICE 等配置缺失或未开启，不能据此宣称 Docker 或容器功能可用。
- 内核 ARM64、静态 BusyBox ARM32；通过 COMPAT 执行。继承 ARM32 personality 的 `uname -m` 可能显示 armv8l，应结合 ELF、`getconf LONG_BIT=64` 和 dpkg 的 arm64 判断。
- 原厂模块启用符号版本匹配，不能直接换用其他盒子的 `.ko`。
- Wi-Fi 实测 Android 驱动名为 sdiohal、SDIO ID 为占位值；不能仅凭设备树兼容串推断无线芯片型号。

## 运行与恢复边界

RAM 启动前保留 Android、槽位和引导镜像。执行 kexec 前同步并冻结设备当时的七个可写 ext4 挂载点，脚本有失败解冻和用户态后备任务。该列表与本机挂载布局绑定，换固件后必须复核。

Linux init 中的约 180 秒计时可以处理进入 init 后的多数用户态故障；它覆盖不了早期内核挂死。手动断电恢复和 BootROM 下载恢复是不同层级，不能相互替代。

## 当前 USB 架构（2026-11-20 更新）

上述 RAM 路径保留为早期实验记录。当前启动链为原厂 U-Boot → GPIOAO_11 供电 → USB FAT32 的 aml_autoscript → 安全地址加载 Image/DTB/initramfs → 扫描 USB_ID → loop15 挂 ext4 → switch_root → BusyBox PID 1。

新发布的 initramfs 使用 Debian ARM64 静态 BusyBox，USB/ext4 驱动由原厂内核内建。原厂网络模块不在 initramfs 或发布镜像中；首次启动由使用者提供同机原厂备份提取文件。持久目录中使用 OpenSSH、wpa_supplicant 和 chrony，状态页使用持续监听的 BusyBox httpd。

根镜像不提供预置私钥、公钥或 Wi-Fi 密码。首次启动配置成功后再加载网络，SSH 主机密钥当场生成，密码认证始终关闭。PID 1 仍是 BusyBox；这条路径不证明 systemd/udev、容器或图形桌面兼容。
