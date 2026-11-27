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

## PR #1 实机验收记录

PR 记录在运行 Armbian Bookworm（`6.12.118-ophub`）的 W152D 实机上验证通过：

- **HDMI KMS 与终端输出**：`/dev/dri/card0`（`meson`）与 `/dev/fb0`（`mesondrmfb`）正常创建，`card0-HDMI-A-1` 状态为 `connected` / `enabled`，完整识别外接显示器 256 字节 EDID，硬件 VSync 中断稳定触发，HDMI 屏幕正常显示 `1920x1080@60Hz` `tty1` 登录界面。
- **Mali-450 MP2 3D 加速与调频**：`/dev/dri/card1` 与 `/dev/dri/renderD128`（`lima 1.1.0`）正常初始化 GP、PP0、PP1 与双 L2 缓存；`devfreq` `simple_ondemand` 调频正常（空闲 `125 MHz`，动态覆盖 `125 ~ 800 MHz`）。
- **关联稳定性与日志修复**：
  - 设备树为 `gpu@fe400000` 提供常开 `regulator-mali`（`mali-supply`），消除 `lima` 启动时 `_opp_set_regulators: no regulator (mali) found` 报错；并通过模块顺序固定 HDMI KMS 为 `/dev/dri/card0`、Mali-450 为 `/dev/dri/card1`。
  - S905L4 内置百兆 PHY 实测 MDIO ID 为 `0x01803300`，在 `6.12.x-ophub` 下因 `meson-gxl` 使用 `PHY_ID_MATCH_EXACT(0x01803301)` 会回退到 `Generic PHY` 并跳过 `w152d_g12a_phy_config_init` 模拟校准导致负载断连；设备树 `ethernet-phy@8` 显式声明 `compatible = "ethernet-phy-id0180.3301", "ethernet-phy-ieee802.3-c22"` 后恢复匹配。
  - `install.sh` 自动写入 `/etc/unisoc_cp2log_config.txt` 将展锐 WCN CP2 日志限制为 `1 MiB` 内存盘循环写入（`/dev/shm`），消除启动时配置文件缺失报错与 `/etc/unisoc_cp2log_0.txt` 持续刷写闪存问题。

## 2026-11-27 本地镜像复测

从包含 PR #1 补丁的 Bookworm 镜像经 USB 启动，SSH 核对实机的三个 W152D 模块、eMMC 版 DTB 和 USB 引导脚本与镜像的 SHA-256 一致。DRM 原子状态为 1920×1080@60 Hz，fbcon 已绑定，tty1 文本缓冲区含登录提示，Lima 与百兆以太网均已初始化。测试显示器报告有信号、无画面。

本次启动中，BL33 读到 256 字节 EDID，记录选择 2160p60，随后执行了 CVBS 初始化。进入 Linux 后读取到 ENCI 为 0x13、ENCP 为 0x0、VPP 后混合宽度为 0x2d0（720）。驱动使用固件留下的 VENC 与 HDMI TX 时序，DRM 公布的 1080p 只反映其扫描缓冲区的模式。当前连接器检测也会返回 connected，实际时序与屏幕出图需分别确认。

本地 1080p 测试镜像仅在 USB 引导脚本中增加厂商命令 vout output 1080p60hz，使用 4:4:4、8 位，在 booti 前读取 ENCI、ENCP、VPP 和 VENC MUX，并将检测结果写入 /proc/cmdline 的 w152d.hdmi_handoff 参数。通过 SSH 将同一脚本直接装到现有 USB 盘。首次重启后 SSH 恢复，随后在一次读取范围过大的 VPU 采集中掉线。重新上电后使用者确认出图。SSH 核对当前启动仍来自原 USB 镜像，且命令行有 `w152d.hdmi_handoff=mismatch`。已将出图时使用的脚本保留在 USB 的 `/boot/aml_autoscript`，同时保留 `/boot/aml_autoscript.hdmi-original`。

### 出图后的 SSH 复核

- U-Boot 在进入 USB 脚本前配置 HDMI TX 为 2160p60。脚本成功将 TX 改为 1080p60、4:4:4、8 位。ENCI 为 0，ENCP 为 1，VPP 后混合宽度仍为 3840，VPP 输出寄存器为 3840×2160。因此脚本记录 `mismatch`，使用者仍确认有画面。Linux DRM 活跃模式为 1920×1080@60 Hz，EDID 两个数据块的校验均通过，2 秒内收到 119 次硬件 VSync 中断，fbcon 已绑定 tty1 且文本缓冲区含登录提示。
- Mali-450 的 Lima 渲染节点返回 2 个像素处理器，空闲 125 MHz，暴露的 OPP 上限为 800 MHz。这次只验证了内核接口和设备初始化，当前系统缺少 Mesa EGL/GLES，HDMI 音频也没有注册声卡。
- 有线协商为 100 Mbps 全双工。通过 SSH 各传输 32 MiB，盒子到电脑为 94.4 Mbit/s，电脑到盒子为 92.8 Mbit/s，测试期间无新增链路变化、丢包计数或收发错误。无线驱动扫描到 10 个接入点，当前通过有线联网。
- USB 以 5 Gb/s 连接，直接读取 USB 64 MiB 和 eMMC 4 MiB 均通过。根分区和 /boot 在 USB 上，eMMC 分区保持未挂载。根分区 ext4 错误和警告计数均为 0，systemd 为 running，失败单元及 dpkg 审计均为空。内核仍有展锐固件 TLV 和 CP2 日志文件提示，Wi-Fi 扫描正常。
- U-Boot 在执行 1080p 设置时打印 `Saving Environment to STORAGE... OK`，说明厂商显示命令保存了启动环境。原脚本备份可以恢复 USB 引导文件，启动环境的恢复需要另行核对。

### 4K EDID 交接测试

固定 1080p 的实测时序为 2200×1125（含消隐），而 VPP 输出窗口仍为 3840×2160，使用者报告电视画面变形。改用现有 USB 上的 EDID 交接脚本，去掉固定 1080p 的设置，沿用原厂 preboot 配置的 HDMI TX、VENC 和 VPP。原脚本与固定 1080p 脚本均已在 USB 的 FAT32 分区备份。

重启后，SSH 核对 U-Boot 日志选择 2160p60、4:2:0、10 位，VENC 时序为 4400×2250（含消隐），与 VPP 的 3840×2160 窗口对应。Linux 的扫描缓冲区仍为 1920×1080。使用者在此台 4K 电视上确认有画面且比例正常。此测试验证开机交接，后续仍需测试其他分辨率的显示器和运行中换屏。

### 随后一次冷启动复核

启动 ID 已更新，USB 仍加载同一份 EDID 交接脚本。HDMI TX 为 2160p60、4:2:0、10 位，ENCP 总时序 4400×2250，VPP 窗口 3840×2160，EDID 两块校验通过。2 秒内收到 119 次 VSync，tty1 登录提示和 Lima 渲染节点正常。

内核到 systemd 启动完成约 19.9 秒，失败单元和 dpkg 审计为空。USB 64 MiB 和 eMMC 4 MiB 直接读取通过，ext4 错误和警告计数为 0。有线百兆全双工，SSH 双向传输实测 93.9 / 91.5 Mbit/s，测试期间未增加收发错误、丢弃或链路切换计数。Wi-Fi 扫描到 10 个接入点，未关联。

本次启动记录了 ext4 日志回放及 journald 轮换旧日志，当前日志文件通过校验。展锐固件仍有 TLV 提示，CP2 日志初始化后在 /dev/shm 使用 1 MiB 的循环配置。U-Boot 在进入 USB 脚本前仍保存环境。Linux 当前没有注册音频声卡。

### v0.4.1 新镜像首启验收

刷写后的首个启动使用了候选镜像的 USB 引导脚本，生成了不同于旧系统的 SSH 主机密钥。SSH 登录通过，Armbian 自动初始化完成，USB 根分区扩容到 28.1 GiB。HDMI TX 为 2160p60、4:2:0、10 位，VPP 窗口为 3840×2160，EDID 校验通过，2 秒内收到 120 次 VSync。Lima 返回两个像素处理器。USB 和 eMMC 抽读通过，ext4 错误和警告计数为 0。首次交互登录设置待完成。

首启时 Debian 的 console-setup 在 systemd-tmpfiles 清理 /tmp 前创建了键盘临时文件，清理后再次打开时报文件不存在，systemd 状态为 degraded。SSH 上单独启动 console-setup 后成功，系统回到 running。第二份候选镜像让 console-setup 在启动期清理和模块加载完成后运行，待重新刷盘验收。

第二份候选镜像刷盘后，SSH 核对三个模块均与压缩镜像内的哈希相符，主机密钥已重新生成。systemd 为 running，失败单元列表为空。启动日志时间戳显示 systemd-tmpfiles-setup 完成约 30 毫秒后 console-setup 开始，执行结果为 success。HDMI TX 2160p60 和 VPP 3840×2160 一致，EDID 两块校验通过，2 秒内有 120 次 VSync。Lima 响应正常，USB 根分区扩容到 28.1 GiB，USB 与 eMMC 抽读均通过。SSH 双向传输 94.5 / 93.3 Mbit/s，未新增收发错误、丢弃或链路变化。Wi-Fi 扫描到 11 个接入点。当次 SSH 检查时，首次交互登录标记仍在。

完成首次登录并重新启动后，SSH 确认首启标记已清除，4K60、Lima、console-setup、百兆有线和 USB 根分区均正常。这份 6.12.118 镜像用于 v0.4.1 发布。

### 6.12.119 ophub 跨版本升级试验

在同一只 USB 测试盘安装 [ophub stable 6.12.119](https://github.com/ophub/kernel/releases/tag/kernel_stable)，用随包头文件重建 W152D 的三个 HDMI/GPU 模块。上游 DTB 提供板级 USB 与 eMMC 支持，试验沿用已经验证的 HDMI/GPU 节点和 PHY ID。新旧内核和模块并存。旧版 U-Boot 参数保存在 USB FAT32 根目录的 uEnv-w152d-6.12.118.txt，将其复制覆盖 uEnv.txt 可在下次启动切回 6.12.118。

6.12.119 的一次性试启动通过。已核对 2160p60、VPP 3840×2160、2 秒 120 次 VSync、Lima 识别两个像素处理器、console-setup 正常、USB 与 eMMC 读取正常。百兆有线双向实测 94.4 / 91.9 Mbit/s，无新增收发错误或丢弃。Wi-Fi 扫描到 12 个接入点，未测试关联和传输。试启动通过后将 6.12.119 设为该 USB 盘的默认项，并恢复原有 EDID 引导脚本。再次重启后 SSH 确认仍为 6.12.119，4K60、Lima、console-setup 和百兆有线正常。此试验独立于 6.12.118 的 v0.4.1 候选镜像。
