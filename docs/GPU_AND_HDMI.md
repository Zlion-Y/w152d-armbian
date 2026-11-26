# S905L4 (`meson-gxlx4`) Mali-450 GPU 与 HDMI 2.1 / OSD1 显示适配

针对中兴 W152D（Amlogic S905L4，`family_id = 0x4a`）在 Linux 6.12 Armbian 下无 HDMI 输出及缺少 GPU 驱动的问题，通过逆向原厂 BL33 U-Boot、Android 5.4.210 内核时钟表及 `mali.ko`，完成了显示与 3D GPU 驱动适配。源码与一键部署脚本位于 [gpu-hdmi-driver/](../gpu-hdmi-driver/README.md)。

## 硬件链路与寄存器映射

### 1. Mali-450 MP2 GPU 与无毛刺时钟树

- **GPU 控制器 (`0xfe400000`, `0x40000`)**：
  - 架构为 **ARM Mali-450 MP2**（1 个 GP + 2 个 PP，`8 KiB + 64 KiB` L2 Cache），兼容主线 `lima` 驱动（`amlogic,meson-gxl-mali`, `arm,mali-450`）。
  - GIC SPI 中断号为 `144..151`（`0x90..0x97`），依次对应 `gp`、`gpmmu`、`pp`、`pmu`、`pp0`、`ppmmu0`、`pp1`、`ppmmu1`。
  - 上电复位后内部 PMU（`0xfe402000`）默认关断核心电源域（`PMU_STATUS = 0x7`），由 `lima.ko` 在总线与核心时钟就绪后自动上电复位。
- **GXLX4 GPU 时钟门控与调频 (`w152d_gpu_clk.c`)**：
  - 总线时钟门控 `sys_mali`：`0xfe000044` (`CLKCTRL_SYS_CLK_EN0_REG1`) `BIT(6)`。
  - VPU 中断门控 `sys_vpu_intr`：`0xfe00004c` (`CLKCTRL_SYS_CLK_EN0_REG3`) `BIT(25)`。
  - 核心双分支无毛刺多路复用寄存器 `CLKCTRL_MALI_CLK_CTRL`：**`0xfe00015c`**（注：不同于 S4 的 `0x1b0`）：
    - 分支 0 (`mali_0`)：`div[6:0]`、`gate BIT(8)`、`sel[11:9]`
    - 分支 1 (`mali_1`)：`div[22:16]`、`gate BIT(24)`、`sel[27:25]`
    - 顶层无毛刺切换位：`BIT(31)`（`0 = mali_0`，`1 = mali_1`）
    - 时钟源索引：`0=xtal (24M)`、`1=gp1_pll (852M)`、`2=hifi_pll`、`3=fclk_div2p5 (800M)`、`4=fclk_div3 (666.7M)`、`5=fclk_div4 (500M)`、`6=fclk_div5 (400M)`、`7=fclk_div7 (285.7M)`。
  - 支持 `125 / 250 / 285.7 / 400 / 500 / 666.7 / 800 MHz` 共 7 档 OPP，配合 `simple_ondemand` 实现空闲自动降频至 `125 MHz`。

### 2. VPU OSD v7 线性 DMA 与 HDMI 2.1 TX KMS (`w152d_drm.c`)

- **主线 `meson_drm` 不兼容原因**：主线驱动仅覆盖旧版 GXL/G12A/SM1（VPU 基址 `0xff900000` + Synopsys `dw-hdmi` + Canvas 查表扫描）；S905L4 采用新一代 VPU 基址 `0xff000000`、自研 HDMI 2.1 TX（TOP `0xfe300000`、Core `0xfe310000`）与 OSD v7 线性物理地址直扫引擎。
- **固件交接与 OSD1 寄存器协议**：
  - 原厂 BL33 U-Boot 在启动阶段执行 `hdmitx21_init` 与 `osd_setup_hw`，完成 HDMI 2.1 EDID 读取、VENC 时序配置及 `1920x1080` OSD0 -> VPP 硬件自由缩放链路初始化。
  - OSD1 启用线性地址模式（`VIU_OSD1_CTRL_STAT` `0x1a10` `BIT(2)`）后，直接从 `VIU_OSD1_BLK1_CFG_W4`（`0x1a14`）读取 `phys_addr >> 4`，从 `VIU_OSD1_BLK2_CFG_W4`（`0x1a15` 低 12 位）读取 `stride >> 4`。
  - 支持 `XRGB8888`、`ARGB8888`、`XBGR8888`、`ABGR8888`、`RGB888`、`RGB565` 像素格式；针对无 Alpha 通道格式启用 `VIU_OSD1_CTRL_STAT2`（`0x1a2d`）硬件 Alpha 替换（`0xff`），对 `ARGB8888` 保留逐像素混合。
  - 硬件 VSync 中断位于 `GIC_SPI 197`（`0xc5`），驱动在 `probe` 阶段执行中断脉冲自检；同时从 `0x11000000` 固件日志缓冲区提取完整 128/256 字节显示器原始 EDID 注入 DRM Connector。
  - DRM 驱动名称注册为 `meson`，使 Mesa `kmsro` (`meson_dri.so`) 自动与 Mali-450 `lima` (`card1` / `renderD128`) 建立 64 字节步长对齐的 PRIME DMA-BUF 零拷贝渲染通路。

## 实机验收结果

在运行 Armbian Bookworm（`6.12.118-ophub`）的 W152D 实机上验证通过：

- **HDMI KMS 与终端输出**：`/dev/dri/card0`（`meson`）与 `/dev/fb0`（`mesondrmfb`）正常创建，`card0-HDMI-A-1` 状态为 `connected` / `enabled`，完整识别外接显示器 256 字节 EDID，硬件 VSync 中断稳定触发，HDMI 屏幕正常显示 `1920x1080@60Hz` `tty1` 登录界面。
- **Mali-450 MP2 3D 加速与调频**：`/dev/dri/card1` 与 `/dev/dri/renderD128`（`lima 1.1.0`）正常初始化 GP、PP0、PP1 与双 L2 缓存；`devfreq` `simple_ondemand` 调频正常（空闲 `125 MHz`，动态覆盖 `125 ~ 800 MHz`）。
