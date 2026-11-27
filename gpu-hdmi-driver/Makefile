ifneq ($(KERNELRELEASE),)
obj-m += w152d_dt_overlay.o
obj-m += w152d_gpu_clk.o
obj-m += w152d_drm.o
else
KDIR ?= /lib/modules/$(shell uname -r)/build
DTC ?= dtc
PYTHON ?= python3

.PHONY: all modules dtbs clean

all: modules dtbs

modules: w152d_overlay_dtbo.h
	chmod +x $(CURDIR)/gcc-wrap.sh
	$(MAKE) -C $(KDIR) M=$(CURDIR) CC=$(CURDIR)/gcc-wrap.sh modules

w152d_overlay_dtbo.h: w152d_overlay.dts
	$(DTC) -@ -I dts -O dtb -o w152d_overlay.dtbo w152d_overlay.dts
	$(PYTHON) -c 'b=open("w152d_overlay.dtbo","rb").read(); print("static const u8 w152d_overlay_dtbo[] __aligned(8) = {" + ",".join(hex(x) for x in b) + "};")' > w152d_overlay_dtbo.h

dtbs: meson-gxlx4-w152d.dtb meson-gxlx4-w152d-emmc.dtb

meson-gxlx4-w152d.dtb: meson-gxlx4-w152d.dts
	$(DTC) -I dts -O dtb -o $@ $<

meson-gxlx4-w152d-emmc.dtb: meson-gxlx4-w152d-emmc.dts
	$(DTC) -I dts -O dtb -o $@ $<

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
	rm -f w152d_overlay.dtbo w152d_overlay_dtbo.h
endif
