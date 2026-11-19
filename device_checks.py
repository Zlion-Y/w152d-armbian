"""Run non-booting checks over an explicitly selected, root ADB connection.

Only creates test files below /data/local/tmp/w152d-linux-probe. Does not reboot,
load a kernel, change slots, mount filesystems, or write block devices.
"""
import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
REMOTE = '/data/local/tmp/w152d-linux-probe'


def mov(reg, immediate):
    assert 0 <= immediate < 65536
    return 0xd2800000 | (immediate << 5) | reg  # movz Xd, #imm16


def elf64(code, tail=b''):
    base, offset = 0x400000, 120
    body = struct.pack('<' + 'I' * len(code), *code) + tail
    size = offset + len(body)
    ident = b'\x7fELF' + bytes([2, 1, 1]) + bytes(9)
    header = ident + struct.pack('<HHIQQQIHHHHHH', 2, 183, 1, base+offset, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    phdr = struct.pack('<IIQQQQQQ', 1, 5, 0, base, base, size, size, 4096)
    return header + phdr + body


def probes():
    # AArch64 Linux syscall numbers: write=64, exit=93, name_to_handle_at=264.
    # Reference: Linux v5.4 include/uapi/asm-generic/unistd.h.
    message = b'W152D_NATIVE_AARCH64_OK\n'
    delta = 32 - 4  # ADR is the second instruction; message follows 8 instructions.
    adr_x1 = 0x10000001 | ((delta & 3) << 29) | (((delta >> 2) & 0x7ffff) << 5)
    hello = elf64([mov(0, 1), adr_x1, mov(2, len(message)), mov(8, 64), 0xd4000001, mov(0, 0), mov(8, 93), 0xd4000001], message)
    # NULL pathname must return EFAULT if implemented, ENOSYS if unavailable.
    # This call does not open, mount, or modify anything. Return errno as exit code.
    handle = elf64([mov(i, 0) for i in range(5)] + [mov(8, 264), 0xd4000001, 0xcb0003e0, mov(8, 93), 0xd4000001])
    return {'native64-check': hello, 'fhandle-check': handle}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--adb', default=os.environ.get('ADB', 'adb'))
    args = parser.parse_args()
    evidence = HERE / 'evidence' / ('device_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    evidence.mkdir(parents=True)
    records = []

    def adb(*argv, expected=0):
        p = subprocess.run([args.adb, '-s', args.serial, *argv], capture_output=True, timeout=45)
        records.append({'args': list(argv), 'returncode': p.returncode, 'stdout': p.stdout.decode(errors='replace'), 'stderr': p.stderr.decode(errors='replace')})
        (evidence / 'commands.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        if expected is not None and p.returncode != expected:
            raise RuntimeError(f'ADB command failed ({p.returncode}): {argv}; see {evidence}')
        return p

    assert 'uid=0(root)' in adb('shell', 'id').stdout.decode(), 'Run adb root first'
    adb('shell', 'mkdir -p ' + REMOTE)
    adb('push', str(HERE / 'out/busybox-stock'), REMOTE + '/busybox')
    adb('shell', 'chmod 0755 ' + REMOTE + '/busybox')
    bb = REMOTE + '/busybox'
    listing = adb('shell', bb + ' --list').stdout.decode().splitlines()
    required = {'sh', 'mount', 'mkdir', 'cat', 'insmod', 'ip', 'uname', 'sleep', 'chroot', 'cpio', 'gzip', 'tar'}
    assert required <= set(listing), 'Missing BusyBox applets: ' + repr(required - set(listing))
    (evidence / 'busybox-applets.txt').write_text('\n'.join(listing) + '\n', encoding='utf-8')
    binaries = probes()
    for name, data in binaries.items():
        local = evidence / name
        local.write_bytes(data)
        adb('push', str(local), REMOTE + '/' + name)
        adb('shell', 'chmod 0755 ' + REMOTE + '/' + name)
    native = adb('shell', REMOTE + '/native64-check')
    assert native.stdout.strip() == b'W152D_NATIVE_AARCH64_OK', native.stdout
    fhandle = adb('shell', REMOTE + '/fhandle-check', expected=None)
    assert fhandle.returncode in (14, 38), 'Unexpected syscall probe result'
    config_gz = adb('exec-out', 'cat /proc/config.gz').stdout
    (evidence / 'runtime.config.gz').write_bytes(config_gz)
    config = gzip.decompress(config_gz)
    (evidence / 'runtime.config').write_bytes(config)
    same_config = config == (HERE / 'out/kernel.config').read_bytes()
    assert same_config, 'Runtime config differs from stock kernel evidence'
    fdt = adb('exec-out', 'cat /sys/firmware/fdt').stdout
    assert fdt[:4] == bytes.fromhex('d00dfeed')
    (evidence / 'runtime.dtb').write_bytes(fdt)
    slotinfo = adb('shell', 'getprop ro.boot.slot_suffix; for slot in 0 1; do bootctl is-slot-bootable $slot; echo slot_${slot}_bootable_rc=$?; bootctl is-slot-marked-successful $slot; echo slot_${slot}_successful_rc=$?; done').stdout.decode()
    hashes = adb('shell', 'sha256sum /dev/block/by-name/boot_a /dev/block/by-name/boot_b /dev/block/by-name/vendor_boot_a /dev/block/by-name/vendor_boot_b').stdout.decode()
    expected_hashes = json.loads((HERE / 'out/audit.json').read_text(encoding='utf-8'))['sources']
    partition_matches = {}
    for line in hashes.splitlines():
        digest, path = line.split()
        name = path.rsplit('/', 1)[-1]
        original = ('vendor_boot_a.img' if name.startswith('vendor_boot') else 'boot_a.img')
        partition_matches[name] = digest == expected_hashes[original]
    assert len(partition_matches) == 4 and all(partition_matches.values())
    modules = adb('shell', 'cat /proc/modules').stdout.decode()
    (evidence / 'runtime.modules').write_text(modules, encoding='utf-8')
    module_names = {line.split()[0] for line in modules.splitlines()}
    dependency_order = json.loads((HERE / 'out/audit.json').read_text(encoding='utf-8'))['network_module_order']
    module_loaded = {n: n[:-3].replace('-', '_') in module_names for n in dependency_order}
    kexec = adb('shell', 'cat /proc/sys/kernel/kexec_load_disabled; cat /sys/kernel/kexec_loaded; cat /proc/meminfo | head -n 3; kexec --version').stdout.decode()
    sdio = adb('shell', 'cat /sys/bus/sdio/devices/*/uevent').stdout.decode()
    summary = {
        'status': 'ANDROID_RUNTIME_CHECKS_PASSED_NOT_INDEPENDENT_BOOT',
        'busybox_required_applets': 'PASS', 'busybox_applet_count': len(listing),
        'native_aarch64_execution': 'PASS (static ELF, no Android or glibc dependency)',
        'name_to_handle_at_errno': fhandle.returncode,
        'name_to_handle_at_result': 'ENOSYS: syscall unavailable' if fhandle.returncode == 38 else 'EFAULT: syscall implemented',
        'runtime_config_equals_stock': same_config,
        'boot_partitions_equal_stock': partition_matches,
        'slot_state': slotinfo,
        'network_dependencies_already_loaded': module_loaded,
        'kexec_read_only_info': kexec,
        'sdio_runtime_info': sdio,
        'probe_sha256': {n: hashlib.sha256(d).hexdigest() for n, d in binaries.items()},
        'limits': ['Not a standalone Linux boot', 'No kexec load or execute performed', 'No block-device writes or slot changes', 'Full Armbian rootfs/systemd not tested'],
    }
    (evidence / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('Evidence:', evidence)


if __name__ == '__main__':
    main()
