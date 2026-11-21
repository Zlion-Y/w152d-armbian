echo W152D USB mainline boot
# Green LEDs are active high; red LEDs are active low.
gpio clear GPIOAO_4
gpio clear GPIOAO_5
gpio clear GPIOAO_9
gpio clear GPIOAO_7
setenv w152d_old_args "${bootargs}"
setenv w152d_old_fdt_high "${fdt_high}"
setenv w152d_old_initrd_high "${initrd_high}"
if fatload usb 0:1 0x08600000 w152d/mainline/Image; then
    if itest ${filesize} == 0x@IMAGE_SIZE@; then
        if fatload usb 0:1 0x0b800000 w152d/mainline/initramfs.cpio.gz; then
            setenv w152d_ml_rd_size ${filesize}
            if itest ${filesize} == 0x@INITRD_SIZE@; then
                if fatload usb 0:1 0x0d000000 w152d/mainline/integrated-probe.dtb; then
                    if itest ${filesize} == 0x@DTB_SIZE@; then
                        if fdt addr 0x0d000000 && fdt resize 0x10000; then
                            powerset 8 0
                            if itest.l *0xfe00400c == 0; then
                                mw.l fe00400c 00111111 1
                            fi
                            if itest.l *0xfe00400c == 0x00111111; then
                                gpio set GPIOX_6
                                setenv fdt_high 0xffffffffffffffff
                                setenv initrd_high 0xffffffffffffffff
                                setenv bootargs 'earlycon=meson,0xfe07a000,921600 console=ttyS0,921600 keep_bootcon loglevel=7 oops=panic panic=12 rdinit=/init'
                                booti 0x08600000 0x0b800000:${w152d_ml_rd_size} 0x0d000000
                            fi
                        fi
                    fi
                fi
            fi
        fi
    fi
fi
setenv bootargs "${w152d_old_args}"
setenv fdt_high "${w152d_old_fdt_high}"
setenv initrd_high "${w152d_old_initrd_high}"
echo W152D mainline boot returned
