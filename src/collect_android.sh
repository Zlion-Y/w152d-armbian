#!/system/bin/sh
# Read-only hardware/boot inventory. No reboot, partition writes, or slot changes.
section() { printf '\n=== %s ===\n' "$1"; }
section identity
id
uname -a
getprop ro.product.model
getprop ro.board.platform
getprop ro.boot.slot_suffix
getprop ro.boot.verifiedbootstate
getprop ro.boot.flash.locked
getprop ro.build.version.release
section boot_command_line
cat /proc/cmdline
section boot_control_read_only
if command -v bootctl >/dev/null 2>&1; then
    bootctl hal-info
    bootctl get-current-slot
    bootctl is-slot-bootable 0
    bootctl is-slot-marked-successful 0
    bootctl is-slot-bootable 1
    bootctl is-slot-marked-successful 1
fi
section partitions
ls -l /dev/block/by-name
cat /proc/partitions
section filesystems
cat /proc/filesystems
cat /proc/mounts
section modules
cat /proc/modules
section module_load_lists
for f in /lib/modules/modules.load /vendor/lib/modules/modules.load /vendor/etc/init/hw/init.amlogic.board.rc; do
    if [ -f "$f" ]; then echo "--- $f"; cat "$f"; fi
done
section network_and_usb
ip link
for f in /sys/bus/sdio/devices/*/uevent /sys/bus/usb/devices/*/uevent; do
    if [ -f "$f" ]; then echo "--- $f"; cat "$f"; fi
done
section kernel_config_available
ls -l /proc/config.gz
section available_tools
for t in busybox chroot unshare mount switch_root kexec; do command -v "$t"; done
section recent_kernel_messages
dmesg | tail -n 180
section end
