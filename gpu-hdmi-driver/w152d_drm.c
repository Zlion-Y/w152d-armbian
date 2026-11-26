// SPDX-License-Identifier: GPL-2.0
/*
 * Amlogic S905L4 (Meson GXLX4) VPU OSD1 + HDMI 2.1 TX DRM/KMS Driver for ZTE W152D
 *
 * Drives the S905L4 VPU OSD v7 linear DMA scanout engine (0xff000000) and
 * HDMI 2.1 TX status/EDID pipeline initialized by BL33 U-Boot (hdmitx21),
 * providing:
 *   - Atomic KMS /dev/dri/card0 ("meson" driver name for automatic Mesa kmsro + lima pairing)
 *   - Hardware CMA zero-copy scanout & 64B-aligned PRIME DMA-BUF import from Mali-450 (lima)
 *   - Hardware VSync interrupt (GIC_SPI 197 / 0xc5) with automatic fallback self-test
 *   - Hardware alpha-replace for XRGB8888/RGB888/RGB565 + per-pixel alpha for ARGB8888
 *   - Authentic HDMI EDID exposure from firmware handoff + /dev/fb0 fbcon console
 */

#include <linux/atomic.h>
#include <linux/ctype.h>
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/interrupt.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>

#include <drm/drm_aperture.h>
#include <drm/drm_atomic.h>
#include <drm/drm_atomic_helper.h>
#include <drm/drm_connector.h>
#include <drm/drm_damage_helper.h>
#include <drm/drm_drv.h>
#include <drm/drm_edid.h>
#include <drm/drm_fb_dma_helper.h>
#include <drm/drm_fbdev_dma.h>
#include <drm/drm_fourcc.h>
#include <drm/drm_framebuffer.h>
#include <drm/drm_gem_atomic_helper.h>
#include <drm/drm_gem_dma_helper.h>
#include <drm/drm_gem_framebuffer_helper.h>
#include <drm/drm_managed.h>
#include <drm/drm_modeset_helper_vtables.h>
#include <drm/drm_probe_helper.h>
#include <drm/drm_simple_kms_helper.h>
#include <drm/drm_vblank.h>

/* S905L4 VPU register byte offsets (reg_index << 2 from 0xff000000) */
#define VPU_REG(idx)			((idx) << 2)
#define VIU_OSD1_CTRL_STAT		VPU_REG(0x1a10)
#define VIU_OSD1_BLK0_CFG_W4		VPU_REG(0x1a13)
#define VIU_OSD1_BLK1_CFG_W4		VPU_REG(0x1a14) /* linear phys_addr >> 4 */
#define VIU_OSD1_BLK2_CFG_W4		VPU_REG(0x1a15) /* linear stride >> 4 in [11:0] */
#define VIU_OSD1_BLK0_CFG_W0		VPU_REG(0x1a1b)
#define VIU_OSD1_BLK0_CFG_W1		VPU_REG(0x1a1c)
#define VIU_OSD1_BLK0_CFG_W2		VPU_REG(0x1a1d)
#define VIU_OSD1_BLK0_CFG_W3		VPU_REG(0x1a1e)
#define VIU_OSD1_CTRL_STAT2		VPU_REG(0x1a2d)
#define ENCP_VIDEO_EN			VPU_REG(0x1b80)
#define VPP_MISC			VPU_REG(0x1d26)

/* VIU_OSD1_CTRL_STAT bits */
#define OSD_ENABLE			BIT(0)
#define OSD_MEM_LINEAR_ADDR		BIT(2)
#define OSD_GLOBAL_ALPHA_MASK		GENMASK(20, 12)
#define OSD_GLOBAL_ALPHA_MAX		(0x1ffU << 12)
#define OSD_BLK0_ENABLE			BIT(21)

/* VIU_OSD1_CTRL_STAT2 bits */
#define OSD_REPLACE_SHIFT		6
#define OSD_REPLACE_VAL_MASK		GENMASK(13, 6)
#define OSD_REPLACE_EN			BIT(14)

/* VIU_OSD1_BLK0_CFG_W0 values (tbl_addr=0x40, little_endian=BIT(15)) */
#define OSD_W0_BASE			((0x40U << 16) | BIT(15))
#define OSD_BLK_MODE_16			(4U << 8)
#define OSD_BLK_MODE_32			(5U << 8)
#define OSD_BLK_MODE_24			(7U << 8)
#define OSD_CMAT_16_RGB565		(2U << 2)
#define OSD_CMAT_32_ARGB		(1U << 2) /* B,G,R,A in little-endian = XRGB8888/ARGB8888 */
#define OSD_CMAT_32_ABGR		(2U << 2) /* R,G,B,A in little-endian = XBGR8888/ABGR8888 */
#define OSD_CMAT_24_RGB			(0U << 2)

#define VPP_POSTBLEND_EN		BIT(7)

#define UBOOT_LOG_PHYS			0x11000000ULL
#define UBOOT_LOG_SIZE			0x40000UL
#define FW_FB_PHYS			0x7f000000ULL
#define FW_FB_SIZE			0x800000ULL

struct w152d_drm_priv {
	struct drm_device drm;
	struct drm_simple_display_pipe pipe;
	struct drm_connector connector;
	void __iomem *vpu;
	void __iomem *hdmitx_top;
	void __iomem *gpioh_in;
	int irq;
	bool irq_working;
	atomic_t irq_hits;
	u32 osd_w;
	u32 osd_h;
	u8 edid_raw[256];
	size_t edid_len;
};

#define to_w152d_drm(_drm) container_of(_drm, struct w152d_drm_priv, drm)

static const u32 w152d_formats[] = {
	DRM_FORMAT_XRGB8888,
	DRM_FORMAT_ARGB8888,
	DRM_FORMAT_XBGR8888,
	DRM_FORMAT_ABGR8888,
	DRM_FORMAT_RGB888,
	DRM_FORMAT_RGB565,
};

static int hex_byte_parse(const char *p)
{
	int hi = hex_to_bin(p[0]);
	int lo = hex_to_bin(p[1]);

	if (hi < 0 || lo < 0)
		return -1;
	return (hi << 4) | lo;
}

static void w152d_try_extract_uboot_edid(struct w152d_drm_priv *priv)
{
	const char *marker = "dump EDID rawdata";
	char *buf, *pos;
	void *map;
	size_t i;
	u8 sum;

	map = memremap(UBOOT_LOG_PHYS, UBOOT_LOG_SIZE, MEMREMAP_WB);
	if (!map)
		return;

	buf = kvmalloc(UBOOT_LOG_SIZE + 1, GFP_KERNEL);
	if (!buf) {
		memunmap(map);
		return;
	}

	memcpy(buf, map, UBOOT_LOG_SIZE);
	memunmap(map);
	buf[UBOOT_LOG_SIZE] = '\0';

	/* Replace NULs with spaces so strstr scans full ring buffer */
	for (i = 0; i < UBOOT_LOG_SIZE; i++) {
		if (buf[i] == '\0')
			buf[i] = ' ';
	}

	pos = strstr(buf, marker);
	while (pos) {
		char *next = strstr(pos + strlen(marker), marker);
		if (!next)
			break;
		pos = next;
	}

	if (pos) {
		pos += strlen(marker);
		while (*pos && !isxdigit(*pos))
			pos++;

		for (i = 0; i < 256 && isxdigit(pos[0]) && isxdigit(pos[1]); i++) {
			int b = hex_byte_parse(pos);
			if (b < 0)
				break;
			priv->edid_raw[i] = (u8)b;
			pos += 2;
		}

		if (i >= 128 &&
		    priv->edid_raw[0] == 0x00 && priv->edid_raw[1] == 0xff &&
		    priv->edid_raw[7] == 0x00) {
			sum = 0;
			for (size_t k = 0; k < 128; k++)
				sum += priv->edid_raw[k];
			if (sum == 0)
				priv->edid_len = (i == 256) ? 256 : 128;
		}
	}

	kvfree(buf);
}

static enum drm_connector_status
w152d_connector_detect(struct drm_connector *connector, bool force)
{
	struct w152d_drm_priv *priv = to_w152d_drm(connector->dev);

	/* Keep active whenever VENC is running or HPD pin is asserted */
	if (readl(priv->vpu + ENCP_VIDEO_EN) & 0x1)
		return connector_status_connected;
	if (priv->gpioh_in && (readl(priv->gpioh_in) & (BIT(0) | BIT(2))))
		return connector_status_connected;
	return connector_status_connected;
}

static const struct drm_connector_funcs w152d_connector_funcs = {
	.detect = w152d_connector_detect,
	.fill_modes = drm_helper_probe_single_connector_modes,
	.destroy = drm_connector_cleanup,
	.reset = drm_atomic_helper_connector_reset,
	.atomic_duplicate_state = drm_atomic_helper_connector_duplicate_state,
	.atomic_destroy_state = drm_atomic_helper_connector_destroy_state,
};

static int w152d_connector_get_modes(struct drm_connector *connector)
{
	struct w152d_drm_priv *priv = to_w152d_drm(connector->dev);
	struct drm_display_mode *mode, *m;
	int count = 0;
	bool found_native = false;

	if (priv->edid_len >= 128) {
		const struct drm_edid *drm_edid;

		drm_edid = drm_edid_alloc(priv->edid_raw, priv->edid_len);
		if (drm_edid) {
			drm_edid_connector_update(connector, drm_edid);
			count = drm_edid_connector_add_modes(connector);
			drm_edid_free(drm_edid);
		}
	} else {
		drm_edid_connector_update(connector, NULL);
	}

	list_for_each_entry(m, &connector->probed_modes, head) {
		if (m->hdisplay == priv->osd_w && m->vdisplay == priv->osd_h &&
		    drm_mode_vrefresh(m) == 60) {
			m->type |= DRM_MODE_TYPE_PREFERRED | DRM_MODE_TYPE_DRIVER;
			found_native = true;
		} else {
			m->type &= ~DRM_MODE_TYPE_PREFERRED;
		}
	}

	if (!found_native) {
		mode = drm_cvt_mode(connector->dev, priv->osd_w, priv->osd_h,
				    60, false, false, false);
		if (mode) {
			if (priv->osd_w == 1920 && priv->osd_h == 1080) {
				/* Exact CEA-861 VIC 16 1080p60 timing */
				mode->clock = 148500;
				mode->hdisplay = 1920;
				mode->hsync_start = 2008;
				mode->hsync_end = 2052;
				mode->htotal = 2200;
				mode->vdisplay = 1080;
				mode->vsync_start = 1084;
				mode->vsync_end = 1089;
				mode->vtotal = 1125;
				mode->flags = DRM_MODE_FLAG_PHSYNC | DRM_MODE_FLAG_PVSYNC;
			}
			drm_mode_set_name(mode);
			mode->type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED;
			drm_mode_probed_add(connector, mode);
			count++;
		}
	}

	return count;
}

static const struct drm_connector_helper_funcs w152d_connector_helper_funcs = {
	.get_modes = w152d_connector_get_modes,
};

static enum drm_mode_status
w152d_pipe_mode_valid(struct drm_simple_display_pipe *pipe,
		      const struct drm_display_mode *mode)
{
	struct w152d_drm_priv *priv = to_w152d_drm(pipe->crtc.dev);

	if (mode->hdisplay != priv->osd_w || mode->vdisplay != priv->osd_h)
		return MODE_BAD;
	return MODE_OK;
}

static void w152d_osd1_program(struct w152d_drm_priv *priv,
			       struct drm_plane_state *state)
{
	struct drm_framebuffer *fb = state->fb;
	struct drm_gem_dma_object *dma_obj;
	dma_addr_t paddr;
	u32 src_x, src_y, stride_16, w0, stat2, ctrl, geom_x, geom_y;
	bool force_opaque = true;

	if (!fb)
		return;

	dma_obj = drm_fb_dma_get_gem_obj(fb, 0);
	if (!dma_obj)
		return;

	src_x = state->src.x1 >> 16;
	src_y = state->src.y1 >> 16;
	paddr = dma_obj->dma_addr + fb->offsets[0] +
		(dma_addr_t)src_y * fb->pitches[0] +
		(dma_addr_t)src_x * fb->format->cpp[0];
	paddr &= ~(dma_addr_t)0xf;

	stride_16 = (fb->pitches[0] >> 4) & 0xfffU;

	switch (fb->format->format) {
	case DRM_FORMAT_ARGB8888:
		force_opaque = false;
		fallthrough;
	case DRM_FORMAT_XRGB8888:
		w0 = OSD_W0_BASE | OSD_BLK_MODE_32 | OSD_CMAT_32_ARGB;
		break;
	case DRM_FORMAT_ABGR8888:
		force_opaque = false;
		fallthrough;
	case DRM_FORMAT_XBGR8888:
		w0 = OSD_W0_BASE | OSD_BLK_MODE_32 | OSD_CMAT_32_ABGR;
		break;
	case DRM_FORMAT_RGB888:
		w0 = OSD_W0_BASE | OSD_BLK_MODE_24 | OSD_CMAT_24_RGB;
		break;
	case DRM_FORMAT_RGB565:
		w0 = OSD_W0_BASE | OSD_BLK_MODE_16 | OSD_CMAT_16_RGB565;
		break;
	default:
		w0 = OSD_W0_BASE | OSD_BLK_MODE_32 | OSD_CMAT_32_ARGB;
		break;
	}

	geom_x = ((priv->osd_w - 1) << 16) | 0U;
	geom_y = ((priv->osd_h - 1) << 16) | 0U;

	/* Program linear DMA base address and 16-byte stride */
	writel((u32)(paddr >> 4), priv->vpu + VIU_OSD1_BLK1_CFG_W4);
	writel((readl(priv->vpu + VIU_OSD1_BLK2_CFG_W4) & ~0xfffU) | stride_16,
	       priv->vpu + VIU_OSD1_BLK2_CFG_W4);

	/* Program pixel format & alpha replacement */
	stat2 = readl(priv->vpu + VIU_OSD1_CTRL_STAT2);
	if (force_opaque)
		stat2 = (stat2 & ~(OSD_REPLACE_VAL_MASK | OSD_REPLACE_EN)) |
			(0xffU << OSD_REPLACE_SHIFT) | OSD_REPLACE_EN;
	else
		stat2 &= ~OSD_REPLACE_EN;
	writel(stat2, priv->vpu + VIU_OSD1_CTRL_STAT2);
	writel(w0, priv->vpu + VIU_OSD1_BLK0_CFG_W0);

	/* Program OSD1 input & output window geometry */
	writel(geom_x, priv->vpu + VIU_OSD1_BLK0_CFG_W1);
	writel(geom_y, priv->vpu + VIU_OSD1_BLK0_CFG_W2);
	writel(geom_x, priv->vpu + VIU_OSD1_BLK0_CFG_W3);
	writel(geom_y, priv->vpu + VIU_OSD1_BLK0_CFG_W4);

	/* Enable OSD1 linear scanout + VPP postblend */
	ctrl = readl(priv->vpu + VIU_OSD1_CTRL_STAT);
	ctrl &= ~OSD_GLOBAL_ALPHA_MASK;
	ctrl |= OSD_ENABLE | OSD_MEM_LINEAR_ADDR | OSD_GLOBAL_ALPHA_MAX | OSD_BLK0_ENABLE;
	writel(ctrl, priv->vpu + VIU_OSD1_CTRL_STAT);

	writel(readl(priv->vpu + VPP_MISC) | VPP_POSTBLEND_EN,
	       priv->vpu + VPP_MISC);
}

static void w152d_pipe_enable(struct drm_simple_display_pipe *pipe,
			      struct drm_crtc_state *crtc_state,
			      struct drm_plane_state *plane_state)
{
	struct w152d_drm_priv *priv = to_w152d_drm(pipe->crtc.dev);

	if (priv->irq_working)
		drm_crtc_vblank_on(&pipe->crtc);
	w152d_osd1_program(priv, plane_state);
}

static void w152d_pipe_disable(struct drm_simple_display_pipe *pipe)
{
	struct w152d_drm_priv *priv = to_w152d_drm(pipe->crtc.dev);
	u32 ctrl;

	ctrl = readl(priv->vpu + VIU_OSD1_CTRL_STAT);
	writel(ctrl & ~OSD_ENABLE, priv->vpu + VIU_OSD1_CTRL_STAT);

	if (priv->irq_working)
		drm_crtc_vblank_off(&pipe->crtc);
}

static int w152d_pipe_check(struct drm_simple_display_pipe *pipe,
			    struct drm_plane_state *plane_state,
			    struct drm_crtc_state *crtc_state)
{
	struct w152d_drm_priv *priv = to_w152d_drm(pipe->crtc.dev);

	if (!priv->irq_working)
		crtc_state->no_vblank = true;
	return 0;
}

static void w152d_pipe_update(struct drm_simple_display_pipe *pipe,
			      struct drm_plane_state *old_state)
{
	struct drm_crtc *crtc = &pipe->crtc;
	struct w152d_drm_priv *priv = to_w152d_drm(crtc->dev);
	struct drm_pending_vblank_event *event;

	if (pipe->plane.state->fb)
		w152d_osd1_program(priv, pipe->plane.state);

	event = crtc->state->event;
	if (event) {
		crtc->state->event = NULL;
		spin_lock_irq(&crtc->dev->event_lock);
		if (priv->irq_working && drm_crtc_vblank_get(crtc) == 0)
			drm_crtc_arm_vblank_event(crtc, event);
		else
			drm_crtc_send_vblank_event(crtc, event);
		spin_unlock_irq(&crtc->dev->event_lock);
	}
}

static int w152d_pipe_enable_vblank(struct drm_simple_display_pipe *pipe)
{
	return 0;
}

static void w152d_pipe_disable_vblank(struct drm_simple_display_pipe *pipe)
{
}

static const struct drm_simple_display_pipe_funcs w152d_pipe_funcs = {
	.mode_valid = w152d_pipe_mode_valid,
	.enable = w152d_pipe_enable,
	.disable = w152d_pipe_disable,
	.check = w152d_pipe_check,
	.update = w152d_pipe_update,
	.enable_vblank = w152d_pipe_enable_vblank,
	.disable_vblank = w152d_pipe_disable_vblank,
};

static irqreturn_t w152d_drm_irq(int irq, void *data)
{
	struct w152d_drm_priv *priv = data;

	atomic_inc(&priv->irq_hits);
	if (priv->irq_working)
		drm_crtc_handle_vblank(&priv->pipe.crtc);
	return IRQ_HANDLED;
}

static int w152d_drm_dumb_create(struct drm_file *file_priv,
				 struct drm_device *drm,
				 struct drm_mode_create_dumb *args)
{
	/* 64-byte stride alignment satisfies both VPU OSD1 MIF (16B) and Mali-450 Lima GPU */
	args->pitch = ALIGN(DIV_ROUND_UP(args->width * args->bpp, 8), 64);
	return drm_gem_dma_dumb_create_internal(file_priv, drm, args);
}

DEFINE_DRM_GEM_DMA_FOPS(w152d_drm_fops);

static const struct drm_driver w152d_drm_driver = {
	.driver_features = DRIVER_GEM | DRIVER_MODESET | DRIVER_ATOMIC,
	.fops = &w152d_drm_fops,
	DRM_GEM_DMA_DRIVER_OPS_WITH_DUMB_CREATE(w152d_drm_dumb_create),
	DRM_FBDEV_DMA_DRIVER_OPS,
	/* Use "meson" so Mesa kmsro (meson_dri.so) automatically binds with Mali-450 lima */
	.name = "meson",
	.desc = "Amlogic S905L4 W152D VPU OSD1 + HDMI2.1 DRM",
	.date = "20261126",
	.major = 1,
	.minor = 0,
};

static const struct drm_mode_config_funcs w152d_mode_config_funcs = {
	.fb_create = drm_gem_fb_create,
	.atomic_check = drm_atomic_helper_check,
	.atomic_commit = drm_atomic_helper_commit,
};

static int w152d_drm_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct w152d_drm_priv *priv;
	struct drm_device *drm;
	struct resource *res;
	u32 w1, w2;
	int ret;

	ret = dma_set_mask_and_coherent(dev, DMA_BIT_MASK(32));
	if (ret)
		return dev_err_probe(dev, ret, "failed to set 32-bit DMA mask\n");

	priv = devm_drm_dev_alloc(dev, &w152d_drm_driver,
				  struct w152d_drm_priv, drm);
	if (IS_ERR(priv))
		return PTR_ERR(priv);

	drm = &priv->drm;
	platform_set_drvdata(pdev, priv);
	atomic_set(&priv->irq_hits, 0);

	res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
	if (!res)
		return -EINVAL;
	priv->vpu = devm_ioremap(dev, res->start, resource_size(res));
	if (!priv->vpu)
		return -ENOMEM;

	res = platform_get_resource(pdev, IORESOURCE_MEM, 1);
	if (res)
		priv->hdmitx_top = devm_ioremap(dev, res->start, resource_size(res));

	res = platform_get_resource(pdev, IORESOURCE_MEM, 2);
	if (res)
		priv->gpioh_in = devm_ioremap(dev, res->start, resource_size(res));

	/* Detect OSD1 active plane dimensions configured by BL33 U-Boot */
	w1 = readl(priv->vpu + VIU_OSD1_BLK0_CFG_W1);
	w2 = readl(priv->vpu + VIU_OSD1_BLK0_CFG_W2);
	priv->osd_w = ((w1 >> 16) & 0x1fffU) + 1;
	priv->osd_h = ((w2 >> 16) & 0x1fffU) + 1;
	if (priv->osd_w < 640 || priv->osd_w > 3840 ||
	    priv->osd_h < 480 || priv->osd_h > 2160) {
		priv->osd_w = 1920;
		priv->osd_h = 1080;
	}

	w152d_try_extract_uboot_edid(priv);

	ret = drmm_mode_config_init(drm);
	if (ret)
		return ret;

	drm->mode_config.min_width = 640;
	drm->mode_config.max_width = 3840;
	drm->mode_config.min_height = 480;
	drm->mode_config.max_height = 2160;
	drm->mode_config.preferred_depth = 24;
	drm->mode_config.funcs = &w152d_mode_config_funcs;

	drm_connector_helper_add(&priv->connector, &w152d_connector_helper_funcs);
	ret = drm_connector_init(drm, &priv->connector, &w152d_connector_funcs,
				 DRM_MODE_CONNECTOR_HDMIA);
	if (ret)
		return ret;

	ret = drm_simple_display_pipe_init(drm, &priv->pipe, &w152d_pipe_funcs,
					   w152d_formats, ARRAY_SIZE(w152d_formats),
					   NULL, &priv->connector);
	if (ret)
		return ret;

	/* Probe & self-test hardware VIU VSync interrupt (60Hz -> ~16.7ms period) */
	priv->irq = platform_get_irq_optional(pdev, 0);
	if (priv->irq > 0) {
		ret = devm_request_irq(dev, priv->irq, w152d_drm_irq,
				       IRQF_TRIGGER_RISING, "w152d-viu-vsync", priv);
		if (!ret) {
			msleep(35);
			if (atomic_read(&priv->irq_hits) > 0) {
				ret = drm_vblank_init(drm, 1);
				if (!ret)
					priv->irq_working = true;
			}
		}
	}

	drm_mode_config_reset(drm);

	ret = drm_aperture_remove_conflicting_framebuffers(FW_FB_PHYS, FW_FB_SIZE,
							   &w152d_drm_driver);
	if (ret)
		dev_warn(dev, "conflicting fb removal returned %d\n", ret);

	ret = drm_dev_register(drm, 0);
	if (ret)
		return ret;

	drm_fbdev_dma_setup(drm, 32);

	dev_info(dev,
		 "S905L4 HDMI2.1/OSD1 KMS ready: %ux%u@60Hz, vsync_irq=%d(%s, hits=%d), edid=%zuB\n",
		 priv->osd_w, priv->osd_h, priv->irq,
		 priv->irq_working ? "hw" : "sw-fallback",
		 atomic_read(&priv->irq_hits), priv->edid_len);
	return 0;
}

static void w152d_drm_remove(struct platform_device *pdev)
{
	struct w152d_drm_priv *priv = platform_get_drvdata(pdev);

	drm_dev_unregister(&priv->drm);
	drm_atomic_helper_shutdown(&priv->drm);
}

static const struct of_device_id w152d_drm_of_match[] = {
	{ .compatible = "amlogic,w152d-vpu-drm" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, w152d_drm_of_match);

static struct platform_driver w152d_drm_platform_driver = {
	.probe = w152d_drm_probe,
	.remove = w152d_drm_remove,
	.driver = {
		.name = "w152d-vpu-drm",
		.of_match_table = w152d_drm_of_match,
	},
};
module_platform_driver(w152d_drm_platform_driver);

MODULE_DESCRIPTION("Amlogic S905L4 (GXLX4) VPU OSD1 + HDMI 2.1 DRM/KMS Driver for ZTE W152D");
MODULE_LICENSE("GPL");
