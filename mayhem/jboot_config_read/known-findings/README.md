# jboot_config_read: crashes found by AFL (not guarded)

Run as `/mayhem/jboot_config_read -m -e /dev/null -i <file>`. UBSan's `alignment` check is relaxed for
this tool: it casts arbitrary byte offsets of the input to packed-looking structs.

| input | result |
|---|---|
| `trailing-scan-overread.bin` | heap-buffer-overflow in `find_header` (`jboot_config_read.c:181`): both scan loops use `<= buf_size`, so they read past the end of the buffer. The shipped seed avoids it only because its last data header claims a length beyond the end of the file, which ends the second loop early; any other valid image, and any input without an STAG header, reads out of bounds |
| `find-header-error-used-as-count.bin` | `find_header` returns `EXIT_FAILURE` (1) on a bad CSXF magic/checksum, which `main` takes for "1 header found"; `print_mac` then dereferences the uninitialised `configs_table[0]` (`jboot_config_read.c:317`) |

## Defects Mayhem reported, by root cause

All frames are in `jboot_config_read.c`; none is in a harness. The eight defects of run 3 (the one in the
stamp) come from four causes:

1. `find_header` has no bounds on its walk. Both scan loops use `<= buf_size`, and the CSXF header is read from
   `tmp_buf + STAG_SIZE` without checking that it fits: `find_header:181` (the 4-byte `memcmp`), `:182` (the
   `tag_checksum` of a STAG candidate near the end), `:200` (the CSXF `checksum` of a header the file cuts off)
   and `:222` (the data-header read in the second loop). The first loop only exits by finding a valid STAG
   header or by running to `tmp_buf == buf + buf_size`, whose first byte is out of bounds, so every input
   without a valid STAG header crashes in it at once. The second loop has the same flaw, which is why every
   seed ends with a header that over-claims its length (see the table above).
2. `csxf->raw_length` is taken from the input and used unchecked as the checksum length, so `jboot_checksum`
   reads past the buffer: `jboot_checksum:153`, `jboot_checksum:160`.
3. A data header's `length` is unchecked when the EEPROM image is written: `write_file:294` (`fwrite` of
   `length` bytes from inside the buffer).
4. `find_header` returns `EXIT_FAILURE` (1) for a bad CSXF magic/checksum, which `main` takes for a count of
   one header: `print_mac:317`.

Four of the eight are line-level variants of cause 1.

## Why the cmd stays `-m -e /dev/null -i @@`, and what it leaves unreached

Mayhem run 3 reached 85 edges. A coverage build (`-fprofile-instr-generate -fcoverage-mapping`, normal flags)
that ran the six seeds with this cmd covers 175 of 247 lines. The rest is:

- `usage()` and the options `-o`, `-p`, `-v`, `-h`, and `print_data_header` (130-143), which only `-p` and `-v`
  reach: either option prints every data header's `length` bytes, and the last header is always one that jumps
  past the end of the buffer (the scan only ends once a header does, or it overreads in `find_header`), so it
  prints past the end. With `-p` or `-v`, every input reports an overread in `print_data_header:140` before
  anything else, and a target for them would crash on all of its seeds; `-o` only adds a `sscanf`.
- The CSXF magic and checksum failure messages (195-211): they return `EXIT_FAILURE`, which `main` takes for a
  count of one, so every input that gets there ends in the `print_mac:317` defect.
- `read_file`'s open and read failures and `write_file`'s failures: `-i @@` always names a readable file, and
  `-e /dev/null` always opens and accepts the write.
- The final fold of `jboot_checksum` (line 164): it needs an odd-length body whose running sum plus the last byte is below `0xFF`.

The seeds under `testsuite/` reach the decoy-STAG, junk-skipping, no-EEPROM, no-MAC and odd-length
(checksum tail byte) paths of `find_header`/`jboot_checksum`/`write_eeprom`/`print_mac`.
