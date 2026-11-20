#!/usr/bin/env bash
# Runs inside the Steam Runtime 3 "sniper" SDK container (Debian 11, glibc 2.31; started by
# packaging/linux/build_appimage.sh): builds the native port against that glibc and assembles the
# AppImage's folder in /work/AppDir. /src is the repository (read-only), /work is out/portable on
# the host: the libraries built here and the build tree stay there between runs.
set -euo pipefail
SRC=/src WORK=/work
DEPS=$WORK/deps
export CC=gcc-14 CXX=g++-14
# GCC needs ~1.5 GB per C++ job here: BUILD_JOBS (default 10) bounds the build's memory.
mkdir -p "$DEPS/src" "$DEPS/build"

# Libraries the SDK lacks, built static (PIC) into $DEPS; Vulkan's loader, glslang, CMake and Ninja
# come from the SDK. SDL3 is built here too (shared, shipped in the package): the SDK's links X11,
# Wayland, PulseAudio, libdecor... directly, and a system without one of them could not start the
# game; this one loads every backend at run time and needs only libc and libm.
clone() { # repository tag folder
    [[ -d $DEPS/src/$3 ]] || git -c advice.detachedHead=false clone -q --depth 1 --branch "$2" "https://github.com/$1.git" "$DEPS/src/$3"
}
cmake_dep() { # folder source-subfolder extra-arguments...
    local name=$1 sub=$2; shift 2
    [[ -f $DEPS/build/$name/.installed ]] && return
    cmake -S "$DEPS/src/$name/$sub" -B "$DEPS/build/$name" -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$DEPS" -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DBUILD_SHARED_LIBS=OFF "$@" >/dev/null
    ninja -C "$DEPS/build/$name" install >/dev/null
    touch "$DEPS/build/$name/.installed"
}
clone fmtlib/fmt 12.2.1 fmt && cmake_dep fmt . -DFMT_TEST=OFF -DFMT_DOC=OFF
clone Cyan4973/xxHash v0.8.3 xxhash && cmake_dep xxhash cmake_unofficial -DXXHASH_BUILD_XXHSUM=OFF
clone Tessil/robin-map v1.4.1 robin-map && cmake_dep robin-map .
clone libsdl-org/SDL release-3.4.20 sdl3 && cmake_dep sdl3 . -DSDL_SHARED=ON -DSDL_STATIC=OFF \
    -DSDL_DEPS_SHARED=ON -DSDL_TESTS=OFF -DSDL_TEST_LIBRARY=OFF -DSDL_EXAMPLES=OFF -DSDL_INSTALL_DOCS=OFF
# Its pkg-config file would put this container's path in the loader's library search path.
sed -i 's/ -Wl,-rpath,${libdir}//; s/ -Wl,--enable-new-dtags//' "$DEPS/lib/pkgconfig/sdl3.pc"
# The Vulkan headers the port is developed against (the SDK's are 1.4.309).
clone KhronosGroup/Vulkan-Headers v1.4.363 vulkan-headers && cmake_dep vulkan-headers .
if [[ ! -f $DEPS/include/boost/version.hpp ]]; then
    curl -sSL https://archives.boost.io/release/1.87.0/source/boost_1_87_0.tar.bz2 |
        tar -xj -C "$DEPS/src" boost_1_87_0/boost
    cp -r "$DEPS/src/boost_1_87_0/boost" "$DEPS/include/"
fi

# The sources, without the host's build outputs, saves and settings (user/, sotc.ini are the
# player's and never go into a package). The build tree in $WORK/src/out is kept: incremental.
mkdir -p "$WORK/src"
tar -C "$SRC" --exclude=./out --exclude=./user --exclude=./dist --exclude=./pgo \
    --exclude=./sotc.ini --exclude=./.vscode -cf - . | tar -C "$WORK/src" -xf -
cd "$WORK/src"
export PKG_CONFIG_PATH=$DEPS/lib/pkgconfig:$DEPS/share/pkgconfig
BB_CMAKE_ARGS="-DBB_PORTABLE=ON -DBB_AVPLAYER=OFF -DCMAKE_PREFIX_PATH=$DEPS -DVulkan_INCLUDE_DIR=$DEPS/include -DBoost_INCLUDE_DIR=$DEPS/include" \
    NINJA_FLAGS="-j${BUILD_JOBS:-10} -k 0" BB_RELOCATABLE=1 bash build.sh

# The AppImage's folder: the loader with its GPU library and SDL3 (bin/, found through $ORIGIN),
# the launch scripts and the SDK's Python 3.9 (usr/), AppRun and the desktop entry.
APP=$WORK/AppDir
rm -rf "$APP"
mkdir -p "$APP/bin/gpu" "$APP/usr/bin" "$APP/usr/lib" "$APP/launcher"
strip --strip-debug -o "$APP/bin/bb-probe" out/bb-probe
strip --strip-debug -o "$APP/bin/gpu/libbbgpu.so" out/gpu/libbbgpu.so
strip --strip-debug -o "$APP/bin/gpu/libSDL3.so.0" "$(readlink -f "$DEPS/lib/libSDL3.so.0")"
cp sotc.py LICENSE "$APP/"
cp -r scripts "$APP/"
cp launcher/sotc.png "$APP/launcher/"
cp docs/sotc/README-SotC.md "$APP/README.md"
cp /usr/bin/python3.9 "$APP/usr/bin/python3"
tar -C /usr/lib --exclude='python3.9/test' --exclude='python3.9/idlelib' --exclude='python3.9/tkinter' \
    --exclude='python3.9/turtledemo' --exclude='python3.9/ensurepip' --exclude='python3.9/lib2to3' \
    --exclude='python3.9/distutils' --exclude='python3.9/pydoc_data' --exclude='python3.9/site-packages' \
    --exclude='python3.9/dist-packages' --exclude='python3.9/config-3.9-x86_64-linux-gnu' \
    -cf - python3.9 | tar -C "$APP/usr/lib" -xf -
cp packaging/linux/AppRun "$APP/AppRun"
chmod +x "$APP/AppRun"
cp packaging/linux/sotc-pc.desktop "$APP/"
cp launcher/sotc.png "$APP/sotc-pc.png"

# Portability check: nothing may need a glibc newer than this SDK's.
newest=$(for f in "$APP/bin/bb-probe" "$APP/bin/gpu/"*.so* "$APP/usr/bin/python3"; do
    objdump -T "$f" | grep -o 'GLIBC_[0-9.]*'; done | sort -V -u | tail -1)
echo "AppDir ready: newest glibc symbol $newest"
if [[ $(printf '%s\n' "$newest" GLIBC_2.31 | sort -V | tail -1) != GLIBC_2.31 ]]; then
    echo "The package needs a glibc newer than 2.31 ($newest)" >&2; exit 1
fi
