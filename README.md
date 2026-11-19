# W152D / S905L4 Armbian 适配记录

目标：先使用原厂内核运行 Armbian，再验证持久根文件系统与“插 U 盘启动 Linux、拔盘回 Android”。这是板级适配研究记录，目前没有可刷机发行版，也不代表 Armbian 官方支持 W152D。

**2026-11-19：已通过 kexec 两次独立启动官方 Armbian Bookworm ARM64 用户空间，密钥 SSH、PTY 交互终端和 SFTP 均通过；两次均自动返回 Android，boot/vendor_boot 两槽摘要未变。**

| 项目 | 当前状态 |
|---|---|
| SoC / 原厂 DT 标识 | S905L4 / `gxlx4_s905l4_w150d` |
| 内核 | 原厂 ARM64 Linux 5.4.210 |
| 用户空间 | Armbian 26.11.0-trunk.136 Bookworm / Debian 12 ARM64 |
| PID 1 | 自定义 BusyBox `/init`；systemd 尚未作为 PID 1 启动 |
| 根文件系统 | RAM 中的 tmpfs；未持久化 |
| 网络 | 原厂模块驱动的有线网口已通过；Wi-Fi 未验证 |
| 远程操作 | 专用密钥 SSH，端口 2222；PTY、SFTP 通过 |
| USB 直接引导 | 未实测；原厂环境中存在 USB 恢复加载入口 |
| 启动分区刷写 | 本轮未改写 boot、vendor_boot、bootloader 或槽位 |

```text
Android root ADB
    → kexec → 原厂内核 + 小型网络引导环境
    → 将 Armbian 解包到 tmpfs → switch_root
    → Armbian ARM64 用户空间 + 密钥 SSH
    → 约 180 秒计时重启 → Android
```

## 记录与路线

- [实验进展与失败记录](docs/PROGRESS.md)
- [启动架构与内核限制](docs/ARCHITECTURE.md)
- [USB 优先启动与救援验证计划](docs/USB_BOOT_AND_RECOVERY.md)
- [脱敏后的实测摘要与输入哈希](docs/evidence/2026-11-19.json)

优先事项：验证 USB 存储与持久根文件系统；确认本机 BootROM USB 下载救援入口；验证一次性 U-Boot USB 引导；最后才考虑保存 USB 优先启动环境。systemd/udev、长期运行、Wi-Fi、显示和硬解仍需后续验证。

## 源码与本地复现

仓库保存实际实验脚本的整理版本。ADB、原厂输入和 OpenSSL 路径已参数化，保留 `--execute` 才进行内核交接的保护。整理后的源码完成本地语法与离线构建校验，硬件全链路证据来自整理前的本机实验；不把路径参数化本身算作新的硬件实测。

需要 Python 3.10+、ADB、OpenSSL，以及自行备份的同机原厂镜像。原厂固件、下载缓存、根文件系统归档、私钥和原始设备日志均不上传。

```powershell
python -m pip install -r requirements.txt

# 仅作格式示例：替换为自己的原厂备份目录、ADB、设备地址和网关。
$env:W152D_STOCK_DIR = 'C:\path\to\stock-backup'
$env:ADB = 'C:\path\to\platform-tools\adb.exe'
python build_probe.py
python build_network_probe.py --ip 192.0.2.16 --gateway 192.0.2.1 --return-after 90

# 从固定 digest 下载官方 rootfs 缓存，校验并解压为 tar。
python fetch_armbian_rootfs.py --download
python prepare_armbian_rootfs.py --serial '192.0.2.16:5555'
python build_staged_armbian.py
```

`192.0.2.0/24` 是文档示例地址，必须换成盒子实际地址。网络探针暂时使用从 Android 核对到的以太网地址作为静态地址，不能直接套到其他局域网。

使用 `device_checks.py --serial ...` 采集运行时设备树，再用以下命令进行**仅加载、卸载的预检**：

```powershell
python run_ram_probe.py --serial '192.0.2.16:5555' `
  --runtime-dtb 'evidence\device_时间戳\runtime.dtb' --probe-dir armbian-staged
```

实际内核交接需另加 `--execute`，并提前在另一终端启动 `verify_armbian_ssh.py --native --seconds 220`。根文件系统内的计时只在 `/init` 执行后有效，早期内核卡死仍可能需要断电。执行脚本内冻结的挂载点列表来自本机，换固件或挂载布局后需要重新核对。

`wait_android_recovery.py --serial ...` 检查返回 Android；`record_armbian_validation.py --serial ...` 将当前启动包与本地验证记录绑定，并重新核对引导分区哈希。其他脚本用途见其 `--help` 或文件头。

## 仓库内容边界

这里只提交自建脚本、文档和经过筛选的结果摘要。原厂内核、BusyBox、模块与设备树由本机固件提取，各自遵循原有许可和分发条件；仓库不打包分发这些二进制。生成的 rootfs 含专用 SSH 主机私钥，不能当作通用镜像公开发布。

## 上游来源

- [Armbian 官方 rootfs 缓存](https://github.com/armbian/os/pkgs/container/os%2Frootfs-arm64-bookworm-minimal)
- [AOSP vendor_boot 格式](https://source.android.com/docs/core/architecture/partitions/vendor-boot-partitions)
- [systemd v252 内核要求](https://github.com/systemd/systemd/blob/v252/README)
- [U-Boot 晶晨启动流程](https://docs.u-boot.org/en/latest/board/amlogic/boot-flow.html)
- [ophub 多启动激活脚本，仅作对照](https://github.com/ophub/amlogic-s9xxx-armbian/blob/main/build-armbian/armbian-files/platform-files/amlogic/bootfs/aml_autoscript.cmd)
