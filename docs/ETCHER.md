# 用 balenaEtcher 制作 W152D 启动盘

此镜像面向 W152D / GXLX4 BT203。MBR 的第一分区是 128 MiB FAT32，保存 Linux 6.12 启动文件和用户配置；第二分区是 Armbian Bookworm 的 ext4 根文件系统。使用至少 4 GB、逻辑扇区为 512 字节的 USB 大容量存储设备。首次启动将第二分区和 ext4 扩到 U 盘的剩余容量。

启动后可用 `findmnt /` 和 `df -h /` 核对挂载与容量。扩容只修改同一 USB 盘的第二分区，保留第一分区。扩容出错时，系统仍可启动，日志在 `/run/w152d-grow-rootfs.log`；未完成的扩容会在下次启动时重试。大于约 2 TiB 的设备超出当前 MBR 扩容范围。

1. 解压下载包取得 `.img`，核对 SHA-256。
2. 在 Etcher 选择 **Flash from file**，选中 `.img`，再选择要清空的 U 盘。执行刷写并等待校验完成。 [balenaEtcher](https://etcher.balena.io/)
3. 首次使用时，按[一次性配置 USB 优先](USB_BOOT_AND_RECOVERY.md#一次性配置-usb-优先)修改并保存原厂 U-Boot 的启动环境。配置后关闭盒子，在任一外置 USB 口插盘再上电。
4. 需要 SSH 登录时，把自己的 OpenSSH Ed25519 **公钥**存到 FAT 卷 `W152DBOOT` 上的 `w152d/config/authorized_keys`。镜像可以直接启动并生成独立的 SSH 主机密钥，也可在之后关机拔盘再添加公钥。设备的地址由 DHCP 分配，SSH 端口为 2222。

镜像已内置 `boot.arm` 和 `continuous`。首次启动会消费 `BOOT` 标记，SSH 服务就绪后才写回下一次启动标记。若首次启动被中断，可在电脑上把 `w152d/mainline/boot.arm` 恢复为四个字节的 `BOOT`，无需重刷。

## 四口验收

用 Etcher 刷写测试镜像到一只约 8 GB 的普通 USB2 U 盘后，在 W152D 上逐口冷启动。四次均从同一张镜像进入 Linux 6.12、挂载可写根文件系统并到达 SSH 就绪状态。

| 物理接口 | U-Boot 入口 | Linux USB 路径 |
| --- | --- | --- |
| USB3 | 设备已有的 USB 优先入口 | `1-1` |
| USB2 | 临时打开 Hub 和端口供电，再扫描并加载脚本 | `3-1.1` |
| USB2 | 临时打开 Hub 和端口供电，再扫描并加载脚本 | `3-1.2` |
| USB2 | 临时打开 Hub 和端口供电，再扫描并加载脚本 | `3-1.3` |

Hub 路径 `3-1.1` 另验证了补齐供电后由原厂 `recovery_from_udisk` 自动找到 FAT 分区并执行入口脚本。四口共用一份镜像，端口供电和启动项由盒子的 U-Boot 决定。

本次 Etcher 2.1.9 在校验进度到 100% 时报告写盘进程退出。Windows 随后读到了 FAT 卷，四口均可启动。这一轮 Etcher 界面没有报告校验成功；该现象也有上游报告。 [Etcher #4668](https://github.com/balena-io/etcher/issues/4668)

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
