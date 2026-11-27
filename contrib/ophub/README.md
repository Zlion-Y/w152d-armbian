# W152D 接入 ophub

| 仓库 | 当前状态 |
| --- | --- |
| `ophub/linux-6.12.y` | USB 内核源码已合并。eMMC 设备树和无线唤醒日志降级已分别提交。[USB 内核 #10](https://github.com/ophub/linux-6.12.y/pull/10) · [eMMC 设备树 #11](https://github.com/ophub/linux-6.12.y/pull/11) · [无线日志 #12](https://github.com/ophub/linux-6.12.y/pull/12) |
| `ophub/kernel` | 通用 stable 6.12 构建配置已合并。[配置 PR #51](https://github.com/ophub/kernel/pull/51) |
| `ophub/firmware` | SC2355 固件已合并，维护者已将文件放入 `firmware/uwe5622_sc3255/`。[固件 PR #9](https://github.com/ophub/firmware/pull/9) · [目录说明](https://github.com/ophub/firmware/pull/10#issuecomment-7089464790) |
| `ophub/amlogic-s9xxx-armbian` | USB 板型 PR 在审阅，eMMC 安装 PR 为草稿。eMMC 从原厂 Android 安装、用 fork 标准镜像重装及拔盘冷启动均已实测。[USB 板型 #3796](https://github.com/ophub/amlogic-s9xxx-armbian/pull/3796) · [eMMC 安装 #3798](https://github.com/ophub/amlogic-s9xxx-armbian/pull/3798) · [eMMC 构建验收](https://github.com/Zlion-Y/amlogic-s9xxx-armbian/actions/runs/45189785474) |

维护者给出的提交位置和板型要求见 [#3770](https://github.com/ophub/amlogic-s9xxx-armbian/issues/3770)。W152D 使用盒子上的原厂 U-Boot，通过环境变量配置 USB 供电和启动优先级。

## USB 板型

`BOARD=w152d` 使用显式选板构建，当前按 `BUILD=no` 准备。板型目录提供预编译的 `aml_autoscript`、`uEnv.txt` 和板级配置。标准 initramfs 按根分区 UUID 启动 systemd，上游 `armbian-tf` 负责扩容。打包时按维护者建议为 W152D 指定两份 SC2355 固件的链接，保留通用 UWE5622 固件路径。[USB 构建记录](https://github.com/Zlion-Y/amlogic-s9xxx-armbian/actions/runs/45115730373)

实机验收包含 USB3 和三个 USB2 外口冷启动、拔盘回原厂 Android、ext4 扩容、systemd、有线 DHCP、Wi-Fi 和双色灯。USB2 Hub 的三路供电需在扫描前打开。USB3 测试盘协商 5 Gb/s，USB2 测试盘协商 480 Mb/s。网络灯按有线链路载波切换。

本地 6.12 补丁将 W152D 的 `sdiohal_cp_sleep_wakeup entry` 日志降到 `pr_debug`，沿用原有无线唤醒逻辑。该补丁通过 6.12.118 构建和实机 Wi-Fi 双向传输测试。[构建记录](https://github.com/Zlion-Y/amlogic-s9xxx-armbian/actions/runs/45115730373) · [上游 PR #12](https://github.com/ophub/linux-6.12.y/pull/12)

## eMMC 安装

eMMC 设备树以 USB DTS 为基础，加入内置 eMMC 控制器和 MMC 别名，采用实测的 4 MHz 上限。W152D 专用安装镜像通过板型表预选 eMMC DTB。通用 `armbian-install` 走 W152D 分区参数分支，沿用原厂引导备份与回写、MBR、格式化和复制流程。

已在一台 64 GB W152D 上验证从原厂 Android 11 启动、安装、拔盘 eMMC 冷启动和插盘优先 USB。三码密钥区、有线及 Wi-Fi MAC 比对通过。[eMMC 安装与验收](../../docs/EMMC_INSTALL.md)

同版本内核离线重装已有实机记录。跨版本升级和在线取包待验证。Mali-450 MP2 GPU（`lima` + `125~800 MHz` `devfreq`）与 HDMI 显示输出（`1920x1080@60Hz` Atomic KMS、EDID、VSync 及 `/dev/fb0` `tty1` 终端）已通过外置模块与完整设备树完成实机点亮验证，详见 [GPU 与 HDMI 驱动目录](../../gpu-hdmi-driver/README.md) 与 [硬件适配说明](../../docs/GPU_AND_HDMI.md)。蓝牙、硬解、温度读取、CPU 调频和硬件看门狗未纳入本轮验收。

## 本地适配补丁

[内核补丁](kernel-board.patch)、[构建配置片段](w152d.config) 和 [Armbian 早期试制补丁](armbian-board.patch) 用于复现本地适配。Armbian 试制补丁以 [`f816cfcca674`](https://github.com/ophub/amlogic-s9xxx-armbian/commit/f816cfcca674a312985cb76271c9d28753d6dd76) 为基线，保留了当时的自定义首启、扩容和内核更新处理。当前提交范围以上表 PR 为准。

本地内核构建基线为 [6.12.118 的 `237b076a69ad`](https://github.com/ophub/linux-6.12.y/commit/237b076a69ad793cad84c3997645275696bbe678)。使用[构建说明](../../docs/BUILD.md)中的固定源归档运行：

```sh
JOBS=8 bash tools/build_w152d_kernel.sh --ophub /path/to/unifreq-237b076a.tar.gz outputs/w152d-ophub
```
