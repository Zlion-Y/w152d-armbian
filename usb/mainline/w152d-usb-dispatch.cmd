echo W152D USB boot dispatcher
if fatload usb 0:1 0x030c0000 w152d/mainline/boot.arm; then
    if itest.l *0x030c0000 == 0x544f4f42; then
        mw.l 0x030c0000 0 1
        if fatwrite usb 0:1 0x030c0000 w152d/mainline/boot.arm 4; then
            if fatload usb 0:1 0x030a0000 w152d/mainline/boot.scr; then
                source 0x030a0000
            fi
        fi
    fi
fi
echo W152D USB stock fallback
if fatload usb 0:1 0x030a0000 w152d/aml_autoscript.usb-stock.bak; then
    source 0x030a0000
fi
