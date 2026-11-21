#!/usr/bin/env bash
# sotc: Clang profile-guided optimization of the GPU library. Builds an instrumented
# out/gpu-pgogen/libbbgpu.so, loads it in front of out/gpu's through LD_LIBRARY_PATH (bb-probe's
# RUNPATH yields to it) and trains it with tools/sotc_bench_gameplay.py --move: the menus, the
# save's load and PGO_SECONDS (default 240) of gameplay at the Shrine of Worship (needs that save).
# Then it merges the profile into pgo/bbgpu.profdata and rebuilds: build.sh uses that profile by
# default (BB_PGO=off skips it). Re-run after large GPU-side changes; functions changed since the
# profile are compiled without it.
# Measured (i5-13600KF + RX 6650 XT, Shrine gameplay): 65.5 FPS without the profile, 71.9 with it.
# Environment: SOTC_GAME_DIR (see sotc.py); SOTC_BENCH_WRAP, a command in front of the game, e.g.
# "systemd-run --user --scope --slice=sotc.slice -p MemoryHigh=12G".
set -euo pipefail
cd "$(dirname "$0")/.."
export CC=${CC:-clang} CXX=${CXX:-clang++}
[[ $("$CC" --version) == *clang* ]] || { echo 'PGO needs Clang (CC=clang)' >&2; exit 1; }
mkdir -p pgo
rm -f pgo/*.profraw
linker=(); command -v ld.lld >/dev/null && linker=(-DCMAKE_LINKER_TYPE=LLD)
cmake -S gpu -B out/gpu-pgogen -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBB_PGO=generate \
    -DBB_PGO_DIR="$PWD/pgo" -DBB_LTO=ON "${linker[@]}" ${BB_CMAKE_ARGS:-} >/dev/null
ninja -C out/gpu-pgogen bbgpu > out/gpu-pgogen-build.log 2>&1 ||
    { tail -20 out/gpu-pgogen-build.log >&2; echo 'Instrumented build failed' >&2; exit 1; }
[[ -x out/bb-probe ]] || BB_PGO=off bash build.sh
# The instrumented library writes (and merges) its profile every 30 s and at exit.
python3 tools/sotc_bench_gameplay.py --label pgo-train --move --measure "${PGO_SECONDS:-240}" \
    LD_LIBRARY_PATH="$PWD/out/gpu-pgogen${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" || true
ls pgo/*.profraw >/dev/null 2>&1 || { echo 'No profile was written (out/bench/pgo-train.log)' >&2; exit 1; }
llvm-profdata merge -o pgo/bbgpu.profdata pgo/*.profraw
rm -f pgo/*.profraw
echo "Profile: $PWD/pgo/bbgpu.profdata"
# Ninja does not track the profile file: recompile everything with the new one.
[[ -d out/gpu ]] && ninja -C out/gpu -t clean >/dev/null
bash build.sh
