#!/usr/bin/env bash
# Assemble boot artifacts from an already compiled W152D Linux tree.
set -euo pipefail

kernel=$(realpath "${1:?compiled W152D kernel tree required}")
busybox=$(realpath "${2:?static ARM64 BusyBox required}")
firmware=$(realpath "${3:?firmware directory required}")
output=$(realpath -m "${4:?new output directory required}")
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test ! -e "$output"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

release=$(cat "$kernel/include/config/kernel.release")
case "$release" in 6.12.*) ;; *) echo "Expected Linux 6.12: $release" >&2; exit 1 ;; esac
LC_ALL=C readelf -h "$busybox" >"$work/busybox.elf"
grep -Eq 'Machine:[[:space:]]+AArch64' "$work/busybox.elf"
LC_ALL=C readelf -l "$busybox" >"$work/busybox.program"
if grep -q 'INTERP' "$work/busybox.program"; then
    echo 'BusyBox must be statically linked' >&2
    exit 1
fi
(
    cd "$firmware"
    sha256sum -c <<'EOF'
2515a0a09d8e94da63aa2769b6457eee3c56c300641675da3aeb5ede09dacfaf  wcnmodem.bin
4c95dac0bf3681e1af31e89d6bd54494ce183839cf4a2e19c5953e2b243398f7  wifi_56630001_3ant.ini
EOF
    test -s regulatory.db
    test -s regulatory.db.p7s
)
for flag in GPIO_W152D_AO GPIO_REGMAP LEDS_GPIO LEDS_TRIGGER_NETDEV; do
    grep -qx "CONFIG_${flag}=y" "$kernel/.config"
done

cpp -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -I "$kernel/include" \
    "$repo/mainline/dts/meson-gxlx4-w152d-integrated-probe.dts" -o "$work/board.dts"
dtc -I dts -O dtb -o "$work/integrated-probe.dtb" "$work/board.dts"

# Keep cpio manifest paths relative to support spaces in caller paths.
mkdir "$work/sources"
cp "$busybox" "$work/sources/busybox"
cp "$repo/usb/mainline/"{init,w152d_usb_root} "$work/sources/"
for name in wcnmodem.bin wifi_56630001_3ant.ini regulatory.db regulatory.db.p7s; do
    cp "$firmware/$name" "$work/sources/"
done
modules=(
    drivers/usb/host/xhci-plat-hcd.ko
    drivers/net/phy/smsc.ko
    drivers/net/phy/meson-gxl.ko
    drivers/net/mdio/mdio-mux-meson-g12a.ko
    net/rfkill/rfkill.ko
    net/wireless/cfg80211.ko
    drivers/net/wireless/uwe5622/unisocwifi/sprdwl_ng.ko
)
for module in "${modules[@]}"; do
    vermagic=$(modinfo -F vermagic "$kernel/$module")
    if [[ $vermagic != "$release "*aarch64* ]]; then
        echo "Unexpected module vermagic for $module: $vermagic" >&2
        exit 1
    fi
    cp "$kernel/$module" "$work/sources/"
done

cc "$kernel/usr/gen_init_cpio.c" -o "$work/gen_init_cpio"
(
    cd "$work"
    cat >initramfs.list <<'EOF'
dir /bin 0755 0 0
dir /dev 0755 0 0
dir /proc 0755 0 0
dir /sys 0755 0 0
dir /drivers 0755 0 0
dir /lib 0755 0 0
dir /lib/firmware 0755 0 0
nod /dev/console 0600 0 0 c 5 1
nod /dev/null 0666 0 0 c 1 3
file /bin/busybox sources/busybox 0755 0 0
file /init sources/init 0755 0 0
file /bin/w152d-usb-root sources/w152d_usb_root 0755 0 0
EOF
    for module in "${modules[@]}"; do
        name=${module##*/}
        printf 'file /drivers/%s sources/%s 0644 0 0\n' "$name" "$name"
    done >>initramfs.list
    for name in wcnmodem.bin wifi_56630001_3ant.ini regulatory.db regulatory.db.p7s; do
        printf 'file /lib/firmware/%s sources/%s 0644 0 0\n' "$name" "$name"
    done >>initramfs.list
    ./gen_init_cpio initramfs.list | gzip -n -9 >initramfs.cpio.gz
)

mkdir "$output"
cp "$kernel/arch/arm64/boot/Image" "$work/integrated-probe.dtb" "$work/initramfs.cpio.gz" "$output/"
cp "$kernel/.config" "$output/kernel.config"
(cd "$output" && sha256sum Image integrated-probe.dtb initramfs.cpio.gz kernel.config >SHA256SUMS)
