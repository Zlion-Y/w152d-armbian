// SPDX-License-Identifier: GPL-2.0
/*
 * Amlogic S905L4 (Meson GXLX4) Mali-450 GPU Clock Provider for ZTE W152D
 *
 * Hardware register layout verified from GXLX4 silicon & vendor clk-gxlx4:
 *   - CLKCTRL_SYS_CLK_EN0_REG1 (0xfe000044): BIT(6) = sys_mali APB/AXI bus gate
 *   - CLKCTRL_SYS_CLK_EN0_REG3 (0xfe00004c): BIT(25) = sys_vpu_intr gate
 *   - CLKCTRL_MALI_CLK_CTRL    (0xfe00015c): dual-branch glitch-free mux
 *       Branch 0 (mali_0): div[6:0], gate BIT(8), sel[11:9]
 *       Branch 1 (mali_1): div[22:16], gate BIT(24), sel[27:25]
 *       Final glitch-free mux (mali): BIT(31) (0 = mali_0, 1 = mali_1)
 *       Parent mux table:
 *         0: xtal        (24 MHz)
 *         1: gp1_pll     (852 MHz)
 *         2: hifi_pll
 *         3: fclk_div2p5 (800 MHz)
 *         4: fclk_div3   (666.666 MHz)
 *         5: fclk_div4   (500 MHz)
 *         6: fclk_div5   (400 MHz)
 *         7: fclk_div7   (285.714 MHz)
 */

#include <linux/clk-provider.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

#define SYS_MALI_EN_BIT		BIT(6)
#define SYS_VPU_INTR_EN_BIT	BIT(25)

#define MALI_B0_DIV_SHIFT	0
#define MALI_B0_DIV_MASK	GENMASK(6, 0)
#define MALI_B0_GATE		BIT(8)
#define MALI_B0_SEL_SHIFT	9
#define MALI_B0_SEL_MASK	GENMASK(11, 9)
#define MALI_B0_MASK		GENMASK(11, 0)

#define MALI_B1_DIV_SHIFT	16
#define MALI_B1_DIV_MASK	GENMASK(22, 16)
#define MALI_B1_GATE		BIT(24)
#define MALI_B1_SEL_SHIFT	25
#define MALI_B1_SEL_MASK	GENMASK(27, 25)
#define MALI_B1_MASK		GENMASK(27, 16)

#define MALI_FINAL_MUX_BIT	BIT(31)

#define W152D_MALI_CLK_BUS	0
#define W152D_MALI_CLK_CORE	1
#define W152D_MALI_CLK_NUM	2

struct w152d_mali_opp {
	unsigned long rate;
	u8 sel;
	u8 div;
};

static const struct w152d_mali_opp w152d_mali_opps[] = {
	{ 125000000UL, 5, 3 }, /* fclk_div4 / 4 */
	{ 250000000UL, 5, 1 }, /* fclk_div4 / 2 */
	{ 285714285UL, 7, 0 }, /* fclk_div7 / 1 */
	{ 400000000UL, 6, 0 }, /* fclk_div5 / 1 */
	{ 500000000UL, 5, 0 }, /* fclk_div4 / 1 (default) */
	{ 666666666UL, 4, 0 }, /* fclk_div3 / 1 */
	{ 800000000UL, 3, 0 }, /* fclk_div2p5 / 1 */
};

static const unsigned long w152d_parent_rates[8] = {
	24000000UL,   /* 0: xtal */
	852000000UL,  /* 1: gp1_pll */
	491520000UL,  /* 2: hifi_pll */
	800000000UL,  /* 3: fclk_div2p5 */
	666666666UL,  /* 4: fclk_div3 */
	500000000UL,  /* 5: fclk_div4 */
	400000000UL,  /* 6: fclk_div5 */
	285714285UL,  /* 7: fclk_div7 */
};

struct w152d_gpu_clk_priv {
	void __iomem *mali_ctrl;
	void __iomem *sys_en1;
	void __iomem *sys_en3;
	spinlock_t lock;
	struct clk_hw bus_hw;
	struct clk_hw core_hw;
};

#define to_priv_from_bus(_hw)  container_of(_hw, struct w152d_gpu_clk_priv, bus_hw)
#define to_priv_from_core(_hw) container_of(_hw, struct w152d_gpu_clk_priv, core_hw)

static int w152d_mali_bus_enable(struct clk_hw *hw)
{
	struct w152d_gpu_clk_priv *priv = to_priv_from_bus(hw);
	unsigned long flags;
	u32 val;

	spin_lock_irqsave(&priv->lock, flags);
	val = readl(priv->sys_en1);
	writel(val | SYS_MALI_EN_BIT, priv->sys_en1);
	readl(priv->sys_en1);
	spin_unlock_irqrestore(&priv->lock, flags);
	return 0;
}

static void w152d_mali_bus_disable(struct clk_hw *hw)
{
	/* Keep APB/AXI slave interface accessible across runtime PM transitions */
}

static int w152d_mali_bus_is_enabled(struct clk_hw *hw)
{
	struct w152d_gpu_clk_priv *priv = to_priv_from_bus(hw);

	return !!(readl(priv->sys_en1) & SYS_MALI_EN_BIT);
}

static unsigned long w152d_mali_bus_recalc_rate(struct clk_hw *hw,
						unsigned long parent_rate)
{
	return 166666666UL;
}

static const struct clk_ops w152d_mali_bus_ops = {
	.enable = w152d_mali_bus_enable,
	.disable = w152d_mali_bus_disable,
	.is_enabled = w152d_mali_bus_is_enabled,
	.recalc_rate = w152d_mali_bus_recalc_rate,
};

static int w152d_mali_core_enable(struct clk_hw *hw)
{
	struct w152d_gpu_clk_priv *priv = to_priv_from_core(hw);
	unsigned long flags;
	u32 val;

	spin_lock_irqsave(&priv->lock, flags);
	val = readl(priv->mali_ctrl);
	if (val & MALI_FINAL_MUX_BIT) {
		if (!(val & MALI_B1_MASK))
			val |= (5U << MALI_B1_SEL_SHIFT);
		val |= MALI_B1_GATE;
	} else {
		if (!(val & MALI_B0_MASK))
			val |= (5U << MALI_B0_SEL_SHIFT);
		val |= MALI_B0_GATE;
	}
	writel(val, priv->mali_ctrl);
	readl(priv->mali_ctrl);
	spin_unlock_irqrestore(&priv->lock, flags);
	udelay(5);
	return 0;
}

static void w152d_mali_core_disable(struct clk_hw *hw)
{
	/* Keep minimum glitch-free clock active so Mali PMU IRQ/regs never bus-fault */
}

static int w152d_mali_core_is_enabled(struct clk_hw *hw)
{
	struct w152d_gpu_clk_priv *priv = to_priv_from_core(hw);
	u32 val = readl(priv->mali_ctrl);

	if (val & MALI_FINAL_MUX_BIT)
		return !!(val & MALI_B1_GATE);
	return !!(val & MALI_B0_GATE);
}

static unsigned long w152d_mali_core_recalc_rate(struct clk_hw *hw,
						 unsigned long parent_rate)
{
	struct w152d_gpu_clk_priv *priv = to_priv_from_core(hw);
	u32 val = readl(priv->mali_ctrl);
	u32 sel, div;

	if (val & MALI_FINAL_MUX_BIT) {
		sel = (val & MALI_B1_SEL_MASK) >> MALI_B1_SEL_SHIFT;
		div = (val & MALI_B1_DIV_MASK) >> MALI_B1_DIV_SHIFT;
	} else {
		sel = (val & MALI_B0_SEL_MASK) >> MALI_B0_SEL_SHIFT;
		div = (val & MALI_B0_DIV_MASK) >> MALI_B0_DIV_SHIFT;
	}

	return w152d_parent_rates[sel & 7] / (div + 1);
}

static const struct w152d_mali_opp *w152d_match_opp(unsigned long target)
{
	const struct w152d_mali_opp *best = &w152d_mali_opps[0];
	unsigned long best_diff = ULONG_MAX;
	size_t i;

	for (i = 0; i < ARRAY_SIZE(w152d_mali_opps); i++) {
		unsigned long r = w152d_mali_opps[i].rate;
		unsigned long diff = (r > target) ? (r - target) : (target - r);

		if (diff < best_diff) {
			best_diff = diff;
			best = &w152d_mali_opps[i];
		}
	}
	return best;
}

static int w152d_mali_core_determine_rate(struct clk_hw *hw,
					  struct clk_rate_request *req)
{
	const struct w152d_mali_opp *opp = w152d_match_opp(req->rate);

	req->rate = opp->rate;
	return 0;
}

static int w152d_mali_core_set_rate(struct clk_hw *hw, unsigned long rate,
				    unsigned long parent_rate)
{
	struct w152d_gpu_clk_priv *priv = to_priv_from_core(hw);
	const struct w152d_mali_opp *opp = w152d_match_opp(rate);
	unsigned long flags;
	u32 val;

	spin_lock_irqsave(&priv->lock, flags);
	val = readl(priv->mali_ctrl);

	if (!(val & MALI_FINAL_MUX_BIT)) {
		/* Currently on branch 0 -> stage new rate on branch 1, then flip BIT(31) */
		val &= ~MALI_B1_MASK;
		val |= ((u32)opp->sel << MALI_B1_SEL_SHIFT) |
		       ((u32)opp->div << MALI_B1_DIV_SHIFT) |
		       MALI_B1_GATE;
		writel(val, priv->mali_ctrl);
		readl(priv->mali_ctrl);
		udelay(5);

		val |= MALI_FINAL_MUX_BIT;
		writel(val, priv->mali_ctrl);
		readl(priv->mali_ctrl);
		udelay(2);

		val &= ~MALI_B0_GATE;
		writel(val, priv->mali_ctrl);
	} else {
		/* Currently on branch 1 -> stage new rate on branch 0, then clear BIT(31) */
		val &= ~MALI_B0_MASK;
		val |= ((u32)opp->sel << MALI_B0_SEL_SHIFT) |
		       ((u32)opp->div << MALI_B0_DIV_SHIFT) |
		       MALI_B0_GATE;
		writel(val, priv->mali_ctrl);
		readl(priv->mali_ctrl);
		udelay(5);

		val &= ~MALI_FINAL_MUX_BIT;
		writel(val, priv->mali_ctrl);
		readl(priv->mali_ctrl);
		udelay(2);

		val &= ~MALI_B1_GATE;
		writel(val, priv->mali_ctrl);
	}

	readl(priv->mali_ctrl);
	spin_unlock_irqrestore(&priv->lock, flags);
	return 0;
}

static const struct clk_ops w152d_mali_core_ops = {
	.enable = w152d_mali_core_enable,
	.disable = w152d_mali_core_disable,
	.is_enabled = w152d_mali_core_is_enabled,
	.recalc_rate = w152d_mali_core_recalc_rate,
	.determine_rate = w152d_mali_core_determine_rate,
	.set_rate = w152d_mali_core_set_rate,
};

static int w152d_gpu_clk_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct w152d_gpu_clk_priv *priv;
	struct clk_hw_onecell_data *onecell;
	struct resource *res;
	struct clk_init_data bus_init = {};
	struct clk_init_data core_init = {};
	u32 val;
	int ret;

	priv = devm_kzalloc(dev, sizeof(*priv), GFP_KERNEL);
	if (!priv)
		return -ENOMEM;

	onecell = devm_kzalloc(dev, struct_size(onecell, hws, W152D_MALI_CLK_NUM),
			       GFP_KERNEL);
	if (!onecell)
		return -ENOMEM;

	spin_lock_init(&priv->lock);

	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!res)
		return -EINVAL;
	priv->mali_ctrl = devm_ioremap(dev, res->start, resource_size(res));
	if (!priv->mali_ctrl)
		return -ENOMEM;

	res = platform_get_resource(pdev, IORESOURCE_MEM, 1);
	if (!res)
		return -EINVAL;
	priv->sys_en1 = devm_ioremap(dev, res->start, resource_size(res));
	if (!priv->sys_en1)
		return -ENOMEM;

	res = platform_get_resource(pdev, IORESOURCE_MEM, 2);
	if (res)
		priv->sys_en3 = devm_ioremap(dev, res->start, resource_size(res));

	/* Enable sys_mali bus gate & VPU interrupt gate, pre-init Mali core at 500 MHz */
	val = readl(priv->sys_en1);
	writel(val | SYS_MALI_EN_BIT, priv->sys_en1);
	if (priv->sys_en3) {
		val = readl(priv->sys_en3);
		writel(val | SYS_VPU_INTR_EN_BIT, priv->sys_en3);
	}
	writel((5U << MALI_B0_SEL_SHIFT) | MALI_B0_GATE, priv->mali_ctrl);
	readl(priv->mali_ctrl);
	udelay(10);

	bus_init.name = "w152d_mali_bus";
	bus_init.ops = &w152d_mali_bus_ops;
	bus_init.num_parents = 0;
	priv->bus_hw.init = &bus_init;

	core_init.name = "w152d_mali_core";
	core_init.ops = &w152d_mali_core_ops;
	core_init.flags = CLK_GET_RATE_NOCACHE;
	core_init.num_parents = 0;
	priv->core_hw.init = &core_init;

	ret = devm_clk_hw_register(dev, &priv->bus_hw);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register mali bus clk\n");

	ret = devm_clk_hw_register(dev, &priv->core_hw);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register mali core clk\n");

	onecell->num = W152D_MALI_CLK_NUM;
	onecell->hws[W152D_MALI_CLK_BUS] = &priv->bus_hw;
	onecell->hws[W152D_MALI_CLK_CORE] = &priv->core_hw;

	ret = devm_of_clk_add_hw_provider(dev, of_clk_hw_onecell_get, onecell);
	if (ret)
		return dev_err_probe(dev, ret, "failed to add mali clk provider\n");

	dev_info(dev, "S905L4 Mali-450 clocks active (core=%lu Hz, ctrl=0x%08x)\n",
		 w152d_mali_core_recalc_rate(&priv->core_hw, 0),
		 readl(priv->mali_ctrl));
	return 0;
}

static const struct of_device_id w152d_gpu_clk_of_match[] = {
	{ .compatible = "amlogic,w152d-mali-clk" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, w152d_gpu_clk_of_match);

static struct platform_driver w152d_gpu_clk_driver = {
	.probe = w152d_gpu_clk_probe,
	.driver = {
		.name = "w152d-gpu-clk",
		.of_match_table = w152d_gpu_clk_of_match,
	},
};
module_platform_driver(w152d_gpu_clk_driver);

MODULE_DESCRIPTION("Amlogic S905L4 (GXLX4) Mali-450 GPU Clock Driver for ZTE W152D");
MODULE_LICENSE("GPL");
