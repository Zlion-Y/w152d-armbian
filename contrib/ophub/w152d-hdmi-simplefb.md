# W152D HDMI（simple-framebuffer）

## 结论

GXLX4 的 VPU/HDMI 尚未在 6.12 主线内核走通原生 `meson-drm`。本机实测可行的方式是沿用原厂 U-Boot 的 HDMI/OSD 初始化，再由 Linux `simple-framebuffer` 接管，得到固定的 1920x1080p60 文字控制台。HDMI 音频、热插拔与运行中切分辨率不在范围内。

内核 6.12.118 已启用 `CONFIG_FB_SIMPLE`、`CONFIG_FRAMEBUFFER_CONSOLE` 和 `CONFIG_VT`，因此只需补设备树与启动脚本。

## 需要改动的三处

### 1. 设备树 `/chosen` 增加 simple-framebuffer 节点

`meson-gxlx4-w152d.dts`（USB 板型）已在 `contrib/ophub/kernel-board.patch` 中修改；eMMC 板型 `meson-gxlx4-w152d-emmc.dts` 位于上游 ophub 设备树 PR，需要同样增加：

```dts
chosen {
    #address-cells = <2>;
    #size-cells = <2>;
    ranges;
    stdout-path = "serial0:921600n8";

    framebuffer@7f000000 {
        compatible = "simple-framebuffer";
        reg = <0x0 0x7f000000 0x0 0x5eec00>;
        width = <1920>;
        height = <1080>;
        stride = <5760>;
        format = "r8g8b8";
        status = "okay";
    };
};
```

`reserved-memory` 中已有的 `firmware-framebuffer@7f000000`（8 MiB，`no-map`）保持不变。

### 2. 启动脚本在 `booti` 前初始化 vendor U-Boot 显示

USB 启动脚本 `aml_autoscript.cmd` 已在 `contrib/ophub/armbian-board.patch` 中修改；eMMC 启动脚本（安装时生成的 `boot.cmd`/`boot.scr`）需要同样在 `fdt resize` 之后、`booti` 之前插入：

```text
setenv outputmode 1080p60hz
setenv hdmimode 1080p60hz
vout output 1080p60hz
hdmitx blank 0
osd open
osd clear
osd enable
```

### 3. `uEnv.txt` 的 `APPEND` 增加 `console=tty0`

保留串口控制台，追加虚拟终端：

```text
APPEND=root=... console=ttyAML0,921600n8 console=tty0 net.ifnames=0
```

`getty@tty1` 已在 Armbian 镜像中启用，`console=tty0` 到位后 HDMI 上会出现登录提示。

## 实机验证

- 盒子：中兴 W152D（GXLX4/S905L4），Dell P2219H。
- 镜像：`Armbian_26.11.0_amlogic_w152d_bookworm_6.12.118_server_2026.11.23`。
- 结果：`/dev/fb0` 出现，`simple-framebuffer` 注册 1920x1080x24，`/proc/consoles` 含 `tty0`，HDMI 正常显示文字控制台。
- 当前只做热重启验证，建议再补一次断电冷启动验证。
