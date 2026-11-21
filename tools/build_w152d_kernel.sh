#!/usr/bin/env bash
# Build the W152D kernel and boot modules from a pinned source archive.
set -euo pipefail

if [[ $# != 2 ]]; then
    echo "Usage: bash $0 kernel-source-archive new-build-directory" >&2
    exit 2
fi

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
archive=$(realpath -e -- "$1")
work=$(realpath -m -- "$2")
actual=$(sha256sum <"$archive")
case ${actual%% *} in
    b1a2562be56e42afb3f8489d4c2a7ac472ac23098f1ef1c1e40da601f54625eb)
        localversion=
        ;;
    43029ff144d979d268c69f8ac855d729a05e89402bca6f0b65b6efa85e5b6b2e)
        localversion=-w152d
        ;;
    *)
        echo "Expected a pinned Linux 6.12 source archive from docs/BUILD.md" >&2
        exit 1
        ;;
esac

kernel="$work/linux-6.12"
build="$work/build"
mkdir -- "$work"
mkdir -- "$kernel" "$build"
tar -xf "$archive" -C "$kernel" --strip-components=1

apply=(env "GIT_CEILING_DIRECTORIES=$work" git -C "$kernel" apply --whitespace=nowarn)
if [[ -n $localversion ]]; then
    "${apply[@]}" \
        --exclude=drivers/clk/meson/clk-mpll.h \
        --exclude=drivers/clk/meson/clk-pll.c \
        --exclude=drivers/clk/meson/clk-pll.h \
        --exclude=drivers/net/ethernet/stmicro/stmmac/dwmac-meson8b.c \
        "$repo"/mainline/linux-6.12/*.patch
    "${apply[@]}" "$repo"/mainline/unifreq-6.12.118/*.patch
else
    "${apply[@]}" "$repo"/mainline/linux-6.12/*.patch
fi
install -m 0644 "$repo/mainline/drivers/w152d-usb-clock-probe.c" \
    "$repo/mainline/drivers/w152d-usb3-phy-probe.c" "$kernel/drivers/clk/"
install -m 0644 "$repo/mainline/drivers/w152d-ao-gpio.c" "$kernel/drivers/gpio/"
dts_dir="$kernel/arch/arm64/boot/dts/amlogic"
install -m 0644 "$repo"/mainline/dts/*.dts* "$dts_dir/"
dtb=meson-gxlx4-w152d-integrated-probe.dtb
printf '\ndtb-$(CONFIG_ARCH_MESON) += %s\n' "$dtb" >>"$dts_dir/Makefile"

install -m 0644 "$repo/mainline/kernel.config" "$build/.config"
"$kernel/scripts/config" --file "$build/.config" --disable LOCALVERSION_AUTO
export ARCH=arm64
export CROSS_COMPILE=${CROSS_COMPILE-aarch64-linux-gnu-}
make_args=(-C "$kernel" O="$build" LOCALVERSION="$localversion")
make "${make_args[@]}" olddefconfig
make "${make_args[@]}" -j "${JOBS:-$(nproc)}" Image "amlogic/$dtb"
make "${make_args[@]}" -j "${JOBS:-$(nproc)}" \
    drivers/usb/host/xhci-plat-hcd.ko \
    drivers/net/phy/smsc.ko \
    drivers/net/phy/meson-gxl.ko \
    drivers/net/mdio/mdio-mux-meson-g12a.ko \
    net/rfkill/rfkill.ko \
    net/wireless/cfg80211.ko \
    drivers/net/wireless/uwe5622/unisocwifi/sprdwl_ng.ko
