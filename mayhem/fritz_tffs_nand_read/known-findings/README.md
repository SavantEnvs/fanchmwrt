# fritz_tffs_nand_read: crashes and hangs found by AFL (not guarded)

Run as `/mayhem/fritz_tffs_nand_read -a -o -d <file>`; the file stands in for the MTD device through
`mayhem/mtd_shim.c` (an `ioctl` mock, 16 KiB erase blocks). Only UBSan's `alignment` check is relaxed
for this tool (it does unaligned 32/64-bit loads on every valid image).

| input | result |
|---|---|
| `sector-mark-bad-oob-write.bin` | heap-buffer-overflow (write) in `sector_mark_bad`, called from `check_block` (`fritz_tffs_nand_read.c:414`): the block header's bad-sector list holds an unchecked sector number |
| `strdup-unterminated-name.bin` | heap-buffer-overflow in `strdup` from `parse_key_names` (`fritz_tffs_nand_read.c:305`): name table without a NUL |
| `find-entry-segment-oob.bin` | heap-buffer-overflow in `find_entry` (`fritz_tffs_nand_read.c:252`): `seg` is not checked against the segment count derived from `next_seg` |
| `huge-segment-count-memset.bin` | does not finish within 10 s: `next_seg` of a segment drives a multi-gigabyte `realloc` + `memset` (`fritz_tffs_nand_read.c:248`) |

## Defects Mayhem reported, by root cause

The eight defects of run 3 (four out-of-bounds reads, three out-of-bounds writes and one incorrect
calculation) come from three causes in `fritz_tffs_nand_read.c`, none in `mtd_shim.c`:

1. `seg` of a sector header is not checked against the segment count derived from `next_seg`:
   `find_entry:252` (two reads, two writes, all at the `segments[seg].len` assignment).
2. An entry of the block header's bad-sector list is added to the sector number unchecked:
   `sector_mark_bad:82` (one read, one write, and the index calculation).
3. A name-table string without a NUL: `parse_key_names:305` (one read).

The shim only answers `ioctl`: `MEMGETINFO` with a real device's geometry (16 KiB erase blocks, 2 KiB writes,
64 bytes OOB) and `MEMREADOOB` with an error-free OOB area copied from the sector's own header. It never
touches the data the tool reads, and it cannot make an OOB area disagree with its sector, so every field that
drives the three causes above (`seg`, `next_seg`, the bad-sector list, the name table) comes from the input
file, i.e. from the flash contents on a real device. The `*.bin` files here reproduce them with the shim
unchanged.
