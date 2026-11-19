"""Build an ephemeral Ethernet status probe with a timed firmware reboot."""
import argparse
import gzip
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import stat
import struct
import build_probe as build

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ip', required=True)
    p.add_argument('--gateway', required=True)
    p.add_argument('--return-after', type=int, default=90)
    args = p.parse_args()
    ip, gateway = ipaddress.IPv4Address(args.ip), ipaddress.IPv4Address(args.gateway)
    assert ip in ipaddress.ip_network(str(gateway) + '/24', strict=False)
    assert 45 <= args.return_after <= 180
    for line in (HERE / 'out/SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.sha256((HERE / 'out' / name).read_bytes()).hexdigest() == digest
    entries = build.cpio_parse(gzip.decompress((HERE / 'out/initramfs-probe.cpio.gz').read_bytes()))
    vendor = build.stock_file('vendor_boot_a.img')
    page = struct.unpack_from('<I', vendor, 12)[0]
    hsize = struct.unpack_from('<I', vendor, 2096)[0]
    size = struct.unpack_from('<I', vendor, 24)[0]
    start = build.align(hsize, page)
    stock = build.cpio_parse(gzip.decompress(vendor[start:start+size]))
    assert '/lib/modules/reboot.ko:' in stock['lib/modules/modules.dep'][1].decode().splitlines()
    entries['lib/modules/reboot.ko'] = stock['lib/modules/reboot.ko']
    entries['modules.order'] = (stat.S_IFREG | 0o644, entries['modules.order'][1] + b'reboot.ko\n', 0, 0)
    token = secrets.token_hex(16)
    config = f'PROBE_IP={ip}\nPROBE_GATEWAY={gateway}\nPROBE_TOKEN={token}\nRETURN_AFTER={args.return_after}\nPROBE_PHASE=NATIVE_RAM_INIT\nPORT=18080\n'.encode()
    entries['probe.conf'] = (stat.S_IFREG | 0o600, config, 0, 0)
    for source, target in [('init_network_probe', 'init'), ('status_service.sh', 'status_service.sh')]:
        entries[target] = (stat.S_IFREG | 0o755, (HERE / 'src' / source).read_bytes().replace(b'\r\n', b'\n'), 0, 0)
    archive = gzip.compress(build.cpio_build(entries), compresslevel=9, mtime=0)
    assert build.cpio_parse(gzip.decompress(archive)) == entries
    out = HERE / 'network-probe'
    out.mkdir(exist_ok=True)
    (out / 'initramfs.cpio.gz').write_bytes(archive)
    (out / 'probe.conf').write_bytes(config)
    manifest = {'status': 'READY_FOR_CONTROLLED_RAM_BOOT_NOT_EXECUTED', 'ip': str(ip), 'gateway': str(gateway), 'port': 18080, 'token': token, 'return_after_init_seconds': args.return_after, 'initramfs_bytes': len(archive), 'initramfs_sha256': hashlib.sha256(archive).hexdigest(), 'storage_mounts': False, 'remote_shell': False, 'auto_reboot_verified': False, 'limits': ['Return timer starts only after /init; early kernel hangs require a power cycle', 'Driver reinitialization after kexec is untested', 'Uses the Ethernet DHCP lease observed in Android as a temporary static address', 'Does not start systemd or an Armbian rootfs']}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
