#!/usr/bin/env python3
"""Regenerates the known-answer fixtures under mayhem/<target>/testsuite (asserted by test.sh)."""
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def out(target, name, data):
    d = os.path.join(HERE, target, "testsuite")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


def name_table(pairs):
    return b"".join(struct.pack("<I", i) + pad4(n.encode() + b"\0") for i, (n, _) in pairs)


# fritz_tffs_read: {u16 id, u16 len, value padded to 4} entries; id 0x01ff is the name table.
def tffs_file(pairs):
    names = name_table(pairs)
    img = struct.pack("<HH", 0x01FF, len(names)) + names
    for i, (_, v) in pairs:
        img += struct.pack("<HH", i, len(v)) + pad4(v.encode())
    return img + struct.pack("<HH", 0xFFFF, 0)


PAIRS = [(1, ("firmware_version", "1.2.3")), (2, ("hostname", "fritz.box")), (3, ("wlan_key", "s3cr3t-key!"))]
out("fritz_tffs_read", "tffs.bin", tffs_file(PAIRS))
out("fritz_tffs_read", "tffs-single.bin", tffs_file([(7, ("only", "one"))]))

# fritz_tffs_nand_read: 16 KiB erase blocks (the mtd shim's geometry) of 2 KiB sectors.
SEC, BLK = 0x800, 0x4000


def sector(eid, data, rev=1, seg=0, nxt=0):
    return (struct.pack("<IIIIII", eid, len(data), 0, rev, seg, nxt) + data).ljust(SEC, b"\xff")


def block_hdr():
    return struct.pack("<QII", 0x41564D5F54464653, 0, 2).ljust(SEC, b"\0")


def nand_image(pairs):
    secs = [sector(0x1FF, name_table(pairs))] + [sector(i, v.encode()) for i, (_, v) in pairs]
    return (block_hdr() + b"".join(secs)).ljust(BLK, b"\xff") + block_hdr().ljust(BLK, b"\xff")


NAND_PAIRS = [(1, ("serial", "A1B2C3")), (2, ("country", "DE")), (3, ("ssid", "FRITZ!Box 7490"))]
out("fritz_tffs_nand_read", "nand.bin", nand_image(NAND_PAIRS))
multi = (block_hdr() + sector(0x1FF, name_table([(1, ("long", ""))])) +
         sector(1, b"first-", seg=0, nxt=1) + sector(1, b"second", seg=1, nxt=0))
out("fritz_tffs_nand_read", "nand-multiseg.bin", multi.ljust(BLK, b"\xff"))

def cal_out(name, data):
    out("fritz_cal_extract", name, data)
    out("fritz_cal_extract_limit", name, data)


# fritz_cal_extract: {id (raw 2 bytes), len (big endian u16), payload} entries; entry 2 is a zlib stream.
CAL = b"CALIBRATION-DATA-0123456789abcdef" * 4
z = zlib.compress(CAL)
cal = b"\x00\x01\x00\x04JUNK" + b"\x00\x02" + struct.pack(">H", len(z)) + z + b"\xff\xff\x00\x00"
cal_out("cal.bin", cal)


# jboot_config_read: STAG header, CSXF header (checksummed), then data headers.
def jsum(data):
    c = 0
    for i in range(0, len(data) - 1, 2):
        c += data[i] | (data[i + 1] << 8)
        while c >> 16:
            c = (c & 0xFFFF) + (c >> 16)
    if len(data) & 1:
        c += data[-1] - 0xFF
    while c >> 16:
        c = (c & 0xFFFF) + (c >> 16)
    return c & 0xFFFF


def dhdr(i, t, payload, length=None):
    return struct.pack("<BBHH", i, t, 0x8000, len(payload) if length is None else length) + payload


EEPROM = bytes(range(16))
# The last header over-claims its length so that find_header's trailing scan stops before the end of the
# buffer (it otherwise reads past it, see known-findings/).
body = dhdr(0x30, 0x42, bytes.fromhex("001122334455")) + dhdr(0x00, 0xF5, EEPROM) + dhdr(0x10, 0x42, b"", 0x7FFF)
csxf = struct.pack("<HHIB3sI", 0x5343, 0, len(body), 0, b"\0\0\0", len(body)) + body
csxf = csxf[:2] + struct.pack("<H", ~jsum(csxf) & 0xFFFF) + csxf[4:]
stag = struct.pack("<BBHIIHH", 2, 2, 0x2B24, 0, len(csxf), 0, 0)
stag = stag[:14] + struct.pack("<H", ~jsum(stag[:14]) & 0xFFFF)
out("jboot_config_read", "jboot.bin", stag + csxf)


# bcm4908img: bootfs (JFFS2 dirents, magic 0x1985) at 0, rootfs (UBI#) at 0x20000, then the 20-byte tail
# (crc32 over everything before it).
def dirent(name):
    n = name.encode()
    hdr = struct.pack("<HHII", 0x1985, 0xE001, 40 + len(n), 0)
    return pad4(hdr + struct.pack("<IIIIBB2sII", 1, 1, 2, 0, len(n), 8, b"\0\0", 0, 0) + n)


boot = (dirent("cferam.000") + dirent("vmlinux.lz")).ljust(0x20000, b"\xff")
rootfs = (b"UBI#" + b"\x01" + bytes(range(251))).ljust(256, b"\0")
payload = boot + rootfs
crc = ~zlib.crc32(payload) & 0xFFFFFFFF  # the tool uses a raw (non-inverted) CRC32 register
img = payload + struct.pack("<IIIII", crc, 0x5732, 0x4908, 3, 2)
out("bcm4908img_ls", "bcm4908.bin", img)
out("bcm4908img_extract", "bcm4908.bin", img)


# ---------------------------------------------------------------------------------------------------
# Fuzz-only seeds (test.sh does not read them): each is a well-formed input that takes a different path
# through the tool, so AFL starts from the code behind the first validation gate instead of having to
# find it by mutation. Every seed here parses without a sanitizer report.
# ---------------------------------------------------------------------------------------------------

def jffs2_node(nodetype, body=b""):
    return pad4(struct.pack("<HHII", 0x1985, nodetype, 12 + len(body), 0) + body)


def bcm_image(boot_nodes, vendor=False, padding=False, linksys=False, root=None):
    """cferom_offset > 0 needs a chk vendor header (magic 0x2a23245e, big endian, header_len);
    the crc32 starts at cferom_offset and ends at the BCM4908 tail (before the .LINKSYS. tail)."""
    head = b""
    cferom = b""
    if vendor:
        head = (struct.pack(">II", 0x2A23245E, 0x400) + bytes(range(8)) + b"\0" * 24).ljust(0x400, b"\0")
        cferom = b"CFEROM\0".ljust(0x20000, b"\0")
    boot = b"".join(boot_nodes).ljust(0x20000, b"\xff")
    pad = b"\xff" * 0x20000 if padding else b""
    fw = cferom + boot + pad + (root or rootfs)
    crc = ~zlib.crc32(fw) & 0xFFFFFFFF
    data = head + fw + struct.pack("<IIIII", crc, 0x5732, 0x4908, 3, 2)
    if linksys:
        data += (b".LINKSYS." + b"\0" * 247)
    return data


NAMES = [dirent("a"), dirent("x" * 200), jffs2_node(0xE002, b"\0" * 20), dirent("vmlinux.lz")]
for t in ("bcm4908img_ls", "bcm4908img_extract"):
    out(t, "bcm4908-padding.bin", bcm_image(NAMES, padding=True))
    out(t, "bcm4908-vendor.bin", bcm_image(NAMES[:2], vendor=True))
    out(t, "bcm4908-linksys.bin", bcm_image(NAMES[:1], padding=True, linksys=True))


# bootfs ls walks JFFS2 nodes by `totlen` until the magic stops matching, so a node can point it at the end
# of the file. Each seed below makes it read a node, a dirent or a name that the file cuts short. The
# crc32 still holds: the cut-off nodes sit inside the rootfs bytes, which the parser only checks for the
# UBI# magic, and the bytes that run into the tail do not matter to ls.
def jump_node(frm, to):
    return struct.pack("<HHII", 0x1985, 0xE002, to - frm, 0)


def root_patch(at, data):
    return rootfs[:at] + data + rootfs[at + len(data):]


A = dirent("a")
EOF_AT = 0x20000 + 256  # tail_offset: where the 20-byte tail starts
for name, boot_target, root in (
    ("bcm4908-eof-node.bin", 0xFFFFFF00 + len(A), rootfs),
    ("bcm4908-eof-dirent.bin", EOF_AT - 8, root_patch(248, struct.pack("<HHI", 0x1985, 0xE001, 0x40))),
    ("bcm4908-eof-name.bin", EOF_AT - 32,
     root_patch(224, struct.pack("<HHI", 0x1985, 0xE001, 0x40) + bytes(20) + bytes([20]) + bytes(3))),
):
    out("bcm4908img_ls", name, bcm_image([A, jump_node(len(A), boot_target)], root=root))


# fritz_tffs_read: more name-table / entry shapes (the cmd is `-a`).
def tffs_img(names, values, junk=()):
    """names: [(id, name)], values: [(id, bytes)], junk: entries walked before the name table."""
    img = b""
    for i, v in junk:
        img += struct.pack("<HH", i, len(v)) + pad4(v)
    nt = name_table([(i, (n, None)) for i, n in names])
    img += struct.pack("<HH", 0x01FF, len(nt)) + nt
    for i, v in values:
        img += struct.pack("<HH", i, len(v)) + pad4(v)
    return img + struct.pack("<HH", 0xFFFF, 0)


out("fritz_tffs_read", "tffs-missing-value.bin",
    tffs_img([(1, "present"), (2, "absent")], [(1, b"here")]))
out("fritz_tffs_read", "tffs-odd-lengths.bin",
    tffs_img([(1, "empty"), (2, "one"), (3, "three"), (4, "five")],
             [(1, b""), (2, b"1"), (3, b"333"), (4, b"55555")]))
out("fritz_tffs_read", "tffs-no-values.bin", tffs_img([(1, "lonely")], []))
out("fritz_tffs_read", "tffs-junk-first.bin",
    tffs_img([(1, "k")], [(1, b"v")], junk=[(0x1234, b"abcdef"), (0x0007, b"")]))
out("fritz_tffs_read", "tffs-many.bin",
    tffs_img([(i, "key%02d" % i + "n" * (i % 5)) for i in range(1, 13)],
             [(i, bytes([65 + i]) * i) for i in range(1, 13)]))
out("fritz_tffs_read", "tffs-no-name-table.bin",
    struct.pack("<HH", 0x0001, 4) + b"abcd" + struct.pack("<HH", 0xFFFF, 0))


# fritz_cal_extract and fritz_cal_extract_limit (`-e 2 -s 4 -i 2 -l 64`, with and without `-r`): every seed
# starts with 4 bytes the tool seeks over; entry id 2 is the one it inflates.
def cal_img(entries, prefix=b"\xde\xad\xbe\xef", end=True):
    img = prefix
    for i, p in entries:
        img += i + struct.pack(">H", len(p)) + p
    return img + (b"\xff\xff\x00\x00" if end else b"")


CAL2 = b"\x00\x02"
cal_out("cal-skip-entries.bin",
    cal_img([(b"\x00\x01", b"JUNK"), (b"\x00\x03", b"xx"), (CAL2, z)]))
cal_out("cal-odd-length.bin", cal_img([(CAL2, zlib.compress(CAL[:33]))]))
cal_out("cal-short-payload.bin", cal_img([(CAL2, zlib.compress(b"A"))]))
cal_out("cal-oversize.bin", cal_img([(CAL2, zlib.compress(b"\0" * 140000))]))
cal_out("cal-corrupt.bin",
    cal_img([(CAL2, z[:8] + bytes(b ^ 0x55 for b in z[8:16]) + z[16:])]))
cal_out("cal-truncated.bin", cal_img([(CAL2, z[:len(z) // 2])]))
cal_out("cal-needs-dict.bin", cal_img([(CAL2, b"\x78\xbb\x00\x00\x00\x01" + z[2:])]))
cal_out("cal-no-entry.bin", cal_img([(b"\x00\x01", b"JUNK")]))
cal_out("cal-no-terminator.bin", cal_img([(b"\x00\x01", b"JUNK")], end=False))


# jboot_config_read: images whose STAG/CSXF checks all pass (a failed check makes find_header return
# EXIT_FAILURE, which main takes as a header count; see known-findings/). Every body ends with a header
# that over-claims its length, for the trailing-scan reason given above.
def jboot_img(body, prefix=b"", decoy=False):
    csxf = struct.pack("<HHIB3sI", 0x5343, 0, len(body), 0, b"\0\0\0", len(body)) + body
    csxf = csxf[:2] + struct.pack("<H", ~jsum(csxf) & 0xFFFF) + csxf[4:]
    stag = struct.pack("<BBHIIHH", 2, 2, 0x2B24, 0, len(csxf), 0, 0)
    stag = stag[:14] + struct.pack("<H", ~jsum(stag[:14]) & 0xFFFF)
    fake = (stag[:14] + b"\0\0") if decoy else b""  # same 4 magic bytes, wrong checksum: memcmp hits, checksum misses
    return prefix + fake + stag + csxf


TAIL = dhdr(0x10, 0x42, b"", 0x7FFF)
MAC = bytes.fromhex("001122334455")
out("jboot_config_read", "jboot-junk-decoy.bin",
    jboot_img(dhdr(0x30, 0x42, MAC) + dhdr(0x00, 0xF5, EEPROM) + TAIL, prefix=b"\x01\x02\x03", decoy=True))
out("jboot_config_read", "jboot-mixed-headers.bin",
    jboot_img(b"\x00\x00" + dhdr(0x31, 0x42, b"cfg") + b"\x07" + dhdr(0x30, 0x42, MAC) +
              dhdr(0x01, 0xF5, b"notcal") + struct.pack("<BBHH", 9, 0x99, 0x8000, 2) + b"zz" +
              dhdr(0x00, 0xF5, EEPROM[:8]) + TAIL))
out("jboot_config_read", "jboot-no-eeprom.bin", jboot_img(dhdr(0x30, 0x42, MAC) + TAIL))
out("jboot_config_read", "jboot-no-mac.bin", jboot_img(dhdr(0x00, 0xF5, EEPROM) + TAIL))
out("jboot_config_read", "jboot-odd-length.bin",
    jboot_img(dhdr(0x30, 0x42, MAC) + dhdr(0x00, 0xF5, EEPROM) + TAIL + b"\0"))  # odd raw_length: checksum tail byte
