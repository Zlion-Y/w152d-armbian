# W152D SoC 温度读取

`w152d_thermal` 面向中兴 W152D（GXLX4）。它启用 R1P1 传感器的 500 kHz 采样时钟，通过原厂 BL31 读取本机校准值，并在 Linux thermal 和 hwmon 中注册温度。适配范围为监控读数。

在 `6.12.119-ophub` 的 USB 启动系统上，以四核短时负载验证了温度从 30.7°C 上升到 38.7°C，停载两秒后回落到 32.3°C。卸载和重载通过。正常重启后，systemd 自动加载模块，thermal 和 hwmon 分别读取到 33.3°C 和 33.4°C。

转换公式参考 [Amlogic R1P1 驱动](https://github.com/khadas/common_drivers/blob/3a11a86a02e759fc57fc79410215f7c0c3a0d8e0/drivers/thermal/meson_tsensor.c)。

## 构建和安装

使用与目标系统对应的内核头文件和适用于构建主机的 Kbuild 工具。原生 arm64 构建可在本目录运行 `make KDIR=/path/to/kernel-headers`。构建主机若为 x86-64，需要供该主机运行的 `fixdep`、`modpost` 以及 ARM64 交叉编译器。

将构建出的模块复制到盒子上，确认 `modinfo -F vermagic ./w152d_thermal.ko` 的首字段等于 `uname -r`，再在盒子上安装。

```sh
sudo install -Dm644 w152d_thermal.ko "/lib/modules/$(uname -r)/extra/w152d_thermal.ko"
sudo depmod -a
sudo modprobe w152d_thermal
printf '%s\n' w152d_thermal | sudo tee /etc/modules-load.d/w152d-thermal.conf
```

按 thermal zone 类型找到温度，输出单位为毫摄氏度。

```sh
for zone in /sys/class/thermal/thermal_zone*; do
    [ "$(cat "$zone/type" 2>/dev/null)" = w152d-soc ] && cat "$zone/temp"
done
```

hwmon 中的设备名为 `w152d_soc`，温度属性是 `temp1_input`。
