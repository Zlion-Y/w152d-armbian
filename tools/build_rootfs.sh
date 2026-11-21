#!/bin/sh
# Build a new file on an existing filesystem; never formats a block device.
set -eu
BASE=${1:?base.tar.zst required}
OVERLAY=${2:?overlay.tar required}
OUTPUT=${3:?new rootfs.ext4 path required}
test "$(id -u)" = 0
test -f "$BASE"; test -f "$OVERLAY"
test ! -L "$OUTPUT"
RESUME=${4:-}
if [ -e "$OUTPUT" ]; then test "$RESUME" = --resume; fi
ROOT=$(mktemp -d /run/w152d-release.XXXXXX)
LOOP=
cleanup() {
    umount "$ROOT/etc/resolv.conf" 2>/dev/null || true
    for mountpoint in dev proc sys; do umount "$ROOT/$mountpoint" 2>/dev/null || true; done
    umount "$ROOT" 2>/dev/null || true
    test -z "$LOOP" || losetup -d "$LOOP" 2>/dev/null || true
    rmdir "$ROOT" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
if [ ! -e "$OUTPUT" ]; then
    truncate -s 2147483648 "$OUTPUT"
    mke2fs -q -F -t ext4 -b 4096 -m 0 -L W152D_ROOTFS -O '^orphan_file,^metadata_csum_seed' -E lazy_itable_init=0,lazy_journal_init=0 "$OUTPUT"
    RESUME=
fi
LOOP=$(losetup --find --show "$OUTPUT")
mount -t ext4 "$LOOP" "$ROOT"
if [ "$RESUME" = --resume ]; then
    grep -q bookworm "$ROOT/etc/os-release"
    test ! -e "$ROOT/var/lib/w152d/provisioned"
    test ! -e "$ROOT/root/.ssh/authorized_keys"
else
tar --zstd --numeric-owner -xpf "$BASE" -C "$ROOT" \
    --exclude='./etc/ssh/ssh_host_*' --exclude='etc/ssh/ssh_host_*' \
    --exclude='./root/.ssh' --exclude='root/.ssh' \
    --exclude='./root/.bash_history' --exclude='root/.bash_history' \
    --exclude='./etc/machine-id' --exclude='etc/machine-id'
fi
mkdir -p "$ROOT/dev" "$ROOT/proc" "$ROOT/sys" "$ROOT/etc/ssh" "$ROOT/usr/sbin"
printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"
chmod 755 "$ROOT/usr/sbin/policy-rc.d"
# Prevent package postinst from generating shared host private keys.
for kind in rsa ecdsa ed25519; do echo FIRST_BOOT_WILL_GENERATE_KEYS > "$ROOT/etc/ssh/ssh_host_${kind}_key"; done
rm -f "$ROOT/etc/resolv.conf"
printf 'nameserver 1.1.1.1\n' > "$ROOT/etc/resolv.conf"
rm -f "$ROOT/etc/apt/sources.list" "$ROOT/etc/apt/sources.list.d/"*.sources "$ROOT/etc/apt/sources.list.d/"*.list
cat > "$ROOT/etc/apt/sources.list.d/debian.sources" <<'EOF'
Types: deb
URIs: https://deb.debian.org/debian
Suites: bookworm bookworm-updates
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg

Types: deb
URIs: https://deb.debian.org/debian-security
Suites: bookworm-security
Components: main
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
EOF
mount --bind /dev "$ROOT/dev"
mount -t proc proc "$ROOT/proc"
mount -t sysfs -o ro sysfs "$ROOT/sys"
mount --bind /etc/resolv.conf "$ROOT/etc/resolv.conf"
printf 'Acquire::ForceIPv4 "true";\nAcquire::https::Timeout "45";\n' > "$ROOT/etc/apt/apt.conf.d/99w152d-build-ipv4"
chroot "$ROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::ForceIPv4=true -o Acquire::Languages=none -o Acquire::https::Timeout=30 -o Acquire::Retries=2 -o APT::Update::Error-Mode=any update
chroot "$ROOT" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::ForceIPv4=true -o Acquire::https::Timeout=30 -y --no-install-recommends install busybox-static chrony openssh-server openssl iproute2 iw wpasupplicant ca-certificates e2fsprogs
chroot "$ROOT" apt-get clean
rm -f "$ROOT/etc/apt/apt.conf.d/99w152d-build-ipv4"
tar --numeric-owner -xpf "$OVERLAY" -C "$ROOT"
cp "$ROOT/bin/busybox" "$ROOT/usr/local/bin/busybox"
mkdir -p "$ROOT/usr/local/libexec/w152d"
ln -sfn ../../bin/busybox "$ROOT/usr/local/libexec/w152d/busybox"
rm -f "$ROOT/etc/ssh/"ssh_host_* "$ROOT/usr/sbin/policy-rc.d"
rm -f "$ROOT/etc/machine-id" "$ROOT/var/lib/dbus/machine-id"
: > "$ROOT/etc/machine-id"
rm -rf "$ROOT/root/.ssh" "$ROOT/etc/wpa_supplicant/"* "$ROOT/var/log/"* "$ROOT/var/cache/apt/archives/"* "$ROOT/var/lib/apt/lists/"*
mkdir -p "$ROOT/root/.ssh" "$ROOT/etc/wpa_supplicant" "$ROOT/var/log" "$ROOT/var/lib/w152d" "$ROOT/usr/lib/firmware"
chmod 700 "$ROOT/root/.ssh"
umount "$ROOT/etc/resolv.conf"
ln -sfn /run/w152d-resolv.conf "$ROOT/etc/resolv.conf"
echo w152d > "$ROOT/etc/hostname"
printf '127.0.0.1 localhost w152d\n::1 localhost\n' > "$ROOT/etc/hosts"
date +%s > "$ROOT/var/lib/w152d/last-good-utc"
printf 'W152D_ARMBIAN_USB_MAINLINE_V1\n' > "$ROOT/etc/w152d-udisk"
chroot "$ROOT" dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > "$OUTPUT.packages.tsv"
if find "$ROOT/etc/ssh" "$ROOT/root/.ssh" -type f -name '*key*' -print | grep .; then
    echo 'Unexpected key in clean image' >&2; exit 1
fi
sync
cleanup
LOOP=
trap - EXIT INT TERM
e2fsck -fn "$OUTPUT"
sha256sum "$OUTPUT"
echo CLEAN_RELEASE_IMAGE_READY
