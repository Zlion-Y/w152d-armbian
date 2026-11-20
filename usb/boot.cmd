# W152D USB boot; volatile RAM commands only, no saveenv or flash writes.
echo W152D_ARMBIAN_USB_DIRECT_V1
if fatload usb 0:1 0x01080000 w152d/Image; then
    if fatload usb 0:1 0x10000000 w152d/initramfs.cpio.gz; then
        setenv w152d_initrd_size ${filesize}
        if fatload usb 0:1 0x01000000 w152d/dtb.img; then
            fdt addr 0x01000000
            fdt resize 0x10000
            setenv bootargs "${bootargs} rdinit=/init otg_device=0 loglevel=7 panic=10"
            echo Booting_stock_kernel_and_Armbian_from_USB
            booti 0x01080000 0x10000000:${w152d_initrd_size} 0x01000000
        fi
    fi
fi
echo USB_boot_returned_continuing_internal_Android
setenv w152d_initrd_size
