# W152D CPU 动态调频和调压

模块通过原厂安全固件控制 GXLX4 的 CPU、DSU 时钟和 VDDCPU PWM，为四颗 Cortex-A55 注册一个 Linux `cpufreq` 策略。加载时核对板型、原厂 OPP 表索引 2、CPU 与 DSU 启动频率和 PWM 启动状态。

| 原厂 CPU 频点 | VDDCPU 标称电压 |
| --- | --- |
| 100、250、500、666.666、1000 MHz | 779 mV |
| 1200 MHz | 799 mV |
| 1404 MHz | 849 mV |
| 1500 MHz | 879 mV |
| 1608 MHz | 929 mV |
| 1704、1800、1920、2016 MHz | 979 mV |

升频前先抬高电压，降频后再降压。每个 PWM 步骤都核对硬件寄存器读回，时钟切换也核对固件读回。卸载时恢复 CPU 1704 MHz、DSU 1368 MHz 和启动 PWM。sysfs 的 `vddcpu_nominal_uv` 显示当前读回匹配的 OPP 标称电压。电压值来自原厂 PWM 表。

## 实机验证

在 USB 启动的 `6.12.119-ophub` 上逐档验证表 2 的 13 个 CPU 频点，以及 100 MHz 和 2016 MHz 的直接往返。重启后首次加载全频段模块，默认 `schedutil` 在 60 秒四核负载下升至 2016 MHz，温度采样最高 44.3°C。负载期间 USB 直读通过，停载后自动降档，空闲统计最低到 250 MHz。

2026 年 11 月 29 日在同一台 W152D 上完成 872 秒交替负载测试。六轮都完成单核与四核负载、USB 直读与数据 SHA-256 校验、停载回落。测试期间自动切换 1,258 次，24 次四核满载采样均为 2016 MHz 和标称 979 mV，最高温度采样为 47.6°C。监测期间未观察到调频失败、内核异常或 I/O 错误。

把镜像内的调频模块和开机加载配置临时装入现有 USB 系统，重启后两项板级驱动均自动加载，`schedutil` 枚举了 13 个频点，温度节点也正常返回读数。

在同一次启动中，先加载受限频段的调频驱动再加载全频段模块，内核可能沿用第一次注册策略时的调度频率基准。验收全频段时，重启后直接加载全频段模块。

## 构建和试用

使用目标内核对应的头文件和 Kbuild 工具，在本目录运行 `make KDIR=/path/to/kernel-headers`。交叉构建可追加 `ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-`，具体工具链用法见 [构建说明](../docs/BUILD.md)。

```sh
sudo insmod ./w152d_cpufreq.ko
grep -H . /sys/devices/system/cpu/cpufreq/policy0/{scaling_governor,scaling_available_frequencies,cpuinfo_cur_freq,vddcpu_nominal_uv}
sudo rmmod w152d_cpufreq
```

试验可通过 `min_khz`、`max_khz` 限制暴露给 Linux 的频点。由本仓库构建脚本打包的镜像会通过 `/etc/modules-load.d/w152d-cpufreq.conf` 在启动时加载模块。
