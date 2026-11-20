#!/usr/bin/env bash
# Linux / Steam Deck: builds the port (unless BB_PREBUILT=1) and starts Shadow of the Colossus
# through sotc.py, the same preparation and launch as on Windows (settings: see sotc.py).
#   bash run.sh [--software] [extra bb-probe arguments]
#   --software: Mesa's Lavapipe CPU renderer (slow; for machines without a Vulkan GPU).
# Native by default (build.sh: out/bb-probe and out/gpu/libbbgpu.so). SOTC_NATIVE=0 builds and runs
# the Windows port under Wine or Steam's Proton instead (build-linux.sh; its MSYS2 CLANG64 sysroot
# is downloaded by packaging/linux-cross/fetch_sysroot.py the first time).
# BB_PREBUILT=1 (packaged builds): the binaries are installed next to this script; nothing is built.
# BB_GAME_DIR is accepted for SOTC_GAME_DIR (the dumped game folder, default ../CUSA08809).
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ${1:-} == --software ]]; then
    shift
    if [[ -z ${VK_DRIVER_FILES:-} ]]; then
        for candidate in /run/opengl-driver/share/vulkan/icd.d/lvp_icd*.json /usr/share/vulkan/icd.d/lvp_icd*.json; do
            if [[ -f $candidate ]]; then export VK_DRIVER_FILES=$candidate; break; fi
        done
    fi
    if [[ -z ${VK_DRIVER_FILES:-} ]]; then echo 'Lavapipe not found; set VK_DRIVER_FILES.' >&2; exit 1; fi
    export VK_LOADER_LAYERS_DISABLE='~implicit~'
fi
PYTHON=${PYTHON:-$(command -v python3 || true)}
if [[ -z $PYTHON ]]; then echo 'Install Python 3 or set PYTHON.' >&2; exit 1; fi
if [[ -n ${BB_GAME_DIR:-} && -z ${SOTC_GAME_DIR:-} ]]; then export SOTC_GAME_DIR=$BB_GAME_DIR; fi
if [[ -z ${BB_PREBUILT:-} ]]; then
    if [[ ${SOTC_NATIVE:-1} == 0 ]]; then
        root=${CLANG64_ROOT:-$HOME/.cache/sotc-clang64}
        if [[ ! -d $root/clang64/include ]]; then "$PYTHON" packaging/linux-cross/fetch_sysroot.py "$root"; fi
        bash build-linux.sh
    else
        bash build.sh
    fi
fi
exec "$PYTHON" sotc.py "$@"
