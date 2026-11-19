"""Build a RAM-only Linux probe from verified W152D stock backups.

Python standard library only; does not access a device or write a flash image.
Outputs are experimental boot components, not an Armbian installation image.
"""
import os
from pathlib import Path
import gzip
import hashlib
import json
import re
import stat
import struct
import zlib

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
STOCK = Path(os.environ.get('W152D_STOCK_DIR', HERE / 'inputs/stock'))
OUT = HERE / 'out'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stock_file(name):
    p = STOCK / name
    data = p.read_bytes()
    expected = p.with_name(name + '.sha256').read_text().split()[0]
    require(sha(data) == expected, f'Stock checksum mismatch: {name}')
    return data


def align(n, page=4):
    return (n + page - 1) // page * page


def xxh32(data, seed=0):
    mask = 0xffffffff
    p1, p2, p3, p4, p5 = 2654435761, 2246822519, 3266489917, 668265263, 374761393
    def rot(x, n):
        x &= mask
        return ((x << n) | (x >> (32 - n))) & mask
    def rnd(acc, value):
        return rot(acc + value * p2, 13) * p1 & mask
    pos = 0
    if len(data) >= 16:
        lanes = [(seed + p1 + p2) & mask, (seed + p2) & mask, seed, (seed - p1) & mask]
        while pos + 16 <= len(data):
            words = struct.unpack_from('<4I', data, pos)
            lanes = [rnd(a, b) for a, b in zip(lanes, words)]
            pos += 16
        h = sum(rot(a, n) for a, n in zip(lanes, (1, 7, 12, 18))) & mask
    else:
        h = (seed + p5) & mask
    h = (h + len(data)) & mask
    while pos + 4 <= len(data):
        h = rot(h + struct.unpack_from('<I', data, pos)[0] * p3, 17) * p4 & mask
        pos += 4
    for b in data[pos:]:
        h = rot(h + b * p5, 11) * p1 & mask
    h ^= h >> 15
    h = h * p2 & mask
    h ^= h >> 13
    h = h * p3 & mask
    return h ^ (h >> 16)


def lz4_block(data, limit):
    pos, out = 0, bytearray()
    def length(value):
        nonlocal pos
        if value == 15:
            while True:
                require(pos < len(data), 'Truncated LZ4 length')
                b = data[pos]
                pos += 1
                value += b
                if b != 255:
                    break
        return value
    while pos < len(data):
        token = data[pos]
        pos += 1
        n = length(token >> 4)
        require(pos + n <= len(data), 'Truncated LZ4 literals')
        out.extend(data[pos:pos+n])
        pos += n
        if pos == len(data):
            break
        require(pos + 2 <= len(data), 'Truncated LZ4 offset')
        offset = struct.unpack_from('<H', data, pos)[0]
        pos += 2
        require(0 < offset <= len(out), 'Invalid LZ4 offset')
        n = length(token & 15) + 4
        require(len(out) + n <= limit, 'LZ4 block exceeds declared maximum')
        pattern = bytes(out[-offset:])
        out.extend((pattern * ((n + offset - 1) // offset))[:n])
    require(len(out) <= limit, 'Oversized LZ4 block')
    return bytes(out)


def lz4_frame(data):
    require(data[:4] == bytes.fromhex('04224d18'), 'Expected standard LZ4 frame')
    flg, bd = data[4:6]
    require(flg >> 6 == 1 and flg & 0x20 and not flg & 0x03, 'Unsupported LZ4 frame flags')
    pos = 6
    content_size = None
    if flg & 8:
        content_size = struct.unpack_from('<Q', data, pos)[0]
        pos += 8
    require(data[pos] == (xxh32(data[4:pos]) >> 8) & 255, 'LZ4 header checksum mismatch')
    pos += 1
    limit = {4: 65536, 5: 262144, 6: 1048576, 7: 4194304}[(bd >> 4) & 7]
    out = bytearray()
    while True:
        size = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        if size == 0:
            break
        raw = bool(size & 0x80000000)
        size &= 0x7fffffff
        require(size <= limit and pos + size <= len(data), 'Invalid LZ4 block size')
        block = data[pos:pos+size]
        pos += size
        if flg & 0x10:
            require(struct.unpack_from('<I', data, pos)[0] == xxh32(block), 'LZ4 block checksum mismatch')
            pos += 4
        out.extend(block if raw else lz4_block(block, limit))
        require(len(out) <= 128 * 1024 * 1024, 'Kernel exceeds probe size limit')
    if flg & 4:
        require(struct.unpack_from('<I', data, pos)[0] == xxh32(out), 'LZ4 content checksum mismatch')
        pos += 4
    # This stock boot.img appends a little-endian uncompressed-size word.
    tail = data[pos:]
    require(not tail or (len(tail) == 4 and struct.unpack('<I', tail)[0] == len(out)), 'Unexpected LZ4 trailing bytes')
    require(content_size is None or len(out) == content_size, 'LZ4 content length mismatch')
    return bytes(out)


def cpio_parse(data):
    pos, result = 0, {}
    while True:
        require(data[pos:pos+6] == b'070701', f'Invalid newc header at {pos}')
        fields = [int(data[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        require(namesize > 0 and pos + 110 + namesize <= len(data), 'Invalid newc name')
        name = data[pos+110:pos+110+namesize-1].decode()
        require(data[pos+110+namesize-1] == 0, 'Missing newc name terminator')
        start = align(pos + 110 + namesize)
        require(start + size <= len(data), 'Truncated newc contents')
        contents = data[start:start+size]
        pos = align(start + size)
        if name == 'TRAILER!!!':
            require(not any(data[pos:]), 'Unexpected data after newc trailer')
            return result
        require(name not in result, f'Duplicate cpio entry: {name}')
        result[name] = (fields[1], contents, fields[9], fields[10])


def cpio_build(entries):
    out = bytearray()
    for ino, (name, (mode, data, major, minor)) in enumerate(list(entries.items()) + [('TRAILER!!!', (0, b'', 0, 0))], 1):
        encoded = name.encode() + b'\0'
        fields = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        out.extend(b'070701' + ''.join(f'{x:08x}' for x in fields).encode() + encoded)
        out.extend(b'\0' * (align(len(out)) - len(out)))
        out.extend(data)
        out.extend(b'\0' * (align(len(out)) - len(out)))
    out.extend(b'\0' * (align(len(out), 512) - len(out)))
    return bytes(out)


def fdt_nodes(dtb):
    header = struct.unpack_from('>10I', dtb)
    magic, total, off_struct, off_strings, _, version, _, _, strsize, structsize = header
    require(magic == 0xd00dfeed and total == len(dtb) and version >= 17, 'Invalid FDT header')
    strings = dtb[off_strings:off_strings+strsize]
    data = dtb[off_struct:off_struct+structsize]
    pos, stack, nodes = 0, [], {}
    while pos < len(data):
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.index(0, pos)
            stack.append(data[pos:end].decode())
            pos = align(end + 1)
            nodes['/' + '/'.join(filter(None, stack))] = {}
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, offset = struct.unpack_from('>II', data, pos)
            pos += 8
            name = strings[offset:strings.index(0, offset)].decode()
            nodes['/' + '/'.join(filter(None, stack))][name] = data[pos:pos+size]
            pos = align(pos + size)
        elif token == 9:
            return nodes
        else:
            require(token == 4, 'Unexpected FDT token')
    raise ValueError('Missing FDT end token')


def main():
    OUT.mkdir(exist_ok=True)
    boot, vendor = stock_file('boot_a.img'), stock_file('vendor_boot_a.img')
    require(boot[:8] == b'ANDROID!' and struct.unpack_from('<I', boot, 40)[0] == 3, 'Expected boot v3')
    ks, rs = struct.unpack_from('<II', boot, 8)
    compressed = boot[4096:4096+ks]
    image = lz4_frame(compressed)
    require(image[56:60] == b'ARMd', 'Expected arm64 Image')
    reference = os.environ.get('W152D_REFERENCE_KERNEL')
    if reference:
        require(image == Path(reference).read_bytes(), 'Fresh extraction differs from reference kernel')
    rdstart = 4096 + align(ks, 4096)
    boot_entries = cpio_parse(gzip.decompress(boot[rdstart:rdstart+rs]))
    require(vendor[:8] == b'VNDRBOOT', 'Expected vendor_boot')
    vversion, page = struct.unpack_from('<II', vendor, 8)
    vrsize = struct.unpack_from('<I', vendor, 24)[0]
    hsize, dsize = struct.unpack_from('<II', vendor, 2096)
    require(vversion == 3 and hsize == 2112 and page == 2048, 'Unexpected vendor_boot layout')
    vrstart = align(hsize, page)
    vendor_entries = cpio_parse(gzip.decompress(vendor[vrstart:vrstart+vrsize]))
    dstart = vrstart + align(vrsize, page)
    dtb = vendor[dstart:dstart+dsize]
    nodes = fdt_nodes(dtb)
    board = nodes['/']['amlogic-dt-id'].rstrip(b'\0').decode()
    require(board == 'gxlx4_s905l4_w150d', 'Unexpected board DTB')
    busybox = boot_entries['sbin/busybox'][1]
    require(busybox[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', busybox, 18)[0] == 40, 'Expected ARM32 BusyBox')
    phoff = struct.unpack_from('<I', busybox, 28)[0]
    phsize, phnum = struct.unpack_from('<HH', busybox, 42)
    phtypes = [struct.unpack_from('<I', busybox, phoff+i*phsize)[0] for i in range(phnum)]
    require(2 not in phtypes and 3 not in phtypes, 'BusyBox must have no PT_DYNAMIC or PT_INTERP')
    marker = image.index(b'IKCFG_ST') + 8
    config = zlib.decompress(image[marker:], wbits=31)
    values = dict(re.findall(r'^(CONFIG_\w+)=(.*)$', config.decode(), re.M))
    for key in ('CONFIG_ARM64', 'CONFIG_COMPAT', 'CONFIG_BLK_DEV_INITRD', 'CONFIG_RD_GZIP', 'CONFIG_DEVTMPFS', 'CONFIG_EXT4_FS', 'CONFIG_USB_STORAGE'):
        require(values.get(key) == 'y', f'Probe prerequisite not built in: {key}')
    dep = vendor_entries['lib/modules/modules.dep'][1].decode()
    graph = {}
    for line in dep.splitlines():
        name, deps = line.split(':', 1)
        graph[Path(name).name] = [Path(x).name for x in deps.split()]
    order, visiting = [], set()
    def visit(name):
        if name in order:
            return
        require(name not in visiting and name in graph, f'Invalid module dependency: {name}')
        visiting.add(name)
        for child in graph[name]:
            visit(child)
        visiting.remove(name)
        require('lib/modules/' + name in vendor_entries, f'Missing module: {name}')
        order.append(name)
    for name in ('dwmac-meson8b.ko', 'meson-gxl.ko'):
        visit(name)
    entries = {name: (stat.S_IFDIR | 0o755, b'', 0, 0) for name in ('bin', 'dev', 'proc', 'sys', 'run', 'tmp', 'lib', 'lib/modules')}
    entries['dev/console'] = (stat.S_IFCHR | 0o600, b'', 5, 1)
    entries['dev/null'] = (stat.S_IFCHR | 0o666, b'', 1, 3)
    entries['bin/busybox'] = (stat.S_IFREG | 0o755, busybox, 0, 0)
    init = (HERE / 'src/init').read_bytes().replace(b'\r\n', b'\n')
    require(init.startswith(b'#!/bin/busybox sh\n'), 'Incorrect init interpreter')
    entries['init'] = (stat.S_IFREG | 0o755, init, 0, 0)
    entries['modules.order'] = (stat.S_IFREG | 0o644, ('\n'.join(order) + '\n').encode(), 0, 0)
    for name in order:
        entries['lib/modules/' + name] = vendor_entries['lib/modules/' + name]
    cpio = cpio_build(entries)
    ramdisk = gzip.compress(cpio, compresslevel=9, mtime=0)
    require(cpio_parse(gzip.decompress(ramdisk)) == entries, 'Generated archive round-trip mismatch')
    outputs = {'Image': image, 'stock-kernel.lz4': compressed, 'w152d-stock.dtb': dtb, 'initramfs-probe.cpio.gz': ramdisk, 'busybox-stock': busybox, 'kernel.config': config}
    for name, data in outputs.items():
        (OUT / name).write_bytes(data)
    keys = ('CONFIG_FHANDLE', 'CONFIG_SYSVIPC', 'CONFIG_DEVTMPFS_MOUNT', 'CONFIG_USER_NS', 'CONFIG_CGROUP_DEVICE', 'CONFIG_AUTOFS4_FS', 'CONFIG_STMMAC_ETH', 'CONFIG_DWMAC_MESON', 'CONFIG_MODVERSIONS')
    report = {
        'status': 'OFFLINE_VERIFIED_NOT_BOOT_TESTED',
        'board': board, 'dtb_nodes': len(nodes),
        'boot_header_version': 3, 'vendor_boot_header_version': vversion,
        'kernel_version': re.search(rb'Linux version [0-9][^\0\n]+', image).group().decode(errors='replace'),
        'sources': {name: sha(data) for name, data in [('boot_a.img', boot), ('vendor_boot_a.img', vendor)]},
        'busybox': {'source': 'stock boot ramdisk /sbin/busybox', 'arch': 'ARM32', 'static_elf': True, 'bytes': len(busybox), 'sha256': sha(busybox), 'applets_runtime_check': 'pending ADB'},
        'network_module_order': order,
        'config_checks': {k: values.get(k, 'not enabled / absent') for k in keys},
        'outputs': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in outputs.items()},
        'limits': ['No Armbian rootfs included', 'No disk mounts or writes in probe /init', 'No adbd or remote login in probe', 'Bootloader USB/booti/bootm capability not tested', 'DTB is unmodified stock, not a mainline DTB', 'No flashable boot.img generated; vendor_boot integration remains to be tested', 'Network module symbols and actual probe order need device validation'],
    }
    (OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    names = list(outputs) + ['audit.json']
    (OUT / 'SHA256SUMS').write_text(''.join(f'{sha((OUT / n).read_bytes())}  {n}\n' for n in names), encoding='ascii')
    print(json.dumps({k: report[k] for k in ('status', 'board', 'dtb_nodes', 'busybox', 'network_module_order', 'config_checks')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
