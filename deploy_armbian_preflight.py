"""Deploy into a fresh private directory and run a bounded mount-namespace SSH check."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import datetime

HERE = Path(__file__).resolve().parent
ADB = os.environ.get('ADB', 'adb')
BASE = '/data/local/tmp/w152d-linux-probe'
ROOT = BASE + '/armbian-bookworm-ram-v1'
import argparse
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument('--serial', required=True)
_parser.add_argument('--adb', default=ADB)
_args = _parser.parse_args()
SERIAL, ADB = _args.serial, _args.adb
events = []
evidence = HERE / 'evidence' / ('armbian_chroot_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')

def adb(*args, timeout=120):
    r = subprocess.run([ADB, '-s', SERIAL, *args], capture_output=True, timeout=timeout)
    events.append({'args': args, 'code': r.returncode, 'stdout': r.stdout.decode(errors='replace'), 'stderr': r.stderr.decode(errors='replace')})
    evidence.write_text(json.dumps(events, indent=2), encoding='utf-8')
    assert r.returncode == 0, str(evidence)
    return r.stdout.decode()

manifest = json.loads((HERE / 'armbian-rootfs/manifest.json').read_text())
tar = HERE / 'armbian-rootfs/rootfs.tar.gz'
assert hashlib.sha256(tar.read_bytes()).hexdigest() == manifest['rootfs_tar_sha256']
adb('shell', 'test ! -e ' + ROOT)
adb('push', str(tar), BASE + '/armbian-rootfs.tar.gz', timeout=180)
assert adb('shell', 'sha256sum ' + BASE + '/armbian-rootfs.tar.gz').split()[0] == manifest['rootfs_tar_sha256']
adb('shell', f'mkdir -m 0700 {ROOT} && {BASE}/busybox tar -xzpf {BASE}/armbian-rootfs.tar.gz -C {ROOT}', timeout=180)
adb('push', str(HERE / 'src/check_armbian_namespace.sh'), BASE + '/check_armbian_namespace.sh')
print(adb('shell', f'{BASE}/busybox chroot {ROOT} /bin/bash -c "export PATH=/usr/sbin:/usr/bin:/sbin:/bin; getconf LONG_BIT; dpkg --print-architecture; cat /etc/os-release"'), flush=True)
print('Starting bounded private namespace SSH check; use verify_armbian_ssh.py.', flush=True)
loader = f'{ROOT}/lib/ld-linux-aarch64.so.1 --library-path {ROOT}/lib/aarch64-linux-gnu:{ROOT}/usr/lib/aarch64-linux-gnu'
print(adb('shell', loader + f' {ROOT}/usr/bin/unshare --mount --propagation private /system/bin/sh ' + BASE + '/check_armbian_namespace.sh', timeout=110), flush=True)
