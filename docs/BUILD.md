# 构建与本地验收

## 输入

官方 Armbian ARM64 Bookworm rootfs 缓存固定到 OCI manifest：

```text
sha256:ecf9ac2659c96e7cb6199e2bb92633710800b4630acefb83c0ec9f621313d10a
```

压缩层为 `sha256:5b6b3b6b70d41347ee54fab5c4b78117873828f280e50307e85de6bb1090cba8`。`fetch_armbian_rootfs.py --download` 会核对来源与层哈希。构建脚本会安装 Debian Bookworm main 中的 BusyBox、chrony、OpenSSH 等包，因此包列表以该次 Release 的 packages.tsv 为准；文件系统 UUID 和包仓库更新意味着它不是逐字节可复现构建。

## 用户空间镜像

需要 ARM64 Linux、root、loop、mke2fs/e2fsck、tar、zstd 和可用网络。x86 主机直接 chroot ARM64 不在本流程的验证范围内。

```sh
python tools/build_release_overlay.py --output /path/to/overlay.tar
sudo sh tools/build_rootfs.sh /path/to/armbian-base.tar.zst /path/to/overlay.tar /path/to/new-rootfs.ext4
```

工具仅新建普通文件，不接受已存在输出；`--resume` 仅用于未配置的失败构建恢复。它创建 ext4、解包官方用户空间、安装 Debian main 软件包、加入本项目启动文件、清理构建状态、卸载并执行 e2fsck。没有把运行中设备镜像删掉几个文件后直接发布：新文件系统从未写入用户 Wi-Fi 密码或设备 SSH 私钥。

构建时 DNS 通过临时只读使用构建机的解析文件，不将构建机网络配置复制进镜像。构建结束移除共享主机密钥、授权公钥、机器 ID 与日志，网络配置首次启动时由使用者导入。

```sh
gzip -6 -c new-rootfs.ext4 > w152d-rootfs-bookworm-v0.2.0-preview.ext4.gz
sha256sum w152d-rootfs-bookworm-v0.2.0-preview.ext4.gz
```

## 引导包

从 Debian 官方 busybox-static ARM64 包取得静态 busybox，核对包索引 SHA256；来源见 debian-busybox-source.json。将对应 copyright 与 GPL 文本保留在附件中。

```sh
python tools/build_bootstrap.py --busybox /path/to/busybox --output outputs/bootstrap
```

生成 aml_autoscript、initramfs、USB_ID 与清单。initramfs 使用 Debian ARM64 静态 BusyBox，不包含厂商模块、设备私钥或 Wi-Fi 配置。原厂内核和所需模块由 `tools/extract_stock.py` 在使用者本机提取。

## 验证

```sh
python -m unittest discover -s tests -v
python -m compileall -q tools
```

发布验收另外包括：initramfs 逐项解包回读、脚本头/数据 CRC、附件 SHA256、ext4 e2fsck、镜像文件级与已知凭据字节扫描、固定 SSH 主机密钥的实机连接验证。源码测试、早期 RAM 试验和发布副本的实机测试分开记录，不混用结果。
