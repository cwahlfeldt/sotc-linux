#!/usr/bin/env bash
# sotc (Linux): play normally while the game logs where Wander is, once a second (an engine
# automation plan of printPlayerPos lines: it moves nothing). The log (user/last_run.log) then has
# "Player Position: SetPlayerPos x y z rx ry rz" lines between the per-second "SOTC SCREEN FPS"
# lines, so the places where the frame rate drops can be read off and measured again with
# tools/sotc_temple_tour.py. Needs the engine's debug flag (RetailBuild=0), as the ride benchmark.
#   bash tools/sotc_track_play.sh [minutes, default 60] [NAME=VALUE ...]
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
minutes=${1:-60}
shift || true
for setting in "$@"; do
    [[ $setting == *=* ]] || { echo "Not NAME=VALUE: $setting" >&2; exit 2; }
    export "${setting?}"
done
plan=user/temp0/sotc_track_plan.txt
mkdir -p user/temp0
{
    echo '*stage "Track"'
    echo 'waitForGameToStart'
    for ((i = 0; i < minutes * 60; ++i)); do
        echo 'printPlayerPos'
        echo 'wait 1'
    done
    echo '*endstage'
} > "$plan"
export SOTC_FPS=1
export SOTC_EXTRA_CVARS="${SOTC_EXTRA_CVARS:-} RetailBuild=0 automate_loadfile(/temp0/sotc_track_plan.txt) automate_go"
echo "Logging Wander's position once a second for up to $minutes minutes; play as usual."
bash run.sh || true
positions=$(grep -c 'Player Position:' user/last_run.log || true)
echo "Logged $positions positions in user/last_run.log."
