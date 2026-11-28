// SPDX-License-Identifier: GPL-2.0-only
/*
 * ZTE W152D (GXLX4) R1P1 SoC temperature readout.
 * Calibration constants and conversion follow the Amlogic R1P1 driver.
 */
#include <linux/arm-smccc.h>
#include <linux/bitfield.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/math64.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/thermal.h>

#define TS_CLK_DIV		GENMASK(7, 0)
#define TS_CLK_GATE		BIT(8)
#define TS_XTAL_HZ		24000000
#define TS_SAMPLE_HZ		500000

#define TS_CFG1			0x04
#define TS_CFG_ENABLE		(BIT(10) | BIT(9) | BIT(5) | BIT(3) | GENMASK(1, 0))
#define TS_CFG_RESET		(BIT(12) | BIT(11))
#define TS_STAT0		0x40
#define TS_CODE			GENMASK(15, 0)
#define TS_CODE_MIN		0x1500
#define TS_CODE_MAX		0x3500

#define SM_SHMEM_OUT_BASE	0x82000021
#define SM_TS_CALIB_READ	0x82000047
#define TS_SENSOR_ID		1
#define TS_TRIM_VALID		BIT(31)
#define TS_TRIM_SIGN		BIT(15)
#define TS_TRIM_MAG		GENMASK(14, 0)

struct w152d_thermal {
	void __iomem *sensor;
	void __iomem *clock;
	u32 saved_cfg;
	u32 saved_clock;
	s32 trim;
};

static struct platform_device *w152d_thermal_device;

static struct resource w152d_thermal_resources[] = {
	DEFINE_RES_MEM(0xfe020000, 0x50),
	DEFINE_RES_MEM(0xfe000158, 0x04),
};

static int w152d_thermal_read_trim(struct device *dev, s32 *trim)
{
	struct arm_smccc_res result;
	struct device_node *node;
	struct resource secmon;
	void __iomem *buffer;
	phys_addr_t address;
	u32 raw;
	int ret;

	/*
	 * This firmware returns calibration in its shared output buffer. The
	 * W152D DT used here leaves the generic Meson secure-monitor unbound,
	 * so there is no other Linux consumer of that buffer.
	 */
	node = of_find_compatible_node(NULL, NULL, "amlogic,meson-gxbb-sm");
	if (node) {
		bool enabled = of_device_is_available(node);

		of_node_put(node);
		if (enabled)
			return -EBUSY;
	}

	node = of_find_node_by_path("/reserved-memory/secmon@5000000");
	if (!node)
		return -ENODEV;
	ret = of_address_to_resource(node, 0, &secmon);
	of_node_put(node);
	if (ret)
		return ret;

	arm_smccc_smc(SM_SHMEM_OUT_BASE, 0, 0, 0, 0, 0, 0, 0, &result);
	address = result.a0;
	if (!IS_ALIGNED(address, sizeof(raw)) || address < secmon.start ||
	    address > secmon.end - (sizeof(raw) - 1)) {
		dev_err(dev, "unexpected firmware output address %pa\n", &address);
		return -EIO;
	}
	buffer = ioremap_cache(address, sizeof(raw));
	if (!buffer)
		return -ENOMEM;

	arm_smccc_smc(SM_TS_CALIB_READ, TS_SENSOR_ID, 0, 0, 0, 0, 0, 0, &result);
	raw = result.a0 ? 0 : readl(buffer);
	iounmap(buffer);
	if (!(raw & TS_TRIM_VALID)) {
		dev_err(dev, "firmware did not return valid sensor calibration (status %#lx)\n",
			result.a0);
		return -ENODATA;
	}
	*trim = FIELD_GET(TS_TRIM_MAG, raw);
	if (raw & TS_TRIM_SIGN)
		*trim = -*trim;

	return 0;
}

static bool w152d_thermal_code_valid(u32 status)
{
	u32 code = FIELD_GET(TS_CODE, status);

	return code >= TS_CODE_MIN && code <= TS_CODE_MAX;
}

static int w152d_thermal_get_temp(struct thermal_zone_device *zone, int *temp)
{
	struct w152d_thermal *sensor = thermal_zone_device_priv(zone);
	u32 code = FIELD_GET(TS_CODE, readl(sensor->sensor + TS_STAT0));
	s64 scaled;
	int denominator;

	if (!w152d_thermal_code_valid(code))
		return -EAGAIN;

	/* The factory DT specifies coefficients 324, 424, 3159, 9411. */
	denominator = 65536 + (324 * code) / 100;
	scaled = div_s64((s64)((424 * code) / 100) * 65536, denominator);
	*temp = (div_s64((scaled + sensor->trim) * 9411, 65536) - 3159) * 100;
	return 0;
}

static const struct thermal_zone_device_ops w152d_thermal_ops = {
	.get_temp = w152d_thermal_get_temp,
};

static void w152d_thermal_restore(void *data)
{
	struct w152d_thermal *sensor = data;
	u32 clock_mask = TS_CLK_DIV | TS_CLK_GATE;
	u32 cfg_mask = TS_CFG_ENABLE | TS_CFG_RESET;
	u32 config = readl(sensor->sensor + TS_CFG1);
	u32 clock = readl(sensor->clock);

	writel((config & ~cfg_mask) | (sensor->saved_cfg & cfg_mask),
	       sensor->sensor + TS_CFG1);
	writel((clock & ~clock_mask) | (sensor->saved_clock & clock_mask),
	       sensor->clock);
}

static void w152d_thermal_unregister_zone(void *data)
{
	thermal_zone_device_unregister(data);
}

static int w152d_thermal_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct thermal_zone_device *zone;
	struct w152d_thermal *sensor;
	u32 clock, status;
	int ret;

	sensor = devm_kzalloc(dev, sizeof(*sensor), GFP_KERNEL);
	if (!sensor)
		return -ENOMEM;
	sensor->sensor = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(sensor->sensor))
		return PTR_ERR(sensor->sensor);
	sensor->clock = devm_platform_ioremap_resource(pdev, 1);
	if (IS_ERR(sensor->clock))
		return PTR_ERR(sensor->clock);

	ret = w152d_thermal_read_trim(dev, &sensor->trim);
	if (ret)
		return ret;

	sensor->saved_clock = readl(sensor->clock);
	clock = (sensor->saved_clock & ~(TS_CLK_DIV | TS_CLK_GATE)) |
		FIELD_PREP(TS_CLK_DIV, TS_XTAL_HZ / TS_SAMPLE_HZ - 1);
	writel(clock, sensor->clock);
	writel(clock | TS_CLK_GATE, sensor->clock);
	sensor->saved_cfg = readl(sensor->sensor + TS_CFG1);
	ret = devm_add_action_or_reset(dev, w152d_thermal_restore, sensor);
	if (ret)
		return ret;

	writel((sensor->saved_cfg & ~TS_CFG_RESET) | TS_CFG_ENABLE,
	       sensor->sensor + TS_CFG1);
	ret = readl_poll_timeout(sensor->sensor + TS_STAT0, status,
				 w152d_thermal_code_valid(status), 1000, 250000);
	if (ret)
		return dev_err_probe(dev, ret, "no valid temperature ADC sample (%#x)\n",
				     status);

	/* Monitor only. No trips or cooling devices are installed by this driver. */
	zone = thermal_zone_device_register_with_trips("w152d-soc", NULL, 0,
			sensor, &w152d_thermal_ops, NULL, 0, 0);
	if (IS_ERR(zone))
		return PTR_ERR(zone);
	ret = devm_add_action_or_reset(dev, w152d_thermal_unregister_zone, zone);
	if (ret)
		return ret;

	return thermal_zone_device_enable(zone);
}

static struct platform_driver w152d_thermal_driver = {
	.driver.name = "w152d-thermal",
};

static int __init w152d_thermal_init(void)
{
	if (!of_machine_is_compatible("amlogic,gxlx4-s905l4-w150d"))
		return -ENODEV;

	w152d_thermal_device = platform_create_bundle(&w152d_thermal_driver,
			w152d_thermal_probe, w152d_thermal_resources,
			ARRAY_SIZE(w152d_thermal_resources), NULL, 0);
	return PTR_ERR_OR_ZERO(w152d_thermal_device);
}

static void __exit w152d_thermal_exit(void)
{
	platform_device_unregister(w152d_thermal_device);
	platform_driver_unregister(&w152d_thermal_driver);
}

module_init(w152d_thermal_init);
module_exit(w152d_thermal_exit);

MODULE_DESCRIPTION("ZTE W152D calibrated SoC temperature sensor");
MODULE_LICENSE("GPL");
