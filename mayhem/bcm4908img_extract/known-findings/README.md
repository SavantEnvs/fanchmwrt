# bcm4908img_extract: coverage ceiling (no crash found by AFL so far)

Run as `/mayhem/bcm4908img extract -t firmware -i <file>`. Mayhem run 3 reached 63 edges. That is the ceiling
of this command, not a thin harness; the numbers below are from a coverage build (`-fprofile-instr-generate
-fcoverage-mapping`, normal flags) that ran every file in `testsuite/`, listed with `llvm-cov`.

## Why it stops there

`bcm4908img_parse` ends with a raw CRC32 over the whole image compared with the tail
(`bcm4908img.c:398`), and `extract` only runs after it returns 0. Mutating a byte of an image breaks the CRC,
so AFL's mutants stop at that line; only the seeds get past it. The tool offers no way to skip the check, and
a CRC fix-up in the harness is not allowed, so the seeds are generated with a correct CRC
(`mayhem/gen-seeds.py`): a plain image, padding between bootfs and rootfs, a `chk` vendor header with a cferom
block, a `.LINKSYS.` tail, a 200-character name, a non-dirent JFFS2 node.

## What the seeds leave unreached (function branch coverage, `-t firmware`; AFL's mutants add the failure returns)

| function | branches missed | what they are |
|---|---|---|
| `bcm4908img_create` and its three helpers | 38 of 38 | another subcommand (`create`) |
| `bcm4908img_bootfs`, `_bootfs_ls`, `_bootfs_mv` | 68 of 68 | other subcommands (`bootfs ls`, `bootfs mv`); `bootfs ls` has its own target, `bcm4908img_ls` |
| `bcm4908img_info`, `usage` | 14 of 14 | other subcommand and help text |
| `bcm4908img_calc_crc32` | 6 of 6 | only called by `bootfs mv` |
| `bcm4908img_open` | 7 of 8 | the `stdin` branches: the cmd always passes `-i` |
| `bcm4908img_parse` | 15 of 46 | `fstat`/`fseek` failure, a file shorter than 1024 bytes, and the CRC mismatch return. The short-file branches need no seed: AFL gets them by truncation |
| `bcm4908img_extract` | 15 of 34 | `-t` missing, `-t cferom`, `bootfs`, `rootfs` and an unsupported type (the cmd fixes `-t firmware`), `length == 0` and a short final read (neither can happen after a successful parse), open failure |

So `-t firmware` after a successful parse is one `fseek` and one `fread`/`fwrite` loop. The remaining
`extract` branches are the three other `-t` values, each a two-line offset calculation, which would take a
target of their own for a handful of edges. The `create`, `bootfs mv`, `bootfs ls` and `info` paths are other
subcommands. `bootfs ls` is covered by `bcm4908img_ls`; `create` and `mv` write files and are not targets.
