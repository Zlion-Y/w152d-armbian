"""Run the prepared ephemeral kernel probe. Requires explicit --execute.

Disrupts ADB while running. Firmware and boot slots are not modified.
Start observe_network_probe.py before executing. Have physical power access.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
REMOTE = '/data/local/tmp/w152d-linux-probe'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--runtime-dtb', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--probe-dir', type=Path, default=HERE / 'network-probe')
    parser.add_argument('--adb', default=os.environ.get('ADB', 'adb'))
    args = parser.parse_args()
    report_path = HERE / 'evidence' / ('ram_boot_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
    manifest = json.loads((args.probe_dir / 'manifest.json').read_text(encoding='utf-8'))
    log = {'status': 'PREPARING', 'manifest': manifest, 'commands': []}

    def save():
        report_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def adb(*argv, timeout=45, allow_failure=False):
        try:
            p = subprocess.run([args.adb, '-s', args.serial, *argv], capture_output=True, timeout=timeout)
            log['commands'].append({'args': list(argv), 'returncode': p.returncode, 'stdout': p.stdout.decode(errors='replace'), 'stderr': p.stderr.decode(errors='replace')})
            save()
            assert allow_failure or p.returncode == 0, 'ADB command failed; see ' + str(report_path)
            return p
        except subprocess.TimeoutExpired as exc:
            log['commands'].append({'args': list(argv), 'timeout': True, 'stdout': (exc.stdout or b'').decode(errors='replace')})
            save()
            raise

    assert 'uid=0(root)' in adb('shell', 'id').stdout.decode()
    assert adb('shell', 'cat /sys/kernel/kexec_loaded').stdout.strip() == b'0', 'Existing target; refusing to replace it'
    log['original_boot_id'] = adb('shell', 'cat /proc/sys/kernel/random/boot_id').stdout.decode().strip()
    log['original_slot'] = adb('shell', 'getprop ro.boot.slot_suffix').stdout.decode().strip()
    current_ip = adb('shell', 'ip -4 addr show dev eth0; cat /sys/class/net/eth0/carrier').stdout.decode()
    assert 'inet ' + manifest['ip'] + '/24' in current_ip and current_ip.strip().endswith('1')
    archive = args.probe_dir / 'initramfs.cpio.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['initramfs_sha256']
    for local, name in [(HERE / 'out/Image', 'Image'), (archive, 'network-initramfs.cpio.gz'), (args.runtime_dtb, 'runtime.dtb'), (HERE / 'src/execute_ram_probe.sh', 'execute_ram_probe.sh')]:
        adb('push', str(local), REMOTE + '/' + name)
        digest = adb('shell', 'sha256sum ' + REMOTE + '/' + name).stdout.decode().split()[0]
        assert digest == hashlib.sha256(local.read_bytes()).hexdigest(), 'Transferred checksum mismatch'
    cmdline = adb('shell', 'cat /proc/cmdline').stdout.decode().replace('\r', ' ').replace('\n', ' ')
    cmdline = re.sub(r'\b(?:loglevel|panic)=[^ ]+', '', cmdline).strip() + ' loglevel=7 panic=10'
    command = f'kexec --load {REMOTE}/Image --type=Image --dtb={REMOTE}/runtime.dtb --initrd={REMOTE}/network-initramfs.cpio.gz --append=' + shlex.quote(cmdline)
    loaded_by_us = False
    try:
        adb('shell', command)
        loaded_by_us = adb('shell', 'cat /sys/kernel/kexec_loaded').stdout.strip() == b'1'
        assert loaded_by_us, 'Load not confirmed'
        log['status'] = 'LOADED_READY'
        save()
        if not args.execute:
            adb('shell', 'kexec --unload')
            loaded_by_us = False
            log['status'] = 'PREFLIGHT_LOAD_AND_UNLOAD_PASSED'
            save()
            print(log['status'], report_path)
            return
        log['status'] = 'EXECUTION_REQUESTED_WAIT_FOR_OBSERVER_AND_RECOVERY'
        save()
        print('Executing RAM probe; ADB will disconnect. Evidence:', report_path, flush=True)
        # After this command, cleanup belongs to the on-device script or new kernel.
        loaded_by_us = False
        try:
            result = adb('shell', 'sh ' + REMOTE + '/execute_ram_probe.sh', timeout=35, allow_failure=True)
            print(result.stdout.decode(errors='replace'), result.stderr.decode(errors='replace'), flush=True)
        except subprocess.TimeoutExpired:
            print('ADB execution channel timed out; inspect observer and reconnect.', flush=True)
    finally:
        if loaded_by_us:
            adb('shell', 'kexec --unload', allow_failure=True)


if __name__ == '__main__':
    main()
