# 中兴 W152D Armbian

面向中兴 W152D（Amlogic S905L4 / GXLX4）的独立 Armbian 适配项目。本仓库是 W152D 镜像、源码、教程和问题反馈的主入口。发行版基于 Armbian Bookworm ARM64 和 ophub 内核，使用盒子上的原厂 U-Boot 启动。

**当前正式版 v0.4.3** · Linux 6.12.119-ophub · 推荐先从 USB 启动试用。

[发布页](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.3) · [下载 USB 镜像](https://github.com/Zlion-Y/w152d-armbian/releases/download/v0.4.3/Armbian_W152D_Bookworm_6.12.119_v0.4.3.img.gz) · [SHA256SUMS](https://github.com/Zlion-Y/w152d-armbian/releases/download/v0.4.3/SHA256SUMS)

## 第一次使用

1. 下载并校验压缩镜像，解压后用 balenaEtcher 写入备用 U 盘。写入会清空所选 U 盘。
2. 关机后接好 HDMI、键盘和网线，只插这一只启动盘。已配置 USB 优先的盒子可以直接上电，原厂启动顺序的盒子先用 TTL 串口临时引导。
3. 在 HDMI 控制台或 TTL 串口完成 Armbian 首次设置。之后从路由器查看盒子的 IP，再通过 SSH 连接。

[完整教程：校验、刷盘、启动、SSH 和故障排查](docs/GETTING_STARTED.md)

## 功能与验收范围

| 功能 | 实测结果 |
| --- | --- |
| USB 启动 | v0.4.3 已在一台 64 GB W152D 上通过整盘刷写、首次设置及重启。四个外置口的历史验收见[板型记录](contrib/ophub/README.md#usb-板型)。 |
| HDMI | v0.4.1 在一台 4K 电视上冷启动输出 2160p60，控制台使用 1080p 缓冲区。HDMI 音频当前不可用，运行中热插拔及其他屏幕的兼容性待验证。 |
| GPU | Mali-450 的 Lima 内核接口可用，可见 `/dev/dri/renderD128`。桌面 3D 渲染待验证。 |
| 网络 | 百兆全双工、DHCP 和 SSH 已验证。v0.4.1 已验证 SC2355 扫描，5 GHz 关联与传输见[历史实测](docs/MAINLINE_USB.md#实机记录)。 |
| eMMC | v0.4.2 已在单台 64 GB W152D 上完成安装和拔盘冷启动，HS200 实际时钟 192 MHz，冷启动后顺序直读 139 MB/s。 |
| 温度及 CPU 调频 | v0.4.3 开机加载两个驱动。已验证原厂表 2 的 13 档，`schedutil` 默认范围为 500–2016 MHz。实测停载后回到 500 MHz。 |

## 文档

| 你想做什么 | 去哪里看 |
| --- | --- |
| 从 U 盘启动并通过 SSH 登录 | [入门教程](docs/GETTING_STARTED.md) |
| 配置 USB 优先或恢复原启动顺序 | [原厂 U-Boot 启动与恢复](docs/USB_BOOT_AND_RECOVERY.md) |
| 安装到内置 eMMC | [eMMC 安装教程](docs/EMMC_INSTALL.md) |
| 查看 HDMI、Lima 或内核升级实测 | [GPU 与 HDMI 实测](docs/GPU_AND_HDMI.md) · [驱动源码与安装](gpu-hdmi-driver/README.md) |
| 读取或适配 SoC 温度 | [温度驱动与实测](thermal-driver/README.md) |
| 查看 CPU 自动调频和 VDDCPU 调压 | [调频驱动与实测](cpufreq-driver/README.md) |
| 自己编译内核或重做发布镜像 | [构建说明](docs/BUILD.md) |
| 找旧版或查看 ophub 接入记录 | [历史发布](releases/README.md) · [ophub 适配记录](contrib/ophub/README.md) |

遇到问题请附上镜像版本、启动介质、`uname -r` 和脱敏后的故障日志。显示问题请同时说明电视或显示器型号，以及有无信号和画面。[提交问题](https://github.com/Zlion-Y/w152d-armbian/issues/new) · [隐私与附件](docs/PRIVACY_AND_ARTIFACTS.md)

感谢 mmlxm2025 提供 HDMI/GPU 驱动和内置有线 PHY 修复。[贡献记录](https://github.com/Zlion-Y/w152d-armbian/pull/1) · [第三方来源](docs/THIRD_PARTY.md)
