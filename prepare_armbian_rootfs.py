"""Create a RAM rootfs from the official cache, preserving owners and modes.

Uses a per-task SSH key pair and pinned host key. Never prints private keys.
The stock kernel is retained; PID 1 is explicitly experimental BusyBox init.
"""
import argparse
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import struct
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'deps'))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption, load_ssh_private_key
import build_probe


def keypair(path):
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        path.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()))
    else:
        key = load_ssh_private_key(path.read_bytes(), None)
    pub = key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    path.with_suffix('.pub').write_bytes(pub + b'\n')
    return path.read_bytes(), pub + b'\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--adb', default=os.environ.get('ADB', 'adb'))
    p.add_argument('--openssl', default=os.environ.get('OPENSSL') or shutil.which('openssl') or r'C:\Program Files\Git\usr\bin\openssl.exe')
    args = p.parse_args()
    out = HERE / 'armbian-rootfs'
    out.mkdir(exist_ok=True)
    keys = HERE / 'keys'
    keys.mkdir(exist_ok=True)
    _, client_pub = keypair(keys / 'client_ed25519')
    host_private, host_pub = keypair(keys / 'host_ed25519')
    password_hash_path = keys / 'root-password.hash'
    if not password_hash_path.exists():
        r = subprocess.run([args.openssl, 'passwd', '-6', '-stdin'], input=(secrets.token_urlsafe(48) + '\n').encode(), capture_output=True, timeout=15)
        assert r.returncode == 0 and r.stdout.strip().startswith(b'$6$'), 'Could not create a random shadow hash'
        password_hash_path.write_bytes(r.stdout.strip())
    source = json.loads((HERE / 'downloads/armbian-bookworm/source.json').read_text())
    blob = Path(source['downloaded_file'])
    assert 'sha256:' + hashlib.sha256(blob.read_bytes()).hexdigest() == source['layers'][0]['digest']
    source_tar = blob.with_suffix('')
    assert source_tar.exists(), 'Decompress the verified cache to .tar first'
    baseline = json.loads((HERE / 'network-probe/manifest.json').read_text())
    token = secrets.token_hex(16)
    config = f"PROBE_IP={baseline['ip']}\nPROBE_GATEWAY={baseline['gateway']}\nPROBE_TOKEN={token}\nRETURN_AFTER=180\nPROBE_PHASE=ARMBIAN_RAM_ROOTFS\nPORT=18080\n".encode()
    ssh_config = b'''Port 2222
ListenAddress 0.0.0.0
HostKey /etc/ssh/ssh_host_ed25519_key_w152d
PidFile /run/sshd-w152d.pid
AuthorizedKeysFile .ssh/authorized_keys
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
UsePAM no
UseDNS no
AllowUsers root
AllowTcpForwarding no
X11Forwarding no
PrintMotd no
Subsystem sftp internal-sftp
'''
    overrides = {}
    def add(name, data=b'', mode=0o644, kind=stat.S_IFREG):
        overrides[name] = (kind | mode, data, 0, 0, 0, 0)
    for directory, mode in [('root', 0o700), ('root/.ssh', 0o700), ('usr/local', 0o755), ('usr/local/bin', 0o755), ('usr/lib/modules', 0o755)]:
        add(directory, mode=mode, kind=stat.S_IFDIR)
    add('usr/local/bin/busybox', (HERE / 'out/busybox-stock').read_bytes(), 0o755)
    add('init', (HERE / 'src/init_armbian_ram').read_bytes().replace(b'\r\n', b'\n'), 0o755)
    add('status_service.sh', (HERE / 'src/status_service.sh').read_bytes().replace(b'\r\n', b'\n'), 0o755)
    add('probe.conf', config, 0o600)
    add('root/.ssh/authorized_keys', client_pub, 0o600)
    add('etc/ssh/ssh_host_ed25519_key_w152d', host_private, 0o600)
    add('etc/ssh/ssh_host_ed25519_key_w152d.pub', host_pub)
    add('etc/ssh/sshd_config_w152d', ssh_config, 0o600)
    add('etc/resolv.conf', f"nameserver {baseline['gateway']}\n".encode())
    modules = build_probe.cpio_parse(gzip.decompress((HERE / 'network-probe/initramfs.cpio.gz').read_bytes()))
    add('modules.order', modules['modules.order'][1])
    for name, entry in modules.items():
        if name.endswith('.ko'):
            add('usr/' + name, entry[1])
    meta = {'source_manifest': source['manifest_digest'], 'source_repository': source['repository'], 'kernel': 'stock W152D 5.4.210', 'init': 'experimental BusyBox /init; systemd is not PID 1', 'persistence': 'RAM only', 'ssh': 'per-task public key only, port 2222'}
    add('etc/w152d-port.json', (json.dumps(meta, indent=2) + '\n').encode())
    with tarfile.open(source_tar) as src:
        members = src.getmembers()
        indexed = {str(PurePosixPath(m.name)): m for m in members}
        for name in indexed:
            assert not name.startswith('/') and '..' not in PurePosixPath(name).parts, 'Unsafe cache path'
            for parent in PurePosixPath(name).parents:
                ancestor = indexed.get(str(parent))
                assert ancestor is None or ancestor.isdir(), 'Archive path traverses a non-directory: ' + name
        for member in members:
            if member.islnk():
                target = str(PurePosixPath(member.linkname))
                assert not target.startswith('/') and '..' not in PurePosixPath(target).parts and target in indexed, 'Unsafe hardlink'
        shadow = src.extractfile(indexed['etc/shadow']).read().decode()
        lines = shadow.splitlines()
        fields = next(line.split(':') for line in lines if line.startswith('root:'))
        fields[1] = password_hash_path.read_text().strip()
        shadow = '\n'.join(':'.join(fields) if line.startswith('root:') else line for line in lines) + '\n'
        add('etc/shadow', shadow.encode(), 0o640)
        tar_path = out / 'rootfs.tar.gz'
        with tar_path.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0, compresslevel=4) as gz, tarfile.open(fileobj=gz, mode='w|') as dst:
            for name, member in indexed.items():
                if name in ('.', '') or name in overrides:
                    continue
                info = copy.copy(member)
                info.name = name
                if info.islnk():
                    info.linkname = str(PurePosixPath(info.linkname))
                dst.addfile(info, src.extractfile(member) if member.isfile() else None)
            for name, (mode, data, uid, gid, major, minor) in overrides.items():
                info = tarfile.TarInfo(name)
                info.mode, info.uid, info.gid = stat.S_IMODE(mode), uid, gid
                info.type = tarfile.DIRTYPE if stat.S_ISDIR(mode) else tarfile.REGTYPE
                info.size = 0 if info.isdir() else len(data)
                dst.addfile(info, None if info.isdir() else io.BytesIO(data))
    print('Deployment tar created; building owner-preserving initramfs...', flush=True)
    expected = {}
    cpio_path = out / 'initramfs.cpio.gz'
    offset = 0
    with tarfile.open(tar_path) as src, cpio_path.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0, compresslevel=4) as dst:
        def emit(name, mode, uid, gid, major, minor, size, reader, ino):
            nonlocal offset
            encoded = name.encode() + b'\0'
            fields = [ino, mode, uid, gid, 1, 0, size, 0, 0, major, minor, len(encoded), 0]
            header = b'070701' + ''.join(f'{x:08x}' for x in fields).encode() + encoded
            dst.write(header)
            offset += len(header)
            pad = (-offset) % 4
            dst.write(b'\0' * pad)
            offset += pad
            hasher = hashlib.sha256()
            remaining = size
            while remaining:
                chunk = reader.read(min(remaining, 1024 * 1024))
                assert chunk, 'Truncated source file'
                dst.write(chunk)
                hasher.update(chunk)
                remaining -= len(chunk)
            offset += size
            pad = (-offset) % 4
            dst.write(b'\0' * pad)
            offset += pad
            expected[name] = (mode, uid, gid, major, minor, size, hasher.hexdigest())
        for ino, member in enumerate(src, 1):
            name = str(PurePosixPath(member.name))
            assert name not in expected
            mode = member.mode & 0o7777
            data, reader, size = None, None, 0
            if member.isfile() or member.islnk():
                target = src.getmember(member.linkname) if member.islnk() else member
                reader = src.extractfile(member)
                size = target.size
                mode |= stat.S_IFREG
            elif member.isdir():
                mode |= stat.S_IFDIR
            elif member.issym():
                data = member.linkname.encode()
                reader, size = io.BytesIO(data), len(data)
                mode |= stat.S_IFLNK
            elif member.ischr():
                mode |= stat.S_IFCHR
            elif member.isblk():
                mode |= stat.S_IFBLK
            elif member.isfifo():
                mode |= stat.S_IFIFO
            else:
                raise ValueError('Unsupported tar type: ' + name)
            emit(name, mode, member.uid, member.gid, member.devmajor, member.devminor, size, reader, ino)
        emit('TRAILER!!!', 0, 0, 0, 0, 0, 0, None, len(expected) + 1)
        dst.write(b'\0' * ((-offset) % 512))
    # Independent sequential read-back checks ownership, permissions and every byte.
    count = 0
    with gzip.open(cpio_path, 'rb') as src:
        while True:
            header = src.read(110)
            assert header[:6] == b'070701'
            f = [int(header[6+i*8:14+i*8], 16) for i in range(13)]
            name = src.read(f[11])[:-1].decode()
            src.read((-(110 + f[11])) % 4)
            h, remaining = hashlib.sha256(), f[6]
            while remaining:
                block = src.read(min(remaining, 1024 * 1024))
                assert block
                h.update(block)
                remaining -= len(block)
            src.read((-f[6]) % 4)
            assert (f[1], f[2], f[3], f[9], f[10], f[6], h.hexdigest()) == expected[name]
            count += 1
            if name == 'TRAILER!!!':
                assert not any(src.read())
                break
    manifest = {'status': 'BUILT_NOT_NATIVE_BOOT_TESTED', **meta, 'ip': baseline['ip'], 'gateway': baseline['gateway'], 'port': 18080, 'ssh_port': 2222, 'token': token, 'return_after_init_seconds': 180, 'initramfs_bytes': cpio_path.stat().st_size, 'uncompressed_cpio_bytes': offset, 'initramfs_sha256': hashlib.sha256(cpio_path.read_bytes()).hexdigest(), 'rootfs_tar_sha256': hashlib.sha256(tar_path.read_bytes()).hexdigest(), 'verified_cpio_entries': count, 'ssh_host_public_key': host_pub.decode().strip()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k != 'ssh_host_public_key'}, indent=2))


if __name__ == '__main__':
    main()
