// SPDX-License-Identifier: GPL-2.0-only
/* W152D CPU and DSU DVFS through the factory GXLX4 secure firmware. */
#include <linux/arm-smccc.h>
#include <linux/cpufreq.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/module.h>
#include <linux/of.h>

#define GX_SECURE_CLK		0x82000098
#define GX_PDVFS_TABLE		0x82000088
#define GX_SECURE_PWM		0x820000c0
#define GX_SET_RATE		3
#define GX_GET_RATE		4
#define GX_CPU_CLK		16
#define GX_DSU_CLK		17
#define GX_TESTED_TABLE		2

#define VDDCPU_PWM_BASE		0xfe058200
#define VDDCPU_PWM_SIZE		0x0c
#define VDDCPU_PWM_MISC		0x08
#define VDDCPU_PWM_MODE		0x01
#define VDDCPU_PWM_TEE_ID	1
#define VDDCPU_PWM_SET_ENABLED	0
#define VDDCPU_PWM_TICKS		36
#define VDDCPU_PWM_MAX_STEP	2
#define VDDCPU_BOOT_TICKS	4

struct w152d_opp {
	unsigned int cpu_khz;
	unsigned int dsu_khz;
	unsigned int microvolts;
	unsigned int duty_percent;
};

/* Factory table 2, with duty percentages from the board's VDDCPU table. */
static const struct w152d_opp w152d_opps[] = {
	{  100000,  100000, 779000, 75 },
	{  250000,  250000, 779000, 75 },
	{  500000,  500000, 779000, 75 },
	{  666666,  666666, 779000, 75 },
	{ 1000000, 1000000, 779000, 75 },
	{ 1200000, 1000000, 799000, 69 },
	{ 1404000, 1128000, 849000, 56 },
	{ 1500000, 1200000, 879000, 47 },
	{ 1608000, 1296000, 929000, 33 },
	{ 1704000, 1368000, 979000, 19 },
	{ 1800000, 1368000, 979000, 19 },
	{ 1920000, 1368000, 979000, 19 },
	{ 2016000, 1368000, 979000, 19 },
};

/* BL33 leaves the clock at 1704 MHz and the PWM at the 1009 mV setting. */
static const struct w152d_opp w152d_boot = { 1704000, 1368000, 1009000, 11 };
static struct cpufreq_frequency_table w152d_freq_table[ARRAY_SIZE(w152d_opps) + 1];
static void __iomem *w152d_pwm;

static unsigned int min_khz = 100000;
module_param(min_khz, uint, 0400);
MODULE_PARM_DESC(min_khz, "Minimum frequency exposed to cpufreq");

static unsigned int max_khz = 2016000;
module_param(max_khz, uint, 0400);
MODULE_PARM_DESC(max_khz, "Maximum frequency exposed to cpufreq");

static unsigned long w152d_clock_call(unsigned int command, unsigned int clock,
				     unsigned long rate_hz)
{
	struct arm_smccc_res result;

	arm_smccc_smc(GX_SECURE_CLK, command, clock, rate_hz, 0, 0, 0, 0, &result);
	return result.a0;
}

static unsigned int w152d_clock_get(unsigned int clock)
{
	unsigned long rate_hz = w152d_clock_call(GX_GET_RATE, clock, 0);

	if (rate_hz < 100000000 || rate_hz > 2016000999)
		return 0;
	return rate_hz / 1000;
}

static int w152d_clock_set(unsigned int clock, unsigned int rate_khz)
{
	s32 status = w152d_clock_call(GX_SET_RATE, clock, rate_khz * 1000UL);
	unsigned int actual = w152d_clock_get(clock);

	if (!status && actual == rate_khz)
		return 0;

	pr_err("w152d-cpufreq: clock %u request %u kHz returned %d, readback %u kHz\n",
	       clock, rate_khz, status, actual);
	return -EIO;
}

static unsigned int w152d_pwm_count(unsigned int high_ticks)
{
	return ((high_ticks - 1) << 16) | (VDDCPU_PWM_TICKS - high_ticks - 1);
}

static unsigned int w152d_opp_ticks(const struct w152d_opp *opp)
{
	return DIV_ROUND_CLOSEST(opp->duty_percent * VDDCPU_PWM_TICKS, 100);
}

static int w152d_pwm_read_ticks(void)
{
	u32 count = readl(w152d_pwm);
	unsigned int high = (count >> 16) + 1;

	if (readl(w152d_pwm + VDDCPU_PWM_MISC) != VDDCPU_PWM_MODE ||
	    high < VDDCPU_BOOT_TICKS || high > w152d_opp_ticks(&w152d_opps[0]) ||
	    count != w152d_pwm_count(high))
		return -EIO;
	return high;
}

static int w152d_pwm_ramp(int from, int to)
{
	struct arm_smccc_res result;
	u32 count;

	/* Increasing duty lowers VDDCPU. Keep the boot period and PWM mode. */
	while (from != to) {
		from += clamp(to - from, -VDDCPU_PWM_MAX_STEP, VDDCPU_PWM_MAX_STEP);
		count = w152d_pwm_count(from);
		arm_smccc_smc(GX_SECURE_PWM, 0, VDDCPU_PWM_TEE_ID, VDDCPU_PWM_SET_ENABLED,
			      count, 0, 0, 0, &result);
		udelay(40);
		if (result.a0 || w152d_pwm_read_ticks() != from) {
			pr_err("w152d-cpufreq: PWM request %#x returned %#lx, readback %#x\n",
			       count, result.a0, readl(w152d_pwm));
			return -EIO;
		}
	}
	return 0;
}

static int w152d_apply(const struct w152d_opp *target)
{
	unsigned int cpu = w152d_clock_get(GX_CPU_CLK);
	unsigned int dsu = w152d_clock_get(GX_DSU_CLK);
	int duty = w152d_pwm_read_ticks();
	int wanted_duty = w152d_opp_ticks(target);
	int ret;

	if (!cpu || !dsu || duty < 0)
		return -EIO;

	/* Raise voltage and DSU before raising CPU. Lower them after CPU. */
	if (wanted_duty < duty) {
		ret = w152d_pwm_ramp(duty, wanted_duty);
		if (ret)
			return ret;
		duty = wanted_duty;
	}
	if (dsu < target->dsu_khz) {
		ret = w152d_clock_set(GX_DSU_CLK, target->dsu_khz);
		if (ret)
			return ret;
	}
	if (cpu != target->cpu_khz) {
		ret = w152d_clock_set(GX_CPU_CLK, target->cpu_khz);
		if (ret)
			return ret;
	}
	if (dsu > target->dsu_khz) {
		ret = w152d_clock_set(GX_DSU_CLK, target->dsu_khz);
		if (ret)
			return ret;
	}
	return w152d_pwm_ramp(duty, wanted_duty);
}

static const struct w152d_opp *w152d_read_opp(void)
{
	unsigned int cpu = w152d_clock_get(GX_CPU_CLK);
	unsigned int dsu = w152d_clock_get(GX_DSU_CLK);
	int duty = w152d_pwm_read_ticks();
	unsigned int i;

	if (duty < 0)
		return NULL;
	if (cpu == w152d_boot.cpu_khz && dsu == w152d_boot.dsu_khz &&
	    duty == VDDCPU_BOOT_TICKS)
		return &w152d_boot;
	for (i = 0; i < ARRAY_SIZE(w152d_opps); i++) {
		if (cpu == w152d_opps[i].cpu_khz && dsu == w152d_opps[i].dsu_khz &&
		    duty == w152d_opp_ticks(&w152d_opps[i]))
			return &w152d_opps[i];
	}
	return NULL;
}

static int w152d_target_index(struct cpufreq_policy *policy, unsigned int index)
{
	const struct w152d_opp *before = w152d_read_opp();
	unsigned int target = policy->freq_table[index].driver_data;
	int ret;

	if (!before)
		return -EIO;
	ret = w152d_apply(&w152d_opps[target]);
	if (ret && w152d_apply(before) && w152d_apply(&w152d_boot))
		pr_err("w152d-cpufreq: failed to restore CPU, DSU and VDDCPU\n");
	return ret;
}

static unsigned int w152d_get(unsigned int cpu)
{
	return w152d_clock_get(GX_CPU_CLK);
}

static ssize_t show_vddcpu_nominal_uv(struct cpufreq_policy *policy, char *buf)
{
	const struct w152d_opp *opp = w152d_read_opp();

	if (!opp)
		return -EAGAIN;
	return sysfs_emit(buf, "%u\n", opp->microvolts);
}

cpufreq_freq_attr_ro(vddcpu_nominal_uv);

static struct freq_attr *w152d_cpufreq_attrs[] = {
	&cpufreq_freq_attr_scaling_available_freqs,
	&vddcpu_nominal_uv,
	NULL,
};

static int w152d_policy_init(struct cpufreq_policy *policy)
{
	cpumask_setall(policy->cpus);
	policy->freq_table = w152d_freq_table;
	policy->cpuinfo.transition_latency = 3 * NSEC_PER_MSEC;
	policy->dvfs_possible_from_any_cpu = true;
	return 0;
}

static struct cpufreq_driver w152d_cpufreq_driver = {
	.name = "w152d-gxlx4",
	.flags = CPUFREQ_CONST_LOOPS,
	.verify = cpufreq_generic_frequency_table_verify,
	.target_index = w152d_target_index,
	.get = w152d_get,
	.init = w152d_policy_init,
	.attr = w152d_cpufreq_attrs,
};

static int __init w152d_cpufreq_init(void)
{
	struct arm_smccc_res result;
	unsigned int i, count = 0;
	int ret;

	if (!of_machine_is_compatible("amlogic,gxlx4-s905l4-w150d"))
		return -ENODEV;
	arm_smccc_smc(GX_PDVFS_TABLE, 0, 0, 0, 0, 0, 0, 0, &result);
	if (result.a0 != GX_TESTED_TABLE)
		return -ENODEV;

	for (i = 0; i < ARRAY_SIZE(w152d_opps); i++) {
		if (w152d_opps[i].cpu_khz < min_khz || w152d_opps[i].cpu_khz > max_khz)
			continue;
		w152d_freq_table[count].frequency = w152d_opps[i].cpu_khz;
		w152d_freq_table[count++].driver_data = i;
	}
	if (!count)
		return -EINVAL;
	w152d_freq_table[count].frequency = CPUFREQ_TABLE_END;

	if (!request_mem_region(VDDCPU_PWM_BASE, VDDCPU_PWM_SIZE, "w152d-vddcpu"))
		return -EBUSY;
	w152d_pwm = ioremap(VDDCPU_PWM_BASE, VDDCPU_PWM_SIZE);
	if (!w152d_pwm) {
		ret = -ENOMEM;
		goto release_pwm;
	}
	if (w152d_read_opp() != &w152d_boot) {
		pr_err("w152d-cpufreq: untested boot state: CPU %u kHz DSU %u kHz PWM %#x\n",
		       w152d_clock_get(GX_CPU_CLK), w152d_clock_get(GX_DSU_CLK), readl(w152d_pwm));
		ret = -ENODEV;
		goto unmap_pwm;
	}
	ret = cpufreq_register_driver(&w152d_cpufreq_driver);
	if (!ret)
		return 0;
	if (w152d_apply(&w152d_boot))
		pr_err("w152d-cpufreq: failed to restore boot state after registration error\n");

unmap_pwm:
	iounmap(w152d_pwm);
release_pwm:
	release_mem_region(VDDCPU_PWM_BASE, VDDCPU_PWM_SIZE);
	return ret;
}

static void __exit w152d_cpufreq_exit(void)
{
	cpufreq_unregister_driver(&w152d_cpufreq_driver);
	if (w152d_apply(&w152d_boot))
		pr_err("w152d-cpufreq: failed to restore boot state on unload\n");
	iounmap(w152d_pwm);
	release_mem_region(VDDCPU_PWM_BASE, VDDCPU_PWM_SIZE);
}

module_init(w152d_cpufreq_init);
module_exit(w152d_cpufreq_exit);

MODULE_DESCRIPTION("W152D GXLX4 CPU frequency and VDDCPU scaling");
MODULE_LICENSE("GPL");
