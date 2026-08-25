#!/bin/sh
set -eu

directory=${1:?release asset directory required}
command -v clamscan >/dev/null 2>&1 || { echo "clamscan is required" >&2; exit 1; }
test_file="${TMPDIR:-/tmp}/mgesture-eicar.$$"
trap 'rm -f "$test_file"' EXIT INT TERM
printf '%s' 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > "$test_file"
if clamscan --no-summary "$test_file" >/dev/null 2>&1; then
  echo "ClamAV did not detect EICAR; refusing to scan release" >&2
  exit 1
fi
clamscan --recursive --infected --no-summary "$directory"
