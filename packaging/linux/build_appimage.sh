#!/usr/bin/env bash
# Builds dist/SotC-PC-x86_64.AppImage: the native Linux port for any x86-64 distribution with
# glibc 2.31 or newer (2021 on; Steam Deck included). It is compiled in Valve's Steam Runtime 3
# "sniper" SDK container (packaging/linux/container_build.sh) and packed with appimagetool.
# Needs podman (or docker) and network the first time: the SDK image, a few libraries, appimagetool.
# The package holds no game files and no Sony firmware; players point it at their own dump.
#   bash packaging/linux/build_appimage.sh
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
engine=${CONTAINER_ENGINE:-$(command -v podman || command -v docker || true)}
if [[ -z $engine ]]; then echo 'Need podman (or docker): sudo pacman -S podman' >&2; exit 1; fi
image=registry.gitlab.steamos.cloud/steamrt/sniper/sdk:latest
if [[ ! -f gpu/third_party/fsr-vulkan/CMakeLists.txt || ! -f gpu/third_party/imgui/imgui.h ]]; then
    git submodule update --init --recursive
fi
mkdir -p out/portable dist
"$engine" run --rm --memory=14g -e BUILD_JOBS="${BUILD_JOBS:-10}" -v "$PWD:/src:ro" -v "$PWD/out/portable:/work" "$image" \
    bash /src/packaging/linux/container_build.sh
tool=out/portable/appimagetool-x86_64.AppImage
if [[ ! -x $tool ]]; then
    curl -sSL -o "$tool" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$tool"
fi
ARCH=x86_64 "$tool" --appimage-extract-and-run --no-appstream out/portable/AppDir dist/SotC-PC-x86_64.AppImage
echo "Built $PWD/dist/SotC-PC-x86_64.AppImage"
