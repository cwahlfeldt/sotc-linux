#!/usr/bin/env bash
# Builds the port (build.sh: out/bb-probe and out/gpu/libbbgpu.so) and starts Shadow of the Colossus
# through sotc.py (settings: see sotc.py).
#   bash run.sh [--software] [extra bb-probe arguments]
#   --software: Mesa's Lavapipe CPU renderer (slow; for machines without a Vulkan GPU).
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
bash build.sh
exec "$PYTHON" sotc.py "$@"
