"""Start the known small network init first, then unpack the large rootfs in userspace."""
import gzip
import hashlib
import json
from pathlib import Path
import stat
import build_probe

HERE = Path(__file__).resolve().parent
out = HERE / 'armbian-staged'
out.mkdir(exist_ok=True)
root = json.loads((HERE / 'armbian-rootfs/manifest.json').read_text())
entries = build_probe.cpio_parse(gzip.decompress((HERE / 'network-probe/initramfs.cpio.gz').read_bytes()))
for source, target in [('src/init_armbian_staged', 'init'), ('src/status_service.sh', 'status_service.sh'), ('armbian-rootfs/rootfs.tar.gz', 'armbian-rootfs.tar.gz')]:
    entries[target] = (stat.S_IFREG | (0o755 if target.endswith('.sh') or target == 'init' else 0o600), (HERE / source).read_bytes(), 0, 0)
entries['probe.conf'] = (stat.S_IFREG | 0o600, f"PROBE_IP={root['ip']}\nPROBE_GATEWAY={root['gateway']}\nPROBE_TOKEN={root['token']}\nPROBE_PHASE=ARMBIAN_BOOTSTRAP\nRETURN_AFTER=180\nPORT=18080\n".encode(), 0, 0)
raw = build_probe.cpio_build(entries)
# The embedded rootfs is already compressed; store the outer layer so kernel
# extraction mainly copies it and network observation can start promptly.
archive = gzip.compress(raw, compresslevel=0, mtime=0)
assert build_probe.cpio_parse(gzip.decompress(archive)) == entries
(out / 'initramfs.cpio.gz').write_bytes(archive)
manifest = {**root, 'status': 'STAGED_BOOT_READY_NOT_TESTED', 'layout': 'small network bootstrap then RAM extraction and switch_root', 'initramfs_sha256': hashlib.sha256(archive).hexdigest(), 'initramfs_bytes': len(archive), 'uncompressed_cpio_bytes': len(raw)}
manifest['verified_rootfs_cpio_entries'] = manifest.pop('verified_cpio_entries')
manifest['verified_cpio_entries'] = len(entries)
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest, indent=2))
