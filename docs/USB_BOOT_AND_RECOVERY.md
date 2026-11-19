# USB 优先启动与救援计划

目标行为：上电由原厂 U-Boot 检查指定 USB 启动文件，存在有效文件时进入 Armbian；没有盘或文件加载失败时保留原厂 Android 路径。内核接管后卡死不属于普通脚本返回，需要另设恢复机制。

## 已有证据

原厂环境备份包含以下逻辑（省略无关参数）：

```text
bootcmd=run storeboot
recovery_from_udisk=... usb start 0 ... run recovery_from_fat_dev ...
recovery_from_fat_dev=... fatload ... aml_autoscript ... autoscr ... recovery.img ... bootm ...
```

因此有 USB 恢复加载入口的环境记录，但默认启动不优先扫描 U 盘。尚未证明本机 U-Boot USB 读盘、booti 或自制镜像启动成功。其他晶晨盒子的激活脚本不能直接用于本机：装载地址、命令、镜像格式、设备树和 DDR 参数均可能不同。

## 计划涉及的内容

1. U 盘：准备启动分区和持久根文件系统；initramfs 加载所需控制器/存储驱动，按 UUID 找 rootfs。
2. U-Boot：验证 USB 枚举和文件加载、可用启动命令及内存布局。
3. 环境：一次性启动通过后，才考虑保存“USB 优先，原厂流程兜底”的 bootcmd。优先保留原厂 U-Boot 本体。
4. 如原厂 U-Boot 功能不足，再研究从 U 盘链式加载适配的第二阶段 U-Boot，不直接套用其他型号引导镜像。

## 引导区域与恢复准备

本机存在 bootloader、bootloader0、bootloader1、env 和 eMMC 硬件 boot0/boot1 访问节点；A/B boot/vendor_boot 不等于底层 bootloader 冗余恢复已经验证。

本地原厂备份复核结果：bootloader.img 为 4,194,304 字节，env.img 为 8,388,608 字节；两个完整硬件引导区备份各为 4,194,304 字节。bootloader0/1.img 各为 4,193,792 字节，等于硬件引导区去掉前 512 字节后的内容。所有六份备份均与配套 SHA256 一致，恢复时不能混用目标与偏移。

用户区采用晶晨 MPT 私有布局，已有备份记录并非标准 GPT；不能拿通用 GPT 分区工具直接重排。

| 故障层级 | 可能恢复入口 | 当前验证程度 |
|---|---|---|
| U 盘文件损坏 | 修改 U 盘；有正确兜底时拔盘回 Android | 目标行为，USB 直接启动未实测 |
| env 启动配置损坏 | 尚可进入的 Android、U-Boot 串口或 USB 恢复入口 | 原厂备份存在；修改后入口存活未验证 |
| bootloader 镜像损坏 | 芯片 BootROM USB 下载，加载匹配 DDR/引导程序后恢复 | 本机物理入口、USB 口、加载过程未实测 |

BootROM 位于芯片内，普通存储刷写不会改变它，但不代表本机线刷工具连接、DDR 初始化和救砖已被验证。现有本地线刷材料主要针对 super，不能当成已经实测的完整 bootloader+env 救援包。

下一轮应先确认底层 USB 下载识别与可用恢复材料，再做不保存环境的一次性 USB 启动；在此之前没有发布永久改 env 或覆盖 bootloader 的执行脚本。

参考：[U-Boot 晶晨启动流程](https://docs.u-boot.org/en/latest/board/amlogic/boot-flow.html)、[ophub 激活多启动脚本](https://github.com/ophub/amlogic-s9xxx-armbian/blob/main/build-armbian/armbian-files/platform-files/amlogic/bootfs/aml_autoscript.cmd)。
