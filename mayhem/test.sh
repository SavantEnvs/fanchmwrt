#!/usr/bin/env bash
#
# mayhem/test.sh — runs the known-answer tests for the fanchmwrt host tools built by mayhem/build.sh.
# Every check compares the tools' real output (or a file they wrote) with an exact expected value, so a
# build whose tools just exit(0) fails. Writes a CTRF report to ${CTRF_REPORT:-$SRC/ctrf-report.json}.
set -uo pipefail
[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH
: "${MAYHEM_JOBS:=$(nproc)}"   # build parallelism; env-overridable, falls back to nproc (use -j"$MAYHEM_JOBS")
cd "$SRC"

# emit_ctrf <tool> <passed> <failed> [skipped] [pending] [other]
# Writes a CTRF report (file + stdout `CTRF {...}` marker) and returns non-zero iff failed>0.
emit_ctrf() {
  local tool="$1" passed="$2" failed="$3" skipped="${4:-0}" pending="${5:-0}" other="${6:-0}"
  local tests=$(( passed + failed + skipped + pending + other ))
  cat > "${CTRF_REPORT:-$SRC/ctrf-report.json}" <<JSON
{
  "results": {
    "tool": { "name": "$tool" },
    "summary": {
      "tests": $tests,
      "passed": $passed,
      "failed": $failed,
      "pending": $pending,
      "skipped": $skipped,
      "other": $other
    }
  }
}
JSON
  printf 'CTRF {"results":{"tool":{"name":"%s"},"summary":{"tests":%d,"passed":%d,"failed":%d,"pending":%d,"skipped":%d,"other":%d}}}\n' \
    "$tool" "$tests" "$passed" "$failed" "$pending" "$skipped" "$other"
  [ "$failed" -eq 0 ]
}

# Known-answer tests over the committed fixtures (regenerate them with mayhem/gen-seeds.py): the host-side
# image tools built by mayhem/build.sh with normal flags, dynamically linked, output compared exactly.
B="$SRC/build-tests"
M="$SRC/mayhem"
[ -x "$B/fritz_tffs_read" ] || { echo "missing $B/fritz_tffs_read — mayhem/build.sh must run first" >&2; exit 1; }
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
pass=0; fail=0

# check <name> <expected> <command...>  — stdout of the command must equal <expected> exactly.
check() {
  local name="$1" want="$2"; shift 2
  local got rc
  got="$("$@" 2>"$W/stderr")"; rc=$?
  if [ "$rc" -eq 0 ] && [ "$got" == "$want" ]; then pass=$((pass + 1)); echo "PASS $name"
  else fail=$((fail + 1)); echo "FAIL $name (rc=$rc)"; echo "  want: $want"; echo "  got:  $got"; fi
}
# check_fail <name> <stderr-substring> <command...>  — must exit non-zero and say <stderr-substring>.
check_fail() {
  local name="$1" want="$2"; shift 2
  if "$@" >/dev/null 2>"$W/stderr"; then fail=$((fail + 1)); echo "FAIL $name (exit 0)"
  elif grep -qF -- "$want" "$W/stderr"; then pass=$((pass + 1)); echo "PASS $name"
  else fail=$((fail + 1)); echo "FAIL $name (stderr: $(head -c 200 "$W/stderr"))"; fi
}

# check_rc <name> <exit status> <command...>  — the command must exit with exactly that status and print nothing.
check_rc() {
  local name="$1" want="$2" out rc; shift 2
  out="$("$@" 2>/dev/null)"; rc=$?
  if [ "$rc" -eq "$want" ] && [ -z "$out" ]; then pass=$((pass + 1)); echo "PASS $name"
  else fail=$((fail + 1)); echo "FAIL $name (rc=$rc)"; fi
}

T="$M/fritz_tffs_read/testsuite"
check "tffs -a" $'firmware_version=1.2.3\nhostname=fritz.box\nwlan_key=s3cr3t-key!' "$B/fritz_tffs_read" -a -i "$T/tffs.bin"
check "tffs -l" $'firmware_version\nhostname\nwlan_key' "$B/fritz_tffs_read" -l -i "$T/tffs.bin"
check "tffs -n" "s3cr3t-key!" "$B/fritz_tffs_read" -n wlan_key -i "$T/tffs.bin"
check "tffs single" "one" "$B/fritz_tffs_read" -n only -i "$T/tffs-single.bin"
check_fail "tffs unknown key" "Unknown key name" "$B/fritz_tffs_read" -n nosuchkey -i "$T/tffs.bin"

T="$M/fritz_tffs_nand_read/testsuite"
check "nand -a" $'serial=A1B2C3\ncountry=DE\nssid=FRITZ!Box 7490' "$B/fritz_tffs_nand_read" -a -d "$T/nand.bin"
check "nand -a -o" $'serial=A1B2C3\ncountry=DE\nssid=FRITZ!Box 7490' "$B/fritz_tffs_nand_read" -a -o -d "$T/nand.bin"
check "nand -l" $'serial\ncountry\nssid' "$B/fritz_tffs_nand_read" -l -d "$T/nand.bin"
check "nand -n" "DE" "$B/fritz_tffs_nand_read" -n country -d "$T/nand.bin"
check "nand multi-segment value" "first-second" "$B/fritz_tffs_nand_read" -n long -d "$T/nand-multiseg.bin"
check_fail "nand unknown key" "Unknown key name" "$B/fritz_tffs_nand_read" -n nosuchkey -d "$T/nand.bin"

T="$M/fritz_cal_extract/testsuite"
CAL="CALIBRATION-DATA-0123456789abcdef"; CAL="$CAL$CAL$CAL$CAL"
"$B/fritz_cal_extract" -e 2 "$T/cal.bin" > "$W/cal.out" 2>/dev/null; printf %s "$CAL" > "$W/cal.want"
if cmp -s "$W/cal.out" "$W/cal.want"; then pass=$((pass + 1)); echo "PASS cal extract"; else fail=$((fail + 1)); echo "FAIL cal extract"; fi
check "cal -i -l" "RATION-DA" "$B/fritz_cal_extract" -e 2 -i 5 -l 9 "$T/cal.bin"
check "cal -r -l" "fedcba987" "$B/fritz_cal_extract" -e 2 -r -l 9 "$T/cal.bin"
check_rc "cal unknown entry" 1 "$B/fritz_cal_extract" -e 9 "$T/cal.bin"

T="$M/jboot_config_read/testsuite"
check "jboot -m" "00:11:22:33:44:55" "$B/jboot_config_read" -i "$T/jboot.bin" -m
"$B/jboot_config_read" -i "$T/jboot.bin" -e "$W/eeprom.bin" >/dev/null 2>&1; printf '\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f' > "$W/eeprom.want"
if cmp -s "$W/eeprom.bin" "$W/eeprom.want"; then pass=$((pass + 1)); echo "PASS jboot eeprom"; else fail=$((fail + 1)); echo "FAIL jboot eeprom"; fi

T="$M/bcm4908img_ls/testsuite"
check "bcm4908img info" $'bootfs offset:\t0x0\nrootfs offset:\t0x20000\nChecksum:\t0x711e191f' "$B/bcm4908img" info -i "$T/bcm4908.bin"
check "bcm4908img bootfs ls" $'cferam.000\nvmlinux.lz' "$B/bcm4908img" bootfs -i "$T/bcm4908.bin" ls
"$B/bcm4908img" extract -t bootfs -i "$T/bcm4908.bin" > "$W/boot.bin" 2>/dev/null
"$B/bcm4908img" extract -t rootfs -i "$T/bcm4908.bin" > "$W/root.bin" 2>/dev/null
check "bcm4908img rootfs" "256 UBI#" sh -c 'echo "$(wc -c < "$1") $(head -c 4 "$1")"' sh "$W/root.bin"
"$B/bcm4908img" create "$W/rebuilt.bin" -f "$W/boot.bin" -f "$W/root.bin" >/dev/null 2>&1
if cmp -s "$W/rebuilt.bin" "$T/bcm4908.bin"; then pass=$((pass + 1)); echo "PASS bcm4908img create round trip"; else fail=$((fail + 1)); echo "FAIL bcm4908img create round trip"; fi
head -c 1000 "$T/bcm4908.bin" > "$W/short.bin"
check_fail "bcm4908img rejects truncated image" "Failed to parse BCM4908 image" "$B/bcm4908img" info -i "$W/short.bin"

emit_ctrf "mayhem-kat" "$pass" "$fail" 0
