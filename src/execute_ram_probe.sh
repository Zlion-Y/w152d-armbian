#!/system/bin/sh
# Source files are all loaded before freezing. No partition writes or slot changes.
BASE=/data/local/tmp/w152d-linux-probe
BB=$BASE/busybox
ROOT=$BASE/ubuntu-base-22.04.5-arm64
LD=$ROOT/lib/ld-linux-aarch64.so.1
LIBS=$ROOT/lib/aarch64-linux-gnu:$ROOT/usr/lib/aarch64-linux-gnu
FREEZE=$ROOT/usr/sbin/fsfreeze
MOUNTS='/metadata /mnt/vendor/odm_ext /backup /mnt/vendor/cache /mnt/vendor/param /mnt/vendor/tee /data'
thaw_all() {
    for point in $MOUNTS; do
        "$LD" --library-path "$LIBS" "$FREEZE" -u "$point" 2>/dev/null
    done
}
# If a userspace preflight stalls, thaw without relying on another ADB command.
($BB sleep 25; thaw_all) &
rescue_pid=$!
cleanup() {
    kill "$rescue_pid" 2>/dev/null
    thaw_all
    kexec --unload
}
trap cleanup EXIT
echo 'Synchronizing filesystems before RAM boot'
sync
for point in $MOUNTS; do
    echo "Freezing $point"
    "$BB" timeout -t 10 "$LD" --library-path "$LIBS" "$FREEZE" -f "$point" || exit 1
done
echo 'FILESYSTEMS_FROZEN_ENTERING_KEXEC'
kexec --exec
echo 'KEXEC_RETURNED_WITHOUT_SWITCH'
exit 1
