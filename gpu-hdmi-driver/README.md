# 中兴 W152D (`Amlogic S905L4` / `meson-gxlx4`) Armbian GPU 与 HDMI 显示驱动

本目录提供针对中兴 W152D（SoC：`Amlogic S905L4` / `gxlx4`，内核：`6.12.x-ophub`）逆向实证开发的 **Mali-450 MP2 GPU 时钟驱动**、**VPU OSD1 + HDMI 2.1 TX Atomic KMS 显示驱动**、**运行态动态 DT Overlay 注入模块**及**完整设备树源码**。

硬件寄存器细节与适配架构说明见 [docs/GPU_AND_HDMI.md](../docs/GPU_AND_HDMI.md)。

## 一、故障根因摘要

1. **设备树节点与控制台参数缺失**：初始精简版 `meson-gxlx4-w152d(-emmc).dtb` 仅包含串口、网卡、USB 与存储节点，缺失 GPU、VPU/HDMI 及 Framebuffer 节点，且 `/boot/uEnv.txt` 仅启用了串口 `console=ttyAML0,921600n8`（缺少 `console=tty1`），导致系统无 `/dev/dri/*` 与 `/dev/fb0`，HDMI 无画面输出。
2. **S905L4 (`gxlx4`) GPU 时钟寄存器偏移差异**：
   - S905L4 的 Mali-450 MP2 基址位于 `0xfe400000`（中断 `GIC_SPI 144..151`），总线时钟门控位于 `0xfe000044` (`CLKCTRL_SYS_CLK_EN0_REG1`) `BIT(6)` (`sys_mali`)；
   - 双分支无毛刺核心时钟控制寄存器位于 **`0xfe00015c`** (`CLKCTRL_MALI_CLK_CTRL`，不同于 S4 的 `0x1b0`)。冷启动默认 `0xfe00015c = 0`，缺少该时钟驱动会导致 `lima` 无法访问 GPU 寄存器。
3. **S905L4 新架构 VPU OSD v7 + HDMI 2.1 TX 显示链路**：
   - S905L4 采用统一寄存器窗口 VPU（`0xff000000`，OSD v7 线性物理地址扫描 `VIU_OSD1_BLK1_CFG_W4 = 0x1a14`、16B 步长 `0x1a15`）与自研 HDMI 2.1 TX（`0xfe300000` / `0xfe310000`），主线旧版 `meson_drm`（仅支持 GXL/G12A/SM1 `0xff900000` + Synopsys `dw-hdmi`）无法匹配；
   - 原厂 BL33 U-Boot (`hdmitx21_init` + `osd_setup_hw`) 在上电阶段已完成 HDMI 2.1 EDID 握手、VENC 时序及 OSD0 -> VPP 硬件缩放器初始化，早期 `simplefb` 与本目录 `w152d_drm` Atomic KMS 驱动沿用固件留下的输出时序，并接管 32 位色线性 DMA 扫描、硬件 VSync 中断、EDID 透传及 `fbcon` 控制台。

## 二、文件清单

| 文件 | 说明 |
| --- | --- |
| `w152d_gpu_clk.c` | S905L4 Mali-450 总线门控 (`0xfe000044[6]`) + 双分支无毛刺动态调频时钟驱动 (`0xfe00015c`，支持 `125 ~ 800 MHz` 7 档 `devfreq` OPP) |
| `w152d_drm.c` | S905L4 VPU OSD1 线性 DMA + HDMI 2.1 状态/EDID Atomic KMS 驱动（注册 DRM 驱动名 `meson` 以自动激活 Mesa `kmsro` + `lima` PRIME 零拷贝 3D 加速，提供 `/dev/dri/card0` 与 `/dev/fb0`） |
| `w152d_dt_overlay.c` + `w152d_overlay.dts` | 运行态动态 DT Overlay 注入兜底模块（支持免重启即时生效；若基础 DTB 已含节点则自动跳过） |
| `meson-gxlx4-w152d-emmc.dts` | 集成早期 `simple-framebuffer`、`gpu-clock-controller@fe00015c`、`gpu@fe400000`（含 OPP 表）与 `display@ff000000` 的完整 eMMC 版设备树 |
| `meson-gxlx4-w152d.dts` | 纯 USB 启动版对应完整设备树 |
| `Makefile` / `gcc-wrap.sh` | 兼容 Debian Bookworm 本机 GCC 12（过滤 GCC 15 头文件参数）与交叉编译工具链的构建脚本 |
| `install.sh` | 实机一键编译、修复 `modpost` GLIBC 兼容、安装模块与 DTB、配置开机自启并尝试加载驱动的部署脚本 |

## 三、在已运行的 W152D Armbian 上一键编译与安装

确保实机已安装 `build-essential`、`device-tree-compiler`、`python3` 及对应内核的 `linux-headers-$(uname -r)`（ophub 镜像默认自带 `/usr/src/linux-headers-*`），在仓库根目录执行：

```bash
sudo bash gpu-hdmi-driver/install.sh
```

脚本会自动完成编译、安装、写入 `/etc/modprobe.d/w152d-gpu-hdmi.conf` 与 `/etc/modules-load.d/w152d-gpu-hdmi.conf`、更新 `/boot/dtb/amlogic/*.dtb` 及 `/boot/uEnv.txt`（追加 `console=tty1`），并通过 `w152d_dt_overlay` 在当前系统尝试加载驱动。HDMI 出图取决于固件交接时的 VENC 和 HDMI TX 配置，见[本地镜像复测](../docs/GPU_AND_HDMI.md#2026-11-27-本地镜像复测)。

## 四、手动编译与核验命令

```bash
cd gpu-hdmi-driver
make

# 核验 DRM / KMS 与 Framebuffer 节点
ls -l /dev/dri /dev/fb0
cat /sys/class/drm/card0-HDMI-A-1/status /sys/class/drm/card0-HDMI-A-1/enabled

# 核验 Mali-450 GPU devfreq 动态调频状态
cat /sys/class/devfreq/fe400000.gpu/governor /sys/class/devfreq/fe400000.gpu/cur_freq
```
