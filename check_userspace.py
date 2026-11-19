"""Validate Ubuntu ARM64/glibc in a private Android chroot, without rebooting.

This is a userspace compatibility check, not an Armbian install or standalone boot.
No mounts or network services are created. Requires root ADB.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
NAME = 'ubuntu-base-22.04.5-base-arm64.tar.gz'
URL = 'https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release/' + NAME
# Canonical's HTTPS SHA256SUMS, checked 2026-11-19.
EXPECTED = '075d4abd2817a5023ab0a82f5cb314c5ec0aa64a9c0b40fd3154ca3bfdae979f'
REMOTE_BASE = '/data/local/tmp/w152d-linux-probe'
ROOT = REMOTE_BASE + '/ubuntu-base-22.04.5-arm64'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial')
    parser.add_argument('--download-only', action='store_true')
    parser.add_argument('--adb', default=os.environ.get('ADB', 'adb'))
    args = parser.parse_args()
    if not args.download_only and not args.serial:
        parser.error('--serial is required for device checks')
    downloads = HERE / 'downloads'
    downloads.mkdir(exist_ok=True)
    archive = downloads / NAME
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + '.partial')
        print('Downloading official Ubuntu Base ARM64 archive...', flush=True)
        with urllib.request.urlopen(URL, timeout=30) as src, partial.open('wb') as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)
        assert hashlib.sha256(partial.read_bytes()).hexdigest() == EXPECTED, 'Downloaded checksum mismatch'
        partial.replace(archive)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == EXPECTED, 'Archive checksum mismatch'
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts, f'Unsafe archive name: {member.name}'
            if member.islnk():
                link = PurePosixPath(member.linkname)
                assert not link.is_absolute() and '..' not in link.parts, 'Unsafe hard link'
        # Do not allow extraction through an absolute or parent-relative symlink.
        outside_links = [PurePosixPath(m.name) for m in members if m.issym() and (m.linkname.startswith('/') or '..' in PurePosixPath(m.linkname).parts)]
        for member in members:
            path = PurePosixPath(member.name)
            assert not any(link in path.parents for link in outside_links), 'Archive writes through an unsafe symlink'
        indexed = {str(PurePosixPath(m.name)): m for m in members}
        bash_member = indexed.get('bin/bash') or indexed.get('usr/bin/bash')
        assert bash_member is not None, 'No bash in archive'
        bash = tar.extractfile(bash_member)
        bash_bytes = bash.read()
        elf = bash_bytes[:20]
        assert elf[:6] == b'\x7fELF\x02\x01' and elf[18:20] == b'\xb7\x00', 'Expected AArch64 bash'
    if args.download_only:
        print(f'Official archive checksum and {len(members)} archive paths: PASS')
        return
    evidence = HERE / 'evidence' / ('userspace_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
    commands = []

    def adb(*argv, allow_failure=False):
        p = subprocess.run([args.adb, '-s', args.serial, *argv], capture_output=True, timeout=60)
        commands.append({'args': list(argv), 'returncode': p.returncode, 'stdout': p.stdout.decode(errors='replace'), 'stderr': p.stderr.decode(errors='replace')})
        evidence.write_text(json.dumps({'commands': commands}, ensure_ascii=False, indent=2), encoding='utf-8')
        assert allow_failure or p.returncode == 0, 'ADB command failed; see ' + str(evidence)
        return p

    assert 'uid=0(root)' in adb('shell', 'id').stdout.decode()
    adb('push', str(archive), REMOTE_BASE + '/' + NAME)
    remote_hash = adb('shell', 'sha256sum ' + REMOTE_BASE + '/' + NAME).stdout.decode().split()[0]
    assert remote_hash == EXPECTED, 'Transferred checksum mismatch'
    exists = adb('shell', 'test -d ' + ROOT, allow_failure=True).returncode == 0
    if not exists:
        # Never overlay an existing rootfs.
        adb('shell', 'mkdir -m 0700 ' + ROOT)
        adb('shell', f'{REMOTE_BASE}/busybox tar -xzpf {REMOTE_BASE}/{NAME} -C {ROOT}')
    remote_bash = adb('shell', 'sha256sum ' + ROOT + '/bin/bash').stdout.decode().split()[0]
    assert remote_bash == hashlib.sha256(bash_bytes).hexdigest(), 'Rootfs bash does not match the verified archive'
    command = "printf 'W152D_UBUNTU_ARM64_CHROOT_OK\\n'; /usr/bin/uname -m; /usr/bin/getconf LONG_BIT; /usr/bin/getconf GNU_LIBC_VERSION; /usr/bin/dpkg --print-architecture; /bin/bash --version; /usr/bin/apt-get --version; /bin/cat /etc/os-release"
    result = adb('shell', f"{REMOTE_BASE}/busybox chroot {ROOT} /bin/bash --noprofile --norc -c \"{command}\"")
    text = result.stdout.decode()
    # uname inherits Android's PER_LINUX32 personality through the ARM32 launcher.
    # Use ELF identity, getconf, dpkg and bash's build target to establish bitness.
    assert 'W152D_UBUNTU_ARM64_CHROOT_OK' in text and 'aarch64-unknown-linux-gnu' in text and '\n64\r\n' in text and 'glibc 2.35' in text and 'arm64' in text
    summary = {'status': 'ARM64_GLIBC_CHROOT_PASSED_NOT_INDEPENDENT_BOOT', 'source_url': URL, 'sha256': EXPECTED, 'archive_entries': len(members), 'device_rootfs_path': ROOT, 'output': text, 'no_new_mounts': True, 'no_services_started': True, 'rebooted': False, 'commands': commands, 'limits': ['Ubuntu Base 22.04.5 is only a compatibility baseline, not the final Armbian rootfs', 'No systemd/udev or PID 1 tested', 'The Android kernel remains running', 'No package updates or public network service configured']}
    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(text)
    print('Evidence:', evidence)


if __name__ == '__main__':
    main()
