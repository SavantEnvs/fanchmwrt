# bcm4908img_ls: coverage ceiling (no crash found by AFL so far)

Run as `/mayhem/bcm4908img bootfs -i <file> ls`. Mayhem run 3 reached 67 edges (the new seeds below were added
after it). The numbers here are from a coverage build (`-fprofile-instr-generate -fcoverage-mapping`,
normal flags) that ran every file in `testsuite/`, listed with `llvm-cov`.

## Why it stops there

`bcm4908img_parse` ends with a raw CRC32 over the whole image compared with the tail (`bcm4908img.c:398`),
and `bcm4908img_bootfs_ls` only runs after it returns 0. A mutated image fails the CRC and AFL never reaches
the JFFS2 walk; no CRC fix-up is allowed in the harness. The seeds are therefore generated with a correct CRC
(`mayhem/gen-seeds.py`) and cover the `ls` walk: dirents, a non-dirent node (skipped by `totlen`), a
200-character name, a `chk` vendor header, padding and a `.LINKSYS.` tail.

Three seeds added after run 3 (`bcm4908-eof-*.bin`) point the walk at the end of the file, so that the node,
dirent and name reads that `ls` checks for short reads come up short. The cut-off nodes sit in the rootfs
bytes, which `parse` only checks for the `UBI#` magic, so the CRC still holds.

## What the seeds leave unreached (function branch coverage; AFL's mutants add the failure returns)

| function | branches missed | what they are |
|---|---|---|
| `bcm4908img_bootfs_ls` | 2 of 14 | `fseek` failure (the offset is a `size_t` below 2^32 plus the start, `fseek` does not fail on it) and "Too long filename" (`nsize` is a `uint8_t`, so `nsize + 1 > FILENAME_MAX + 1` is never true) |
| `bcm4908img_parse` | 15 of 46 | `fstat`/`fseek` failure, a file under 1024 bytes, the CRC mismatch return; the short-file branches need no seed |
| `bcm4908img_bootfs` | 9 of 18 | the `mv` and unknown-command branches (the cmd is fixed to `ls`), a missing `-i` or command, an open failure; the parse-failure return is taken by every mutant, so AFL covers it |
| `bcm4908img_create*`, `_extract`, `_info`, `_bootfs_mv`, `_calc_crc32`, `usage` | all | other subcommands |

Nothing reachable from `bootfs ls` after a valid parse is left. The ceiling is the size of `parse` plus a
14-branch loop. Directory nodes and other inode types add nothing: `ls` tests only the node magic and whether
`nodetype` is a dirent, so any other type takes the same `continue` as the `0xE002` node in the seeds.
