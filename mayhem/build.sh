#!/usr/bin/env bash
#
# mayhem/build.sh — builds the fanchmwrt (OpenWrt) host-side image tools that parse untrusted files:
# fritz-tools (TFFS / TFFS-NAND / calibration extractor), jboot-tools and bcm4908img.
#   /mayhem/<tool>       AFL-instrumented, ASan+UBSan build of the tool itself (the fuzz target)
#   /mayhem/build-tests/ the same tools with normal flags, run by mayhem/test.sh
set -euo pipefail

[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH

: "${SANITIZER_FLAGS=-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer}"
: "${DEBUG_FLAGS:=-g -gdwarf-3}"
: "${CC:=clang}" ; : "${CXX:=clang++}"
: "${COVERAGE_FLAGS=}"
export SANITIZER_FLAGS DEBUG_FLAGS CC CXX COVERAGE_FLAGS

cd "$SRC"
U=package/utils
FRITZ=$U/fritz-tools/src
OUT="$SRC/build-tests"
mkdir -p "$OUT"

# AFL targets: the project's own tools, built once with afl-clang-fast; LSan is disabled at build time.
$CXX $SANITIZER_FLAGS $DEBUG_FLAGS -c mayhem/lsan_off.cc -o "$OUT/lsan_off.o"
FUZZ="afl-clang-fast $SANITIZER_FLAGS $DEBUG_FLAGS -O1"

# UBSan's alignment check is relaxed (and only it) for fritz_tffs_nand_read and jboot_config_read: they
# cast arbitrary byte offsets of their input to wider types, which x86 tolerates, and every valid image
# trips it before any real bug can be reached.
$FUZZ $FRITZ/fritz_tffs_read.c "$OUT/lsan_off.o" -o /mayhem/fritz_tffs_read
$FUZZ -fno-sanitize=alignment $FRITZ/fritz_tffs_nand_read.c mayhem/mtd_shim.c "$OUT/lsan_off.o" \
    -Wl,--wrap=ioctl -o /mayhem/fritz_tffs_nand_read
$FUZZ $FRITZ/fritz_cal_extract.c mayhem/errno_reset.c "$OUT/lsan_off.o" -lz -o /mayhem/fritz_cal_extract
$FUZZ -fno-sanitize=alignment -Wno-pointer-to-int-cast $U/jboot-tools/src/jboot_config_read.c "$OUT/lsan_off.o" -o /mayhem/jboot_config_read
$FUZZ $U/bcm4908img/src/bcm4908img.c "$OUT/lsan_off.o" -o /mayhem/bcm4908img

# Test build: normal flags, dynamically linked, no sanitizers.
T="$CC -O2 $COVERAGE_FLAGS"
$T $FRITZ/fritz_tffs_read.c -o "$OUT/fritz_tffs_read"
$T $FRITZ/fritz_tffs_nand_read.c mayhem/mtd_shim.c -Wl,--wrap=ioctl -o "$OUT/fritz_tffs_nand_read"
$T $FRITZ/fritz_cal_extract.c -lz -o "$OUT/fritz_cal_extract"
$T -Wno-pointer-to-int-cast $U/jboot-tools/src/jboot_config_read.c -o "$OUT/jboot_config_read"
$T $U/bcm4908img/src/bcm4908img.c -o "$OUT/bcm4908img"
