# fritz_tffs_read: crashes found by AFL (not guarded)

`fritz_tffs_read -a -i <file>` trusts every length and string in the TFFS image. Reproduce with the
sanitized build (`/mayhem/fritz_tffs_read -a -i <file>`):

| input | ASan report |
|---|---|
| `strlen-unterminated-name.bin` | heap-buffer-overflow in `strlen` from `parse_key_names` (`fritz_tffs_read.c:152`): a name-table string with no NUL inside the buffer |
| `print-entry-value-overread.bin` | heap-buffer-overflow in `print_entry_value` (`fritz_tffs_read.c:106`): an entry header whose `len` runs past the end of the file |
| `find-entry-header-overread.bin` | heap-buffer-overflow reading the entry header in `get_header_len` from `find_entry` (`fritz_tffs_read.c:76`): the walk only checks `pos < tffs_size` before reading a 4-byte header |

## Defects Mayhem reported, by root cause

The six defects of run 3 (the same as run 2) collapse into three causes, all in `fritz_tffs_read.c`:

1. `find_entry` reads a 4-byte entry header at `pos` after checking only `pos < tffs_size`:
   `get_header_id:84` and `get_header_len:76` (four defects, reached from the name-table search and from the
   per-key search).
2. An entry's `len` is not checked against the file size: `print_entry_value:106`.
3. A name-table string without a NUL: `parse_key_names:152`.

The extra seeds under `testsuite/` cover a missing value, empty and odd-length values, a name table with no
values, entries before the name table, twelve entries, and no name table at all. `-a` is the superset of `-l`
and `-n`; `-b` only swaps the byte order the tool reads headers with.
