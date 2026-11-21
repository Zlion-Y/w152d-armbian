# USB 启动、环境修改与恢复

本文记录原厂 5.4.210 预览版的启动顺序设置。已具备 USB 启动入口的 W152D 可直接使用 [Linux 6.12 适配的 U 盘脚本](MAINLINE_USB.md)，该升级流程仅写入 U 盘。

## 已实测

原厂 U-Boot 能读取 `aml_autoscript`，以 `booti` 启动内核、initramfs 与原厂 DTB，挂载 U 盘上的 ext4 loop 镜像。根文件持久化已跨重启读回。持久 bootcmd 自动启动已通过；临时隐藏 aml_autoscript 后，原厂 Android 回退成功。

最终只需在 USB 扫描前执行 `gpio set GPIOAO_11`。未采用研究阶段的模拟 PHY、供电域、端口数或 U-Boot 指令 RAM 补丁。

## 精确加载布局

| 内容 | 地址 | 说明 |
|---|---|---|
| ARM64 Image | 0x01080000 | image_size 及文件大小均检查低于 DDR 参数 0x02bffe00 |
| DTB | 0x01000000 | booti 前 `fdt resize 0x10000` |
| initramfs | 0x10000000 | 使用本次 fatload 的 filesize |
| 禁用地址 | 0x05080000 | 位于本机 secmon 0x05000000..0x08400000 保留区 |

TTL 为 921600、8N1，无硬件流控。U-Boot 的这个构建没有 sleep 命令，不能直接照搬其他晶晨教程。

## 环境备份与激活

本机 env 分区 8 MiB；偏移 0 和 0x10000 各有一份独立 CRC32 的 64 KiB 副本。它们并非完全相同，不能拿第一份覆盖第二份。工具分别解析和重建，仅替换 bootcmd；0x20000 之后保持不动。

```text
gpio set GPIOAO_11; setenv w152d_bootargs "${bootargs}"; run recovery_from_udisk; setenv bootargs "${w152d_bootargs}"; setenv w152d_bootargs; run common_dtb_load; run storeboot
```

推荐流程：确认同机原厂备份和 TTL 可用 → U 盘文件准备 → 不保存环境的一次性启动 → 离线审阅环境补丁 → 明确执行持久写入。

```powershell
adb -s 192.0.2.18:5555 root
adb connect 192.0.2.18:5555
python tools/activate_usb_adb.py --serial 192.0.2.18:5555 --output outputs/env-review

# 确认备份与差异后，使用另一个尚不存在备份文件的目录执行。
python tools/activate_usb_adb.py --serial 192.0.2.18:5555 --output outputs/env-applied --execute
```

当前构建只支持已核对的 W152D 型号和上述环境格式；尺寸、CRC、变量或型号不符合即停止。默认不写设备。`--execute` 只向 env 写 128 KiB，不写 bootloader、boot、vendor_boot 或槽位状态。备份包含设备专属信息，仅在本机保存。

## 回退

- USB 脚本缺失或加载返回：保留的原厂 storeboot 路径进入 Android。
- 已进入 Linux 后卡死：先同步；需要拔盘时断电后拔，再上电进入 Android。不能保证内核故障自动回退。
- 仍能进入 U-Boot：`run storeboot` 可临时启动 Android，不必立即保存环境。
- env 损坏或 bootloader 损坏：属于不同层级，需要同机备份和匹配恢复入口。不能把本项目的文件复制包当作完整线刷救砖包。

不提供通用 bootloader 替换镜像。设备采用晶晨私有存储布局，不能用通用分区工具重排 eMMC。旧 [架构说明](ARCHITECTURE.md) 记录 RAM 阶段，当前 USB 启动以上述路径为准。
