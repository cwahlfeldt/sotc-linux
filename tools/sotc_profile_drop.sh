#!/usr/bin/env bash
# sotc (Linux): profiles where the FPS drops while you simply play. Starts the game (run.sh, your
# settings) with the profilers armed; they start by themselves the first time the game stays below
# PROFILE_FPS (default 52) for 5 s in a row after the first 30 s, and record 20 s: the draw
# thread's hot spots (or another thread's) and every thread's CPU time. Play near the slow spot
# for a minute or two after it drops, then quit; the report is printed and kept in user/.
#   bash tools/sotc_profile_drop.sh [thread name part, default shadPS4:GpuDraw]
#   PROFILE_FPS=45 bash tools/sotc_profile_drop.sh        (another threshold)
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
thread=${1:-shadPS4:GpuDraw}
name=${thread//[^A-Za-z0-9]/_}
out=$PWD/user/prof-$name.txt
report=$PWD/user/prof-$name.report.txt
rm -f "$out" "$report"
export SOTC_FPS=1 SOTC_THREAD_TIMES=1 SOTC_PROFILE="$thread" SOTC_PROFILE_OUT="$out" \
    SOTC_PROFILE_DELAY=30 SOTC_PROFILE_SECONDS=20 \
    SOTC_PROFILE_TRIGGER_FPS="${PROFILE_FPS:-52}" SOTC_PROFILE_TRIGGER_S=5
echo "Profiling $thread: it starts by itself after 5 s below $SOTC_PROFILE_TRIGGER_FPS FPS."
bash run.sh || true
if [[ -s $out ]]; then
    python3 tools/profile_functions.py "$out" out/gpu/libbbgpu.so 60 --inlines --qualified | tee "$report"
    echo "Kept: $out, $report and user/last_run.log"
else
    echo "No profile: the game never stayed below $SOTC_PROFILE_TRIGGER_FPS FPS for 5 s after the" \
         "first 30 s, or it was closed less than 20 s after that." >&2
fi
