# fritz_cal_extract: behaviour notes (no crash found by AFL so far)

- `-r` leaves the two middle bytes of an even-length payload un-swapped: `buffer_reverse(buf, datasize - 1)`
  swaps `top / 2` pairs, which covers every byte only when the length is odd. `mayhem/test.sh` therefore
  asserts only the first bytes of a reversed payload.
- `errno` is never cleared before `if (errno)` after `get_num()`, so any earlier failing libc call
  (e.g. AFL's forkserver handshake when run outside `afl-fuzz`) makes `-e`/`-s`/`-l`/`-i` fail with a
  misleading "Bad file descriptor".
  The fuzz build links `mayhem/errno_reset.c`, which runs the AFL handshake and clears errno before `main`, so the target runs
  outside `afl-fuzz` (Mayhem's smoke test) the same as under it.

## Coverage

Mayhem run 3 reached 45 edges. This is a 330-line tool with one `inflate` loop in the system, uninstrumented
`zlib`. The numbers below are from a coverage build (`-fprofile-instr-generate -fcoverage-mapping`, normal
flags) that ran the nine seeds plus `cal.bin` with the cmd `-e 2 -s 4 -i 2 -l 64 -r`: 74 of 233 regions are
missed. What is left is:

- `usage()` and every option-parsing failure (`perror` after `-s`, `-e`, `-l`, `-i`, `-o`, an unknown option, a
  missing `-e`): the cmd is fixed, so none of these runs.
- `-o` (open an output file), a missing or unreadable input file, and `fseek` failures: the cmd passes
  `@@` and no `-o`.
- `zerr()` and the write-failure branch: with `-r`, any stream that does not end inside the buffer stops at
  "Data exceeds buffer size" before `zerr()`, so corrupt, truncated and needs-dictionary streams all take that
  one branch here. They reach `zerr()` in the sibling target `fritz_cal_extract_limit` (`-l 64`, no `-r`),
  which covers the limited, non-reversed path.
- The "no `-l`" default (`limit_was_set = false`): it needs a cmd without `-l`.
- "Reached end of filesystem" after an `0xffff` entry: reachable only with `-e 0xffff`, and the cmd fixes `-e 2`.
- `inflateInit` failure and a stream read error (`Z_ERRNO`): cannot happen on a regular file.

`-e 2 -s 4 -i 2 -l 64 -r` sets every option that changes a path in the reversed run (`-e` picks the entry, `-s`
seeks, `-i` skips output bytes, `-l` bounds it, `-r` reverses), and the seeds cover the entry walk, the
`0xffff` end marker, a missing entry, an odd-length, a one-byte, a corrupt, a truncated, a needs-dictionary and a
larger-than-buffer stream.
