#!/system/bin/sh
set -eu
umask 022
BASE=/data/local/tmp/w152d-linux-probe
ROOT=$BASE/armbian-bookworm-ram-v1
BB=$BASE/busybox
# Called using util-linux unshare --mount --propagation private.
# The old stock BusyBox's rprivate option did not reliably change propagation.
if $BB grep -q ' shared:' /proc/self/mountinfo; then
    echo 'Refusing mounts in a shared namespace' >&2
    exit 1
fi
$BB mount -t proc proc "$ROOT/proc"
$BB mount -t sysfs sysfs "$ROOT/sys"
$BB mount -t devtmpfs devtmpfs "$ROOT/dev"
$BB mkdir -p "$ROOT/dev/pts"
$BB mount -t devpts -o mode=0620,ptmxmode=0666 devpts "$ROOT/dev/pts"
$BB mount -t tmpfs -o mode=0755,size=32m tmpfs "$ROOT/run"
$BB mkdir -p "$ROOT/run/sshd"
$BB chmod 0755 "$ROOT/run/sshd"
$BB chroot "$ROOT" /usr/sbin/sshd -t -f /etc/ssh/sshd_config_w152d
$BB chroot "$ROOT" /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config_w152d &
child=$!
trap 'kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true' EXIT HUP INT TERM
echo ARMBIAN_CHROOT_SSH_READY
$BB sleep 90
