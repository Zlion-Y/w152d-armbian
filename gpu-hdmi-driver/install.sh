#!/usr/bin/env bash
# Build, install, and activate W152D S905L4 Mali-450 GPU + HDMI KMS drivers on Armbian.
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "Please run as root: sudo bash $0 [kernel-release]" >&2
    exit 1
fi

KREL="${1:-$(uname -r)}"
KDIR="/lib/modules/${KREL}/build"
SRC_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -d "${KDIR}" ]]; then
    echo "Kernel headers directory not found: ${KDIR}" >&2
    exit 1
fi

# Rebuild scripts/mod/modpost natively if prebuilt binary requires newer glibc (e.g. GLIBC_2.38 on Bookworm)
if [[ -x "${KDIR}/scripts/mod/modpost" ]] && ! "${KDIR}/scripts/mod/modpost" -h >/dev/null 2>&1; then
    if "${KDIR}/scripts/mod/modpost" 2>&1 | grep -q "GLIBC_"; then
        echo "[*] Rebuilding ${KDIR}/scripts/mod/modpost against local glibc..."
        [[ -f "${KDIR}/scripts/mod/modpost.orig" ]] || cp -a "${KDIR}/scripts/mod/modpost" "${KDIR}/scripts/mod/modpost.orig"
        gcc -O2 -I "${KDIR}/scripts/include" -I "${KDIR}/scripts/mod" \
            "${KDIR}/scripts/mod/modpost.c" \
            "${KDIR}/scripts/mod/file2alias.c" \
            "${KDIR}/scripts/mod/sumversion.c" \
            "${KDIR}/scripts/mod/symsearch.c" \
            -o "${KDIR}/scripts/mod/modpost"
    fi
fi

echo "[*] Building kernel modules and device trees for ${KREL}..."
make -C "${SRC_DIR}" KDIR="${KDIR}" all

EXTRA_DIR="/lib/modules/${KREL}/extra"
mkdir -p "${EXTRA_DIR}"
install -m 0644 \
    "${SRC_DIR}/w152d_dt_overlay.ko" \
    "${SRC_DIR}/w152d_gpu_clk.ko" \
    "${SRC_DIR}/w152d_drm.ko" \
    "${EXTRA_DIR}/"
depmod -a "${KREL}"

echo 'softdep lima pre: governor_simpleondemand w152d_gpu_clk' > /etc/modprobe.d/w152d-gpu-hdmi.conf
printf 'w152d_dt_overlay\nw152d_gpu_clk\nlima\nw152d_drm\n' > /etc/modules-load.d/w152d-gpu-hdmi.conf

if [[ -d /boot/dtb/amlogic ]]; then
    for dtb in meson-gxlx4-w152d.dtb meson-gxlx4-w152d-emmc.dtb; do
        if [[ -f "/boot/dtb/amlogic/${dtb}" && ! -f "/boot/dtb/amlogic/${dtb}.bak" ]]; then
            cp -a "/boot/dtb/amlogic/${dtb}" "/boot/dtb/amlogic/${dtb}.bak"
        fi
        install -m 0644 "${SRC_DIR}/${dtb}" "/boot/dtb/amlogic/${dtb}"
    done
fi

if [[ -f /boot/uEnv.txt ]]; then
    [[ -f /boot/uEnv.txt.bak ]] || cp -a /boot/uEnv.txt /boot/uEnv.txt.bak
    if ! grep -q 'console=tty1' /boot/uEnv.txt; then
        sed -i '/^APPEND=/ s/$/ console=tty1/' /boot/uEnv.txt
    fi
fi

sync

if [[ "${KREL}" == "$(uname -r)" ]]; then
    echo "[*] Activating GPU and HDMI KMS modules live..."
    modprobe w152d_dt_overlay || true
    modprobe w152d_gpu_clk
    modprobe lima || true
    modprobe w152d_drm
    echo "[+] Live status:"
    ls -l /dev/dri /dev/fb0 2>/dev/null || true
fi

echo "[+] Installation complete."
