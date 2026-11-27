# W152D 主线发布

## v0.4.1 HDMI 与 GPU

[v0.4.1](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.1) 提供 Armbian Bookworm 与 Linux `6.12.118-ophub` 的 W152D 整盘镜像。核对 `SHA256SUMS` 后解压 `.img.gz`，用 Etcher 写入 U 盘。首次开机在控制台完成 Armbian 账号设置，SSH 主机密钥由本机生成。

USB 启动沿用原厂 U-Boot 通过 EDID 配置的 HDMI 输出。已在一台 4K 电视上测试 2160p60、Lima、U 盘扩容、有线和 SSH。HDMI 音频、运行中热插拔及该版本的 eMMC 安装待验收。[刷盘与首次登录](../docs/GETTING_STARTED.md) · [实机记录](../docs/GPU_AND_HDMI.md) · [构建说明](../docs/BUILD.md)

## 历史 USB 预览版

从 [v0.3.0-preview](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.3.0-preview) 下载完整镜像 ZIP、SHA-256 和 U-Boot 教程。解压 ZIP 后在 Etcher 选择其中的 `.img`。

基于 unifreq 6.12.118 的[测试镜像预览版](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.3.1-unifreq-preview)用于复测移植结果。四口冷启动、自动扩容和网络的实机验收对应 v0.3.0-preview。

项目同时提供 Linux 6.12 板级适配源码、本地打包工具和[整盘镜像构建与四口验收记录](../docs/ETCHER.md)。

## ophub systemd 与 eMMC

[v0.4.0](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.4.0) 是完成 eMMC 安装实机验收的镜像。[eMMC 安装教程](../docs/EMMC_INSTALL.md) · [ophub 适配记录](../contrib/ophub/README.md)
