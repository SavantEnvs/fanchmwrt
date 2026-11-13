# fritz_cal_extract_limit: the limited, non-reversed path of fritz_cal_extract

Run as `/mayhem/fritz_cal_extract -e 2 -s 4 -i 2 -l 64 <file>`: the same binary and seeds as
`fritz_cal_extract`, without `-r`. `-r` (or no `-l`) makes the tool refuse every stream that does not end
within the buffer, which is exactly the "partial data" path, so the two options cannot share a cmd: with `-r`
a corrupt, truncated, needs-dictionary or oversize stream stops at "Data exceeds buffer size". Here the same
streams reach `zerr()` and the limited write. No crash found by AFL so far.
