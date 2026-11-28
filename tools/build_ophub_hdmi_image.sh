#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 || $EUID -ne 0 ]]; then
    echo "Usage (as root): $0 verified-v0.4.0.img[.gz] output.img.gz [w152d-6.12.119-ophub-trial.tgz]" >&2
    exit 2
fi

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
base=$(realpath -- "$1")
output=$(realpath -m -- "$2")
kernel_bundle=${3:-}
if [[ -n $kernel_bundle ]]; then
    kernel_bundle=$(realpath -- "$kernel_bundle")
    printf '%s  %s\n' 553faa8f9117a23d421d27e9fe264630407a141a877793c0c9d2abc589dded4f "$kernel_bundle" | sha256sum -c -
fi
[[ $output == *.img.gz && ! -e $output && ! -e $output.partial ]]
mkdir -p -- "$(dirname -- "$output")"
work=$(mktemp -d "${TMPDIR:-/var/tmp}/w152d-ophub-hdmi.XXXXXXXX")
boot=$work/boot
root=$work/root
source_root=$work/source-root
loop=
source_loop=
cleanup() {
    for path in "$boot" "$root" "$source_root"; do
        if mountpoint -q "$path"; then umount "$path" || return; fi
    done
    if [[ -n $loop ]]; then losetup -d "$loop" || return; fi
    if [[ -n $source_loop ]]; then losetup -d "$source_loop" || return; fi
    rm -rf -- "$work"
    rm -f -- "$output.partial"
}
trap cleanup EXIT
mkdir "$boot" "$root" "$source_root" "$work/driver"

case "$base" in
    *.img.gz)
        printf '%s  %s\n' 596eac37589b357e9fb649452201e1b77c4296b20787d230e50a6e3eb5882f14 "$base" | sha256sum -c -
        pigz -dc -- "$base" | dd of="$work/base.img" bs=4M iflag=fullblock conv=sparse status=none
        base=$work/base.img
        ;;
    *.img)
        printf '%s  %s\n' e03eb2b9f64cf84aff1a235eedecbe8bb2556df6b5d2d140c8ff6e1bbb0e3e7f "$base" | sha256sum -c -
        ;;
    *) echo 'Expected the v0.4.0 standard ophub .img or .img.gz' >&2; exit 2 ;;
esac

# Copy the partition table and FAT32 partition, then populate a new ext4 from
# the verified offline filesystem. Exclude SSH keys even from the ext4 blocks.
dd if="$base" of="$work/w152d.img" bs=512 count=1056768 iflag=fullblock conv=sparse status=none
truncate -s "$(stat -c %s "$base")" "$work/w152d.img"
source_loop=$(losetup --find --show --read-only --partscan "$base")
mount -o ro,noload "${source_loop}p2" "$source_root"
loop=$(losetup --find --show --partscan "$work/w152d.img")
uuid=$(blkid -p -s UUID -o value "${source_loop}p2")
label=$(blkid -p -s LABEL -o value "${source_loop}p2")
[[ $label == ROOTFS ]]
mkfs.ext4 -F -b 4096 -m 0 -N 192000 -L "$label" -U "$uuid" \
    -E lazy_itable_init=0,lazy_journal_init=0 "${loop}p2"
mount "${loop}p1" "$boot"
mount "${loop}p2" "$root"
tar --acls --xattrs --xattrs-include='*' --numeric-owner --sparse \
    --exclude='./etc/ssh/ssh_host_*_key*' -C "$source_root" -cf - . |
    tar --acls --xattrs --xattrs-include='*' --numeric-owner -C "$root" -xpf -
umount "$source_root"
losetup -d "$source_loop"
source_loop=

# Generate installation-specific host keys before Debian checks sshd config.
install -d "$root/etc/systemd/system/ssh.service.d"
cat > "$root/etc/systemd/system/ssh.service.d/10-generate-host-keys.conf" <<'SSH'
[Service]
ExecStartPre=
ExecStartPre=/usr/bin/ssh-keygen -A
ExecStartPre=/usr/sbin/sshd -t
SSH
sed -i 's/^OPENSSHD_REGENERATE_HOST_KEYS=true$/OPENSSHD_REGENERATE_HOST_KEYS=false/' \
    "$root/etc/default/armbian-firstrun"

# setupcon writes to /tmp. Wait until the boot-time tmpfiles cleanup and
# module loading have finished before checking for the HDMI framebuffer.
install -d "$root/etc/systemd/system/console-setup.service.d"
cat > "$root/etc/systemd/system/console-setup.service.d/10-w152d-boot-order.conf" <<'CONSOLE'
[Unit]
After=systemd-tmpfiles-setup.service systemd-modules-load.service
CONSOLE

release=6.12.118-ophub
driver=$work/driver
if [[ -n $kernel_bundle ]]; then
    release=6.12.119-ophub
    mkdir "$work/kernel"
    tar -xzf "$kernel_bundle" -C "$work/kernel"
    driver=$work/kernel/driver
    cp -a "$work/kernel/modules/$release" "$root/usr/lib/modules/"
    target_headers=$root/usr/src/linux-headers-$release
    mkdir "$target_headers"
    tar -xzf "$work/kernel/header-$release.tar.gz" -C "$target_headers"
    ln -sfn "/usr/src/linux-headers-$release" "$root/usr/lib/modules/$release/build"
    install -m 0644 "$work/kernel/boot/vmlinuz-$release" "$boot/zImage"
    install -m 0644 "$work/kernel/boot/uInitrd-$release" "$boot/uInitrd"
    install -m 0644 "$work/kernel/boot/"{config,System.map,initrd.img,vmlinuz}"-$release" "$boot/"

    # Keep the original low-speed DTB available for USB recovery.
    install -m 0644 "$driver/meson-gxlx4-w152d-emmc.dtb" "$boot/dtb/amlogic/meson-gxlx4-w152d-emmc-4mhz.dtb"
    dtc -@ -I dts -O dtb -o "$work/emmc-hs200.dtbo" "$repo/gpu-hdmi-driver/meson-gxlx4-w152d-emmc-hs200.dtso"
    fdtoverlay -i "$driver/meson-gxlx4-w152d-emmc.dtb" -o "$work/emmc-hs200.dtb" "$work/emmc-hs200.dtbo"
    install -m 0644 "$work/emmc-hs200.dtb" "$driver/meson-gxlx4-w152d-emmc.dtb"
fi

headers=$work/headers
cp -a "$root/usr/src/linux-headers-$release" "$headers"

# Use host-native tools for module builds and retain the original target headers.
(
    cd "$headers"
    gcc -O2 -I scripts/include -o scripts/basic/fixdep scripts/basic/fixdep.c
    gcc -O2 -I scripts/include -I scripts/mod -o scripts/mod/modpost \
        scripts/mod/{modpost,file2alias,sumversion,symsearch}.c
)
if [[ -z $kernel_bundle ]]; then
    cp -- "$repo"/gpu-hdmi-driver/{Makefile,gcc-wrap.sh,*.c,*.dts} "$driver/"
    make -C "$driver" -j"${JOBS:-4}" KDIR="$headers" \
        ARCH=arm64 CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}" all
fi

board_modules=()
cross_compile=${CROSS_COMPILE:-aarch64-linux-gnu-}
for feature in thermal cpufreq; do
    module_build=$work/$feature
    mkdir "$module_build"
    cp -- "$repo/$feature-driver/Makefile" "$repo/$feature-driver/w152d_${feature}.c" "$module_build/"
    module_cc=${cross_compile}gcc
    # Preserve the kernel flags used by the soak-tested CPUFreq build.
    if [[ $feature == thermal ]] ||
        ! "$module_cc" -fmin-function-alignment=4 -fstrict-flex-arrays=3 \
            -x c -fsyntax-only /dev/null >/dev/null 2>&1; then
        module_cc=$module_build/gcc-wrap.sh
        install -m 0755 "$repo/gpu-hdmi-driver/gcc-wrap.sh" "$module_cc"
    fi
    make -C "$module_build" -j"${JOBS:-4}" KDIR="$headers" \
        ARCH=arm64 CROSS_COMPILE="$cross_compile" CC="$module_cc"
    board_modules+=("$module_build/w152d_${feature}.ko")
done

modules=$root/usr/lib/modules/$release
install -d "$modules/extra"
for module in "$driver"/{w152d_dt_overlay,w152d_gpu_clk,w152d_drm}.ko "${board_modules[@]}"; do
    name=$(basename "$module" .ko)
    read -r vermagic < <(modinfo -F vermagic "$module")
    printf '%s vermagic: %s\n' "$name" "$vermagic"
    [[ $vermagic == "$release SMP preempt mod_unload aarch64" ]]
    install -m 0644 "$module" "$modules/extra/"
done
depmod -b "$root" "$release"
printf 'softdep lima pre: governor_simpleondemand w152d_gpu_clk w152d_drm\n' > "$root/etc/modprobe.d/w152d-gpu-hdmi.conf"
printf 'w152d_dt_overlay\nw152d_gpu_clk\nw152d_drm\nlima\n' > "$root/etc/modules-load.d/w152d-gpu-hdmi.conf"
printf 'w152d_thermal\n' > "$root/etc/modules-load.d/w152d-thermal.conf"
printf 'w152d_cpufreq\n' > "$root/etc/modules-load.d/w152d-cpufreq.conf"
cat > "$root/etc/unisoc_cp2log_config.txt" <<'CP2'
wcn_cp2_log_limit_size=1M;
wcn_cp2_file_max_num=1;
wcn_cp2_file_cover_old=true;
wcn_cp2_log_path="/dev/shm";
CP2

for name in meson-gxlx4-w152d meson-gxlx4-w152d-emmc; do
    install -m 0644 "$driver/$name.dtb" "$boot/dtb/amlogic/"
done
sed -i -E '/^APPEND=/ { /(^|[[:blank:]])console=tty1([[:blank:]]|$)/! s/$/ console=tty1/; }' "$boot/uEnv.txt"
SOURCE_DATE_EPOCH=0 mkimage -A arm -O linux -T script -C none \
    -n 'W152D HDMI EDID handoff' -d "$repo/contrib/ophub/w152d-hdmi-usb.cmd" "$boot/aml_autoscript"

sync
umount "$boot" "$root"
fsck.fat -n "${loop}p1"
e2fsck -fn "${loop}p2"
losetup -d "$loop"
loop=
pigz -n -p "${JOBS:-4}" -c -- "$work/w152d.img" > "$output.partial"
pigz -t -- "$output.partial"
mv -T -- "$output.partial" "$output"
echo "Built $output"
