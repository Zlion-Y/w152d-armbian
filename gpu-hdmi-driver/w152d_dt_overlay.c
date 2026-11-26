// SPDX-License-Identifier: GPL-2.0
/*
 * Dynamic Device Tree Overlay injector for ZTE W152D (S905L4) GPU & HDMI KMS.
 * No-ops cleanly when the base DTB already contains the GPU & VPU DRM nodes;
 * dynamically applies the overlay when booted from an older/unpatched DTB.
 */

#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>

#include "w152d_overlay_dtbo.h"

static int w152d_ovcs_id = -1;

static int __init w152d_dt_overlay_init(void)
{
	struct device_node *np;
	int ret;

	np = of_find_compatible_node(NULL, NULL, "amlogic,w152d-vpu-drm");
	if (np) {
		of_node_put(np);
		pr_info("w152d_dt_overlay: GPU & HDMI nodes already present in base DTB\n");
		return 0;
	}

	ret = of_overlay_fdt_apply(w152d_overlay_dtbo,
				   sizeof(w152d_overlay_dtbo),
				   &w152d_ovcs_id, NULL);
	if (ret) {
		pr_err("w152d_dt_overlay: of_overlay_fdt_apply failed: %d\n", ret);
		w152d_ovcs_id = -1;
		return ret;
	}

	pr_info("w152d_dt_overlay: dynamically applied GPU & HDMI overlay (id=%d)\n",
		w152d_ovcs_id);
	return 0;
}

static void __exit w152d_dt_overlay_exit(void)
{
	if (w152d_ovcs_id >= 0) {
		of_overlay_remove(&w152d_ovcs_id);
		w152d_ovcs_id = -1;
	}
}

module_init(w152d_dt_overlay_init);
module_exit(w152d_dt_overlay_exit);

MODULE_DESCRIPTION("Dynamic DT Overlay Loader for ZTE W152D S905L4 GPU & HDMI");
MODULE_LICENSE("GPL");
