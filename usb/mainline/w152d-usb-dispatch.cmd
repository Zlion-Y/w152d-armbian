echo W152D USB boot dispatcher
if test -z "${w152d_usbdev}"; then
    setenv w152d_usbdev 0
fi
if fatload usb ${w152d_usbdev}:1 0x030c0000 w152d/mainline/boot.arm 4; then
    if itest.l *0x030c0000 == 0x544f4f42; then
        mw.l 0x030c0000 0 1
        if fatwrite usb ${w152d_usbdev}:1 0x030c0000 w152d/mainline/boot.arm 4; then
            if fatload usb ${w152d_usbdev}:1 0x030a0000 w152d/mainline/boot.scr; then
                source 0x030a0000
            fi
        fi
    fi
fi
setenv w152d_usbdev
echo W152D mainline USB boot skipped or returned
