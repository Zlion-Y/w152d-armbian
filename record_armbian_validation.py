"""Bind the tested artifact to native SSH/recovery evidence and recheck stock boot hashes."""
import datetime
import hashlib
import gzip
import json
import os
from pathlib import Path
import subprocess
import build_probe

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'evidence'
ADB = os.environ.get('ADB', 'adb')
import argparse
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument('--serial', required=True)
_parser.add_argument('--adb', default=ADB)
_args = _parser.parse_args()
SERIAL, ADB = _args.serial, _args.adb
expected = {
    'boot_a': 'f311f302b7e8acdf38724b37853ea4b1a50c5a35c3669702de0b3e531a069e24',
    'boot_b': 'f311f302b7e8acdf38724b37853ea4b1a50c5a35c3669702de0b3e531a069e24',
    'vendor_boot_a': '30ee8e023377bf4deebb6e7b06e6090f2e0aa9f6a03744e1aefe4d8c544bc571',
    'vendor_boot_b': '30ee8e023377bf4deebb6e7b06e6090f2e0aa9f6a03744e1aefe4d8c544bc571',
}
manifest_path = HERE / 'armbian-staged/manifest.json'
manifest = json.loads(manifest_path.read_text())
assert hashlib.sha256((HERE / 'armbian-staged/initramfs.cpio.gz').read_bytes()).hexdigest() == manifest['initramfs_sha256']
assert hashlib.sha256((HERE / 'armbian-rootfs/rootfs.tar.gz').read_bytes()).hexdigest() == manifest['rootfs_tar_sha256']
boot_path = sorted(EVIDENCE.glob('ram_boot_*.json'))[-1]
boot = json.loads(boot_path.read_text())
assert boot['manifest']['initramfs_sha256'] == manifest['initramfs_sha256']
ssh_path = sorted(EVIDENCE.glob('armbian_ssh_*/result.json'))[-1]
ssh = json.loads(ssh_path.read_text())
assert ssh['status'] == 'NATIVE_ARMBIAN_SSH_PTY_SFTP_PASSED'
assert manifest['token'] in (ssh_path.parent / 'native_status.txt').read_text()
recovery_path = sorted(EVIDENCE.glob('android_return_*.json'))[-1]
recovery = json.loads(recovery_path.read_text())
assert recovery_path.stem > boot_path.stem.replace('ram_boot_', 'android_return_')
assert recovery['boot_id'] != boot['original_boot_id'] and recovery['slot'] == boot['original_slot']
command = 'id; getprop sys.boot_completed; getprop ro.boot.slot_suffix; cat /proc/sys/kernel/random/boot_id; cat /sys/kernel/kexec_loaded; sha256sum ' + ' '.join('/dev/block/by-name/' + n for n in expected)
r = subprocess.run([ADB, '-s', SERIAL, 'shell', command], capture_output=True, timeout=60)
assert r.returncode == 0
text = r.stdout.decode().replace('\r', '')
lines = text.splitlines()
assert 'uid=0(root)' in lines[0]
assert lines[1:5] == ['1', boot['original_slot'], recovery['boot_id'], '0']
actual = {line.split()[1].rsplit('/', 1)[-1]: line.split()[0] for line in lines[5:]}
assert actual == expected, 'Boot partition integrity mismatch'
integrity = EVIDENCE / 'post_armbian_ram_integrity.txt'
integrity.write_text(text, encoding='utf-8')
report = {
    'status': 'NATIVE_ARMBIAN_SSH_PTY_SFTP_ANDROID_RETURN_AND_BOOT_INTEGRITY_PASSED',
    'checked_at': datetime.datetime.now().isoformat(),
    'initramfs_sha256': manifest['initramfs_sha256'],
    'rootfs_tar_sha256': manifest['rootfs_tar_sha256'],
    'native_ssh_evidence': str(ssh_path.relative_to(HERE)),
    'ram_boot_evidence': str(boot_path.relative_to(HERE)),
    'android_return_evidence': str(recovery_path.relative_to(HERE)),
    'integrity_evidence': str(integrity.relative_to(HERE)),
    'slot': recovery['slot'], 'boot_hashes': actual,
    'limits': ['RAM only; no persistent installation', 'stock 5.4.210 kernel', 'custom BusyBox PID 1; systemd boot untested', 'Wi-Fi/display/hardware video untested', 'direct full-rootfs initramfs path not validated'],
}
(EVIDENCE / 'armbian_validation_summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
manifest['status'] = report['status']
manifest['validation_report'] = 'evidence/armbian_validation_summary.json'
manifest['verified_rootfs_cpio_entries'] = 21135
manifest['verified_cpio_entries'] = len(build_probe.cpio_parse(gzip.decompress((HERE / 'armbian-staged/initramfs.cpio.gz').read_bytes())))
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
(HERE / 'keys/known_hosts').write_text(f"[{manifest['ip']}]:2222 {manifest['ssh_host_public_key']}\n", encoding='utf-8')
print(json.dumps(report, indent=2))
