# W152D 主线发布

## v0.4.3 温度与 CPU 自动调频

[v0.4.3](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.3) 基于 Linux `6.12.119-ophub`，开机加载 SoC 温度和 CPU 调频调压驱动。原厂表 2 实测覆盖 100–2016 MHz 共 13 档，镜像设定 `schedutil` 默认范围为 500–2016 MHz。干净镜像通过 U 盘整盘刷写、首次设置和重启验收。四核负载升到 2016 MHz，停载后回到 500 MHz。[调频实测](../cpufreq-driver/README.md) · [温度驱动](../thermal-driver/README.md)

## v0.4.2 eMMC HS200

[v0.4.2](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.2) 使用 Linux `6.12.119-ophub`，默认启用 eMMC HS200。已在单台 64 GB W152D 上验证干净镜像从 USB 首次启动、安装到 eMMC、拔盘冷启动。冷启动后 HS200 实际时钟为 192 MHz，顺序直读 1 GiB 测得 139 MB/s。[安装与验收](../docs/EMMC_INSTALL.md)

## v0.4.1 HDMI 与 GPU

[v0.4.1](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.1) 提供 Armbian Bookworm 与 Linux `6.12.118-ophub` 的 W152D 整盘镜像。核对 `SHA256SUMS` 后解压 `.img.gz`，用 Etcher 写入 U 盘。首次开机在控制台完成 Armbian 账号设置，SSH 主机密钥由本机生成。

USB 启动沿用原厂 U-Boot 通过 EDID 配置的 HDMI 输出。已在一台 4K 电视上测试 2160p60、Lima、U 盘扩容、有线和 SSH。HDMI 音频、运行中热插拔及该版本的 eMMC 安装待验收。[刷盘与首次登录](../docs/GETTING_STARTED.md) · [实机记录](../docs/GPU_AND_HDMI.md) · [构建说明](../docs/BUILD.md)

## 历史 USB 预览版

从 [v0.3.0-preview](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.3.0-preview) 下载完整镜像 ZIP、SHA-256 和 U-Boot 教程。解压 ZIP 后在 Etcher 选择其中的 `.img`。

基于 unifreq 6.12.118 的[测试镜像预览版](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.3.1-unifreq-preview)用于复测移植结果。四口冷启动、自动扩容和网络的实机验收对应 v0.3.0-preview。

项目同时提供 Linux 6.12 板级适配源码、本地打包工具和[整盘镜像构建与四口验收记录](../docs/ETCHER.md)。

## ophub systemd 与 eMMC

[v0.4.0](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.0) 是完成 eMMC 安装实机验收的镜像。[eMMC 安装教程](../docs/EMMC_INSTALL.md) · [ophub 适配记录](../contrib/ophub/README.md)
