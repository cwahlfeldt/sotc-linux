#!/usr/bin/env bash
# sotc: rebuild (build.sh) and run Shadow of the Colossus once from the image sotc.py prepared in out/.
# usage: tools/sotc_run.sh [seconds] [log]   (env passes through, e.g. BB_LIST_IMPORTS=1)
set -uo pipefail
cd -- "$(dirname -- "$0")/.."
game=${SOTC_GAME_DIR:-"$(dirname "$0")/../../CUSA08809"}
log=${2:-out/run.txt}
if ! bash build.sh > out/probe-build.log 2>&1; then
    grep -E 'error|Error' out/probe-build.log | head -20; exit 1
fi
timeout "${1:-60}" out/bb-probe out/boot-linked.bin --content-profile out/content.bin --sotc-cpu out/sotc-cpu.bin --app0 "$game" --user out/user > "$log" 2>&1
echo "rc=$?"
grep -v '<Warning> vk_instance' "$log" | grep -v '^Runtime: .*=0' | tail -25
