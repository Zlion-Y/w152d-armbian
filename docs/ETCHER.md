# 用 balenaEtcher 制作 W152D 启动盘

下文的 128 MiB 启动分区、自定义启动标记和 SSH 配置对应本仓库的早期 USB 预览版。ophub 安装镜像的适用范围见 [eMMC 安装与验收](EMMC_INSTALL.md)。

此镜像面向 W152D / GXLX4 BT203。MBR 的第一分区是 128 MiB FAT32，保存 Linux 6.12 启动文件和用户配置；第二分区是 Armbian Bookworm 的 ext4 根文件系统。使用至少 4 GB、逻辑扇区为 512 字节的 USB 大容量存储设备。首次启动将第二分区和 ext4 扩到 U 盘的剩余容量。

启动后可用 `findmnt /` 和 `df -h /` 核对挂载与容量。扩容只修改同一 USB 盘的第二分区，保留第一分区。扩容出错时，系统仍可启动，日志在 `/run/w152d-grow-rootfs.log`；未完成的扩容会在下次启动时重试。大于约 2 TiB 的设备超出当前 MBR 扩容范围。

1. 解压下载包取得 `.img`，核对 SHA-256。
2. 在 Etcher 选择 **Flash from file**，选中 `.img`，再选择要清空的 U 盘。执行刷写并等待校验完成。Windows 若提示格式化第二分区，请取消。 [balenaEtcher](https://etcher.balena.io/)
3. 首次使用时，按[一次性配置 USB 优先](USB_BOOT_AND_RECOVERY.md#一次性配置-usb-优先)修改并保存原厂 U-Boot 的启动环境。配置后关闭盒子，在任一外置 USB 口插盘再上电。
4. 需要 SSH 登录时，把自己的 OpenSSH Ed25519 **公钥**存到 FAT 卷 `W152DBOOT` 上的 `w152d/config/authorized_keys`。镜像可以直接启动并生成独立的 SSH 主机密钥，也可在之后关机拔盘再添加公钥。设备的地址由 DHCP 分配，SSH 端口为 2222。

镜像已内置 `boot.arm` 和 `continuous`。首次启动会消费 `BOOT` 标记，SSH 服务就绪后才写回下一次启动标记。若首次启动被中断，可在电脑上把 `w152d/mainline/boot.arm` 恢复为四个字节的 `BOOT`，无需重刷。

## 四口验收

用 Etcher 刷写最终双分区完整镜像到一只约 8 GB 的普通 USB2 U 盘后，只轮换插口并重新上电。四次均从 Linux 6.12 挂载 `/dev/sda2` 为可写根文件系统，并到达 SSH 就绪状态。

| 物理接口 | U-Boot 入口 | Linux USB 路径 |
| --- | --- | --- |
| USB3 | 临时 `bootcmd` 上电并执行原厂 USB 入口 | `1-1` |
| USB2 | 同一 `bootcmd` 打开三口供电和 Hub，再执行原厂 USB 入口 | `3-1.1` |
| USB2 | 同上 | `3-1.2` |
| USB2 | 同上 | `3-1.3` |

四轮均使用[教程中的完整启动命令](USB_BOOT_AND_RECOVERY.md#一次性配置-usb-优先)，由原厂 `recovery_from_udisk` 找到 FAT 并执行入口脚本。本轮验证使用 RAM 环境，持久化步骤需由设备所有者执行。首次启动将第二分区从 2 GiB 扩至约 7.4 GiB，`df -h /` 报告约 7.2 GiB，后续冷启动沿用扩展后的根分区。

最终镜像已通过有线 100 Mb/s 全双工、DHCP、网关和 SSH 登录。SC2355 扫描到 12 个接入点，使用仅保存在 RAM 中的本地配置验证了 Wi-Fi 关联与 DHCP。通过 `wlan0` 向网关发送 3 次 ping 均收到回应。系统就绪后电源绿灯常亮，有线链路建立时网络绿灯常亮。

稳定性复测持续 10 分 24 秒，SSH 会话持续在线，21 次状态页探测均通过，有线网关探测 63/63，应答期间有线接口收发错误计数均未增加。三轮各 64 MiB 的写入、同步和直读哈希校验全部一致。Wi-Fi 在其中连续关联 5 分 19 秒，网关探测 36/36。运行阶段未记录新增内核崩溃、OOM 或存储 I/O 错误。

早期试制版曾遇到 Etcher 2.1.9 在校验进度到 100% 时报告写盘进程退出，写出的盘仍通过了启动测试。这一现象也有上游报告；刷盘校验异常时应核对卷和启动结果。 [Etcher #4668](https://github.com/balena-io/etcher/issues/4668)

## 驱动、固件和 Wi-Fi

镜像包含 W152D 已适配的 USB、有线以太网、SDIO 和 SC2355 驱动。制作者给[构建脚本](BUILD.md)提供匹配固件时，固件会随 initramfs 进入完整镜像。使用完整镜像时，用户只需提供自己的 Wi-Fi 网络配置。也可从 FAT 分区的 `w152d/firmware/` 加载本地准备的同一组固件。

配置无线可用 `configure_usb.py --ssid`，也可在首次配置前写入 `w152d/config/wpa_supplicant.conf` 和 SSH 公钥。蓝牙和硬解仍待板级验证。

## 自行出镜像

先生成匹配的内核启动包和全新 Armbian ext4 根文件系统，再在 Linux 安装 `util-linux`、`dosfstools`、`mtools` 和 `e2fsprogs`。将生成的普通文件交给 Etcher 刷写。

```sh
python tools/build_etcher_image.py \
  --bundle outputs/mainline-usb \
  --rootfs outputs/rootfs.ext4 \
  --output outputs/w152d-linux-6.12-usb.img
sha256sum outputs/w152d-linux-6.12-usb.img
```
