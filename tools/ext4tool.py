# -*- coding: utf-8 -*-
"""极简 ext4 离线读写工具（纯 Python，直接操作 raw 镜像文件，不需要挂载/WSL）。

用途: 在 Windows 上把文件放进 system_b_mod.img / vendor_b_mod.img 这类
      Android ext4 分区镜像，不依赖 e2fsprogs / Linux / WSL。

支持: ext4 + extents + 64bit + GDT_CSUM(uninit_bg) + metadata_csum(crc32c)。

命令行:
  python ext4tool.py info <img>
  python ext4tool.py ls   <img> <path>
  python ext4tool.py stat <img> <path>
  python ext4tool.py cat  <img> <path> <out>
  python ext4tool.py put  <img> <hostfile> <path>      # 覆盖已有文件（自动扩容/收缩）
  python ext4tool.py check <img>                       # 结构自检
"""
import os
import struct
import sys

CRC32C_POLY = 0x82F63B78
_CRC_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ CRC32C_POLY if _c & 1 else _c >> 1
    _CRC_TABLE.append(_c)


def crc32c(data, crc=0xFFFFFFFF):
    t = _CRC_TABLE
    for b in data:
        crc = (crc >> 8) ^ t[(crc ^ b) & 0xFF]
    return crc & 0xFFFFFFFF


# CRC-16/ARC（poly 0xA001 反射，init 0xFFFF）= e2fsprogs 的 ext2fs_crc16，
# GDT_CSUM（uninit_bg）时代的组描述符校验和就是它，不是 crc32c。
_CRC16_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xA001 if _c & 1 else _c >> 1
    _CRC16_TABLE.append(_c)


def crc16(data, crc=0xFFFF):
    t = _CRC16_TABLE
    for b in data:
        crc = (crc >> 8) ^ t[(crc ^ b) & 0xFF]
    return crc & 0xFFFF


INCOMPAT_64BIT = 0x80
INCOMPAT_CSUM_SEED = 0x2000
RO_COMPAT_GDT_CSUM = 0x10
RO_COMPAT_METADATA_CSUM = 0x400

EXT4_EXTENTS_FL = 0x80000
EXT4_INLINE_DATA_FL = 0x10000000
EXT4_BG_INODE_UNINIT = 0x1
EXT4_BG_BLOCK_UNINIT = 0x2

S_IFDIR = 0o040000


class Ext4(object):
    def __init__(self, path, rw=False):
        self.path = path
        self.rw = rw
        self.f = open(path, "r+b" if rw else "rb")
        self.f.seek(1024)
        self.sb = bytearray(self.f.read(1024))
        assert struct.unpack_from("<H", self.sb, 0x38)[0] == 0xEF53, "not ext4"

        self.inodes_count = struct.unpack_from("<I", self.sb, 0x00)[0]
        self.blocks_count = struct.unpack_from("<I", self.sb, 0x04)[0]
        self.free_blocks = struct.unpack_from("<I", self.sb, 0x0C)[0]
        self.free_inodes = struct.unpack_from("<I", self.sb, 0x10)[0]
        self.first_data_block = struct.unpack_from("<I", self.sb, 0x14)[0]
        self.log_bs = struct.unpack_from("<I", self.sb, 0x18)[0]
        self.bs = 1024 << self.log_bs
        self.blocks_per_group = struct.unpack_from("<I", self.sb, 0x20)[0]
        self.inodes_per_group = struct.unpack_from("<I", self.sb, 0x28)[0]
        self.feat_compat = struct.unpack_from("<I", self.sb, 0x5C)[0]
        self.feat_incompat = struct.unpack_from("<I", self.sb, 0x60)[0]
        self.feat_ro = struct.unpack_from("<I", self.sb, 0x64)[0]
        self.inode_size = struct.unpack_from("<H", self.sb, 0x58)[0] or 128
        self.desc_size = 32
        if self.feat_incompat & INCOMPAT_64BIT:
            self.desc_size = struct.unpack_from("<H", self.sb, 0xFE)[0] or 64
        if self.feat_incompat & INCOMPAT_64BIT:
            self.blocks_count |= struct.unpack_from("<I", self.sb, 0x150)[0] << 32
        self.csum_seed = 0
        if self.feat_incompat & INCOMPAT_CSUM_SEED:
            self.csum_seed = struct.unpack_from("<I", self.sb, 0x270)[0]
        self.has_csum = bool(self.feat_ro & RO_COMPAT_METADATA_CSUM)
        self.has_gdt_csum = bool(self.feat_ro & RO_COMPAT_GDT_CSUM) or self.has_csum
        self.groups = ((self.blocks_count - self.first_data_block +
                        self.blocks_per_group - 1) // self.blocks_per_group)
        self.gdt_off = (self.first_data_block + 1) * self.bs
        self._gd = {}

    # ---------------------------------------------------------------- 基础 IO
    def rd(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def wr(self, off, data):
        assert self.rw
        self.f.seek(off)
        self.f.write(data)

    def blk_off(self, blk):
        return blk * self.bs

    def close(self):
        self.f.close()

    def seed(self):
        if self.csum_seed:
            return self.csum_seed
        return crc32c(bytes(self.sb[0x68:0x78]), 0xFFFFFFFF)

    # ------------------------------------------------------------ 组描述符
    def gd(self, g):
        if g in self._gd:
            return self._gd[g]
        raw = bytearray(self.rd(self.gdt_off + g * self.desc_size, self.desc_size))
        d = {
            "raw": raw,
            "block_bitmap": struct.unpack_from("<I", raw, 0x00)[0],
            "inode_bitmap": struct.unpack_from("<I", raw, 0x04)[0],
            "inode_table": struct.unpack_from("<I", raw, 0x08)[0],
            "free_blocks": struct.unpack_from("<H", raw, 0x0C)[0],
            "free_inodes": struct.unpack_from("<H", raw, 0x0E)[0],
            "used_dirs": struct.unpack_from("<H", raw, 0x10)[0],
            "flags": struct.unpack_from("<H", raw, 0x12)[0],
        }
        if self.desc_size >= 64 and (self.feat_incompat & INCOMPAT_64BIT):
            d["free_blocks"] |= struct.unpack_from("<H", raw, 0x2C)[0] << 16
            d["block_bitmap"] |= struct.unpack_from("<I", raw, 0x20)[0] << 32
            d["inode_bitmap"] |= struct.unpack_from("<I", raw, 0x24)[0] << 32
            d["inode_table"] |= struct.unpack_from("<I", raw, 0x28)[0] << 32
        self._gd[g] = d
        return d

    def _gd_checksum(self, g, raw):
        if not self.has_gdt_csum:
            return
        if self.has_csum:
            crc = crc32c(struct.pack("<I", g), self.seed())
            checked = bytearray(raw)
            checked[0x1E:0x20] = b'\0\0'
            crc = crc32c(checked, crc)
            struct.pack_into("<H", raw, 0x1E, crc & 0xFFFF)
        else:
            # GDT_CSUM：crc16(uuid) -> crc16(group) -> crc16(gd[0:0x1E])
            crc = crc16(bytes(self.sb[0x68:0x78]), 0xFFFF)
            crc = crc16(struct.pack("<I", g), crc)
            crc = crc16(bytes(raw[:0x1E]), crc)
            crc = crc16(bytes(raw[0x20:]), crc)
            struct.pack_into("<H", raw, 0x1E, crc & 0xFFFF)

    def _fill_bitmap_csum(self, g, raw):
        """只有 metadata_csum 才在位图 csum 字段记 crc32c；GDT_CSUM 下这两字段为 0。"""
        if not self.has_csum:
            return
        d = self.gd(g)
        bsz = self.blocks_per_group // 8
        isz = self.inodes_per_group // 8
        bm = self.rd(self.blk_off(d["block_bitmap"]), bsz)
        im = self.rd(self.blk_off(d["inode_bitmap"]), isz)
        bc = crc32c(bm, self.seed())
        ic = crc32c(im, self.seed())
        struct.pack_into("<H", raw, 0x18, bc & 0xFFFF)
        struct.pack_into("<H", raw, 0x1A, ic & 0xFFFF)
        if self.desc_size >= 64:
            struct.pack_into("<H", raw, 0x38, bc >> 16)
            struct.pack_into("<H", raw, 0x3A, ic >> 16)

    def flush_gd(self, g):
        d = self.gd(g)
        raw = d["raw"]
        struct.pack_into("<H", raw, 0x0C, d["free_blocks"] & 0xFFFF)
        struct.pack_into("<H", raw, 0x0E, d["free_inodes"] & 0xFFFF)
        struct.pack_into("<H", raw, 0x10, d["used_dirs"] & 0xFFFF)
        struct.pack_into("<H", raw, 0x12, d["flags"] & 0xFFFF)
        if self.desc_size >= 64:
            struct.pack_into("<H", raw, 0x2C, (d["free_blocks"] >> 16) & 0xFFFF)
        self._fill_bitmap_csum(g, raw)
        self._gd_checksum(g, raw)
        self.wr(self.gdt_off + g * self.desc_size, raw)

    # ---------------------------------------------------------------- inode
    def inode_off(self, ino):
        g = (ino - 1) // self.inodes_per_group
        idx = (ino - 1) % self.inodes_per_group
        return self.gd(g)["inode_table"] * self.bs + idx * self.inode_size, g

    def read_inode(self, ino):
        off, g = self.inode_off(ino)
        raw = bytearray(self.rd(off, self.inode_size))
        d = {
            "ino": ino, "g": g, "off": off, "raw": raw,
            "mode": struct.unpack_from("<H", raw, 0x00)[0],
            "size": struct.unpack_from("<I", raw, 0x04)[0] |
                    (struct.unpack_from("<I", raw, 0x6C)[0] << 32),
            "atime": struct.unpack_from("<I", raw, 0x08)[0],
            "ctime": struct.unpack_from("<I", raw, 0x0C)[0],
            "mtime": struct.unpack_from("<I", raw, 0x10)[0],
            "links": struct.unpack_from("<H", raw, 0x1A)[0],
            "blocks512": struct.unpack_from("<I", raw, 0x1C)[0],
            "flags": struct.unpack_from("<I", raw, 0x20)[0],
        }
        d["is_dir"] = (d["mode"] & 0xF000) == S_IFDIR
        return d

    def _inode_checksum(self, d):
        if not self.has_csum:
            return
        raw = d["raw"]
        gen = struct.unpack_from("<I", raw, 0x64)[0]
        crc = crc32c(struct.pack("<II", d["ino"], gen), self.seed())
        checked = bytearray(raw)
        checked[0x7C:0x7E] = b'\0\0'
        has_high = self.inode_size >= 0x84 and struct.unpack_from('<H', raw, 0x80)[0] >= 4
        if has_high:
            checked[0x82:0x84] = b'\0\0'
        crc = crc32c(checked, crc)
        struct.pack_into("<H", raw, 0x7C, crc & 0xFFFF)
        if has_high:
            struct.pack_into("<H", raw, 0x82, crc >> 16)

    def write_inode(self, d):
        raw = d["raw"]
        struct.pack_into("<H", raw, 0x00, d["mode"])
        struct.pack_into("<I", raw, 0x04, d["size"] & 0xFFFFFFFF)
        struct.pack_into("<I", raw, 0x6C, (d["size"] >> 32) & 0xFFFFFFFF)
        struct.pack_into("<I", raw, 0x08, d["atime"])
        struct.pack_into("<I", raw, 0x0C, d["ctime"])
        struct.pack_into("<I", raw, 0x10, d["mtime"])
        struct.pack_into("<H", raw, 0x1A, d["links"])
        struct.pack_into("<I", raw, 0x1C, d["blocks512"])
        struct.pack_into("<I", raw, 0x20, d["flags"])
        self._inode_checksum(d)
        self.wr(d["off"], raw)

    # ------------------------------------------------------------- extent
    def extents(self, ino_d):
        out = []
        stack = [(bytes(ino_d["raw"][0x28:0x28 + 60]), 0, 0)]
        while stack:
            buf, base, depth_lvl = stack.pop(0)
            if struct.unpack_from("<H", buf, base)[0] != 0xF30A:
                continue
            magic, entries, maxe, depth = struct.unpack_from("<HHHH", buf, base)
            for i in range(entries):
                o = base + 12 + i * 12
                if depth == 0:
                    ee_block, ee_len, hi, lo = struct.unpack_from("<IHHI", buf, o)
                    length = ee_len & 0x7FFF
                    out.append((ee_block, (hi << 32) | lo, length))
                else:
                    ei_block, leaf_lo, leaf_hi = struct.unpack_from("<IIH", buf, o)
                    if depth_lvl < 4:
                        stack.append((self.rd(self.blk_off((leaf_hi << 32) | leaf_lo),
                                              self.bs), 0, depth_lvl + 1))
        out.sort()
        return out

    def block_list(self, ino_d):
        out = []
        for lb, pb, ln in self.extents(ino_d):
            for i in range(ln):
                out.append((lb + i, pb + i))
        out.sort()
        return [pb for _, pb in out]

    def read_file(self, ino_d):
        size = ino_d["size"]
        if ino_d["flags"] & EXT4_INLINE_DATA_FL:
            raise RuntimeError("inline data not supported: ino %d" % ino_d["ino"])
        buf = bytearray(size)
        for lb, pb, ln in self.extents(ino_d):
            start = lb * self.bs
            if start >= size:
                continue
            data = self.rd(self.blk_off(pb), min(ln * self.bs, size - start))
            buf[start:start + len(data)] = data
        return bytes(buf[:size])

    # ---------------------------------------------------------------- 目录
    def listdir(self, ino_d):
        data = self.read_file(ino_d)
        ents = []
        off = 0
        while off + 8 <= len(data):
            ino, rec_len, name_len, ftype = struct.unpack_from("<IHBB", data, off)
            if rec_len < 8 or off + rec_len > len(data):
                break
            if ino:
                name = data[off + 8:off + 8 + name_len].decode("utf-8", "replace")
                if name not in (".", ".."):
                    ents.append((name, ino, ftype))
            off += rec_len
        return ents

    def lookup(self, path):
        cur = self.read_inode(2)
        for p in [x for x in path.strip("/").split("/") if x]:
            if not cur["is_dir"]:
                return None
            found = None
            for name, ino, ft in self.listdir(cur):
                if name == p:
                    found = ino
                    break
            if found is None:
                return None
            cur = self.read_inode(found)
        return cur

    # ------------------------------------------------------------- 位图/分配
    def _bitmap_bytes(self, g):
        d = self.gd(g)
        return d["block_bitmap"], bytearray(
            self.rd(self.blk_off(d["block_bitmap"]), self.blocks_per_group // 8))

    def _bit_get(self, bm, i):
        return (bm[i >> 3] >> (i & 7)) & 1

    def _bit_set(self, bm, i, val):
        if val:
            bm[i >> 3] |= 1 << (i & 7)
        else:
            bm[i >> 3] &= ~(1 << (i & 7)) & 0xFF

    def find_run(self, n, hint=0):
        """找连续 n 个空闲块，优先从 hint 开始向后找；返回起始块号或 None。"""
        for g in range(self.groups):
            d = self.gd(g)
            if d["free_blocks"] < n:
                continue
            start = self.first_data_block + g * self.blocks_per_group
            end = min(start + self.blocks_per_group, self.blocks_count)
            bmblk, bm = self._bitmap_bytes(g)
            lo = max(start, hint) if hint else start
            i = lo - start
            limit = end - start
            run = 0
            run_start = -1
            while i < limit:
                if not self._bit_get(bm, i):
                    if run == 0:
                        run_start = i
                    run += 1
                    if run == n:
                        return start + run_start
                else:
                    run = 0
                i += 1
        return None

    def mark_run(self, start, n, used):
        """把 [start, start+n) 标记为已用/空闲，同步位图、组计数、超级块计数。"""
        end = start + n
        while start < end:
            g = (start - self.first_data_block) // self.blocks_per_group
            d = self.gd(g)
            gstart = self.first_data_block + g * self.blocks_per_group
            gend = min(gstart + self.blocks_per_group, self.blocks_count)
            chunk = min(end, gend) - start
            bmblk, bm = self._bitmap_bytes(g)
            for i in range(start - gstart, start - gstart + chunk):
                self._bit_set(bm, i, 1 if used else 0)
            self.wr(self.blk_off(bmblk), bytes(bm))
            # 位图一旦被改写，UNINIT 标记必须清掉，否则内核会当成全空
            if used:
                d["flags"] &= ~EXT4_BG_BLOCK_UNINIT
            d["free_blocks"] += (-chunk if used else chunk)
            self.flush_gd(g)
            self.free_blocks += (-chunk if used else chunk)
            start += chunk

    def sync_sb(self):
        struct.pack_into("<I", self.sb, 0x0C, self.free_blocks & 0xFFFFFFFF)
        struct.pack_into("<I", self.sb, 0x10, self.free_inodes & 0xFFFFFFFF)
        if self.has_csum:
            c = crc32c(bytes(self.sb[0:0x3FC]), 0xFFFFFFFF)
            struct.pack_into("<I", self.sb, 0x3FC, c)
        self.wr(1024, bytes(self.sb))

    # -------------------------------------------------------------- 写文件
    def write_file(self, ino_d, data):
        bs = self.bs
        need = (len(data) + bs - 1) // bs
        old = self.block_list(ino_d)
        raw = ino_d["raw"]

        phys = list(old)
        if need > len(phys):
            extra = need - len(phys)
            hint = (phys[-1] + 1) if phys else 0
            start = self.find_run(extra, hint) if hint else None
            if start is None:
                start = self.find_run(extra, 0)
            if start is None:
                raise RuntimeError("no contiguous run of %d blocks" % extra)
            self.mark_run(start, extra, True)
            phys += [start + i for i in range(extra)]
        elif need < len(phys):
            drop = phys[need:]
            # 连续尾部一次性释放
            i = 0
            while i < len(drop):
                j = i
                while j + 1 < len(drop) and drop[j + 1] == drop[j] + 1:
                    j += 1
                self.mark_run(drop[i], j - i + 1, False)
                i = j + 1
            phys = phys[:need]

        for i in range(need):
            chunk = data[i * bs:(i + 1) * bs]
            if len(chunk) < bs:
                chunk = chunk + b"\x00" * (bs - len(chunk))
            self.wr(self.blk_off(phys[i]), chunk[:bs])

        runs = []
        for i, pb in enumerate(phys):
            if runs and runs[-1][1] + runs[-1][2] == pb:
                runs[-1][2] += 1
            else:
                runs.append([i, pb, 1])
        if len(runs) > 4:
            raise RuntimeError("fragmented into %d extents (>4), abort" % len(runs))
        struct.pack_into("<HHH", raw, 0x28, 0xF30A, len(runs), 4)
        struct.pack_into("<H", raw, 0x2E, 0)
        for i, (lb, pb, ln) in enumerate(runs):
            struct.pack_into("<IHHI", raw, 0x34 + i * 12, lb, ln, (pb >> 32) & 0xFFFF,
                             pb & 0xFFFFFFFF)
        ino_d["blocks512"] = need * (bs // 512)
        ino_d["size"] = len(data)
        ino_d["flags"] |= EXT4_EXTENTS_FL
        if need == 0:
            struct.pack_into("<HHH", raw, 0x28, 0xF30A, 0, 4)
            struct.pack_into("<H", raw, 0x2E, 0)
            ino_d["blocks512"] = 0
        self.write_inode(ino_d)
        self.sync_sb()

    # -------------------------------------------------------------- 自检
    def check(self):
        """Allocation checks plus superblock, inode and descriptor checksums.

        Not a replacement for e2fsck (directory/extent checksums are not checked).
        """
        bad = []
        if self.has_csum and crc32c(self.sb[:0x3FC]) != struct.unpack_from('<I', self.sb, 0x3FC)[0]:
            bad.append('superblock checksum mismatch')
        used = set()
        for ino in range(1, self.inodes_count + 1):
            off, g = self.inode_off(ino)
            raw = self.rd(off, self.inode_size)
            if struct.unpack_from("<H", raw, 0x00)[0] == 0:
                continue
            d = self.read_inode(ino)
            if self.has_csum and d['links']:
                self._inode_checksum(d)
                if bytes(d['raw']) != raw:
                    bad.append('inode %d checksum mismatch' % ino)
            blocks512 = struct.unpack_from("<I", raw, 0x1C)[0]
            if not blocks512:
                continue
            for pb in self.block_list(d):
                if pb in used:
                    bad.append("block %d referenced twice (ino %d)" % (pb, ino))
                used.add(pb)
        free_sum = 0
        for g in range(self.groups):
            d = self.gd(g)
            checked = bytearray(d['raw'])
            self._gd_checksum(g, checked)
            if checked != d['raw']:
                bad.append('group %d descriptor checksum mismatch' % g)
            free_sum += d["free_blocks"]
            bmblk, bm = self._bitmap_bytes(g)
            start = self.first_data_block + g * self.blocks_per_group
            end = min(start + self.blocks_per_group, self.blocks_count)
            for b in range(start, end):
                on = self._bit_get(bm, b - start)
                if on and b not in used:
                    pass  # 元数据块/间接块也算占用，不逐个校验
                if not on and b in used:
                    bad.append("block %d used by ino but free in bitmap" % b)
        if free_sum != self.free_blocks:
            bad.append("free_blocks mismatch: gdt=%d sb=%d" % (free_sum, self.free_blocks))
        return used, bad


def main():
    cmd = sys.argv[1]
    img = sys.argv[2]
    e = Ext4(img, rw=(cmd == "put"))
    try:
        if cmd == "info":
            print("bs=%d blocks=%d size=%.2f GiB groups=%d inodes=%d ipg=%d" % (
                e.bs, e.blocks_count, e.blocks_count * e.bs / float(1 << 30),
                e.groups, e.inodes_count, e.inodes_per_group))
            print("incompat=%#x ro=%#x metadata_csum=%s gdt_csum=%s desc=%d isize=%d" % (
                e.feat_incompat, e.feat_ro, e.has_csum, e.has_gdt_csum,
                e.desc_size, e.inode_size))
            print("free_blocks=%d free_inodes=%d" % (e.free_blocks, e.free_inodes))
        elif cmd == "ls":
            d = e.lookup(sys.argv[3])
            if d is None:
                print("NOT FOUND")
                return 2
            for name, ino, ft in e.listdir(d):
                c = e.read_inode(ino)
                print("%-40s ino=%-7d size=%-10d %s" % (
                    name, ino, c["size"], "DIR" if c["is_dir"] else "file"))
        elif cmd == "stat":
            d = e.lookup(sys.argv[3])
            if d is None:
                print("NOT FOUND")
                return 2
            print("ino=%d mode=%o size=%d links=%d blocks512=%d flags=%#x" % (
                d["ino"], d["mode"], d["size"], d["links"], d["blocks512"], d["flags"]))
            print("extents=%s" % e.extents(d)[:8])
        elif cmd == "cat":
            d = e.lookup(sys.argv[3])
            if d is None:
                print("NOT FOUND")
                return 2
            open(sys.argv[4], "wb").write(e.read_file(d))
            print("wrote %s (%d bytes)" % (sys.argv[4], d["size"]))
        elif cmd == "put":
            src, dst = sys.argv[3], sys.argv[4]
            data = open(src, "rb").read()
            d = e.lookup(dst)
            if d is None:
                print("NOT FOUND: %s" % dst)
                return 2
            e.write_file(d, data)
            print("wrote %d bytes -> %s (ino %d)" % (len(data), dst, d["ino"]))
        elif cmd == "check":
            used, bad = e.check()
            print("blocks referenced by inodes: %d" % len(used))
            if bad:
                print("PROBLEMS (%d):" % len(bad))
                for b in bad[:20]:
                    print("  " + b)
                return 1
            print("OK: allocation/counts and supported metadata checksums; run e2fsck for full validation")
        else:
            print("unknown cmd")
            return 2
    finally:
        e.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
