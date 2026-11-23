# W152D 主线发布

## USB 预览版

从 [v0.3.0-preview](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.3.0-preview) 下载完整镜像 ZIP、SHA-256 和 U-Boot 教程。解压 ZIP 后在 Etcher 选择其中的 `.img`。

基于 unifreq 6.12.118 的[测试镜像预览版](https://github.com/Zlion-Y/w152d-armbian/releases/tag/v0.3.1-unifreq-preview)用于复测移植结果。四口冷启动、自动扩容和网络的实机验收对应 v0.3.0-preview。

项目同时提供 Linux 6.12 板级适配源码、本地打包工具和[整盘镜像构建与四口验收记录](../docs/ETCHER.md)。

## ophub systemd 与 eMMC

当前 systemd 镜像和 eMMC 适配的进度见 [ophub 接入状态](../contrib/ophub/README.md) 与 [eMMC 安装验收](../docs/EMMC_INSTALL.md)。eMMC 试装使用预选设备树的 W152D 专用安装镜像。
