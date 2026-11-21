# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Native Linux port of PS4 *Shadow of the Colossus* (CUSA08809 EU 1.01 and CUSA08034 US 1.00, the same
eboot build; GPU workarounds gate on `ElfInfo::IsSotc()`, never on one serial). Not an emulator: the game's
own x86-64 code runs directly on the host CPU, a C loader/runtime implements the PS4 system functions
it imports, and a vendored shadPS4 video core translates the PS4 GPU (GCN command streams + shaders)
to Vulkan/SPIR-V. Forked from bloodborne_pc ("bbport"): engine names (`bb-probe`, `bbgpu`, `bb_setjmp`,
`BB_*` env vars, `bbport_*` sources) are kept from it; the Bloodborne-only files were removed. The
Shadow of the Colossus path is `build.sh` / `run.sh` / `sotc.py`.

**Linux only.** The project began as a Windows port; its Windows builds, the Windows launcher
(`SotC.exe`), the Wine/Proton cross build and the AppImage packaging were removed on purpose: one
build environment, the native `build.sh`. Do not bring any of them back unless asked. The sources
still contain `#ifdef _WIN32` code (src/, gpu/shim, gpu/sotc, compat_win.c, vendored shadPS4) that
nothing builds; game fixes go into the Linux paths.

No game files or Sony firmware are in the repo, and none may be added. Running the game needs a local
dump (`SOTC_GAME_DIR`, default `../CUSA08809`) and, for sound, the user's own
`libSceNgs2.sprx`/`libSceUlt.sprx` (`SOTC_SYS_MODULES`).

User-facing docs (README, CHANGELOG, `docs/sotc/*`) are written in Portuguese (README also has
English). Code comments are English.

## Build / run / test

```bash
bash build.sh             # out/bb-probe (loader, C) + out/gpu/libbbgpu.so (GPU library, CMake+Ninja in out/gpu)
                          # build errors: out/gpu-build.log. Clang + lld when present; ThinLTO by default
                          # (BB_LTO=OFF disables); Clang PGO from pgo/bbgpu.profdata when present (BB_PGO=off skips)
bash run.sh               # build.sh, then sotc.py (also `make play`); --software: Lavapipe
python3 sotc.py           # prepare image + run game (settings: env or sotc.ini, see sotc.py docstring)
bash tools/pgo_train.sh   # instrumented build + gameplay training -> pgo/bbgpu.profdata, rebuild
```

`build.sh` inits submodules (`gpu/third_party/*`, `third_party/LibAtrac9`) on first run;
dependencies come from pkg-config (Vulkan, SDL3, X11, xxhash, FFmpeg unless
`BB_CMAKE_ARGS=-DBB_AVPLAYER=OFF`); Zydis and VMA are fetched by CMake when not installed; NixOS
uses `shell.nix`. The fault handling (`src/probe.c`, `#ifndef _WIN32`: heap guard SIGTRAP hook,
null-object skips, copy guard, helper reads, SSE4a fallback) is where game fixes go. Diagnostic:
`SOTC_WATCH_ADDR=a,b` (hardware write watchpoints, logs every writer).

Tests:
- Python (scripts/): `python3 -m unittest discover -s tests` — single file/test:
  `python3 -m unittest discover -s tests -p test_content.py -k <name>`. Some skip unless
  `bash build.sh --test` built the C test binaries first.
- C tests: `bash build.sh --test`.
- GPU C++ tests are `EXCLUDE_FROM_ALL` CMake targets, e.g. `ninja -C out/gpu taa-shader-test`
  (see bottom of `gpu/CMakeLists.txt`).

Benchmarking: the uncapped title-screen run is mostly the intro movie; `tools/sotc_bench_gameplay.py`
measures gameplay (scripted pad input skips the intro and continues the save, then 60 s standing at
the Shrine of Worship altar, ~5700 commands/frame; it prints the commands/frame so runs of different
scenes are not compared; `--move` is heavier but lands in one of two places). Run game tests outside
the editor's scope (`SOTC_BENCH_WRAP="systemd-run --user --scope --slice=sotc.slice -p MemoryHigh=12G"`).
At that scene the command processor mostly waits for the draw thread (`BackAlloc` spin);
`shadPS4:GpuDraw` and `shadPS4:GpuRecorder` are ~85% busy. Other drivers in `tools/`:
`sotc_play.py` (scripted run: pad events, screenshots), `sotc_run.sh [seconds] [log]` (rebuild +
timed run), `sotc_bench_attract.sh`, `sotc_bench_shrine.sh` (needs `out/save-template/CUSA08809` or
`CUSA08034`, a save after colossus 1 whose profile has the language set), `sotc_hangtest.py`.

Profiling: `SOTC_PROFILE=<thread name part>` (sampler in `src/probe.c`; Linux keeps the first 15
characters: `shadPS4:GpuComm`, `shadPS4:GpuDraw`, `shadPS4:GpuReco`) with `SOTC_PROFILE_OUT=<file>`,
then `tools/profile_functions.py <file> out/gpu/libbbgpu.so 60 --inlines --qualified`;
`SOTC_THREAD_TIMES=1` gives every thread's CPU time over the same window. PGO
(`tools/pgo_train.sh`) trains on the gameplay benchmark; retrain after large GPU-side changes
(changed functions are compiled without the profile meanwhile). `tools/rdoc/` are RenderDoc Python
scripts; RenderDoc capture via `SOTC_WRAP` (JSON command prefix, see `sotc.py`) + F12.

## Architecture

**Launch pipeline** (`sotc.py`):
1. Offline preparation by `scripts/` (re-run only when the fingerprint of eboot, modules and
   `scripts/*.py` changes; stamp in `out/prepared.txt`):
   - `prepare.py` parses the plaintext SELF; `link_modules.py` links eboot + bundled `sce_module`
     PRXs (+ user's sys modules) into one image with a shared import table → `out/boot-linked.bin` (BBPROBE5).
   - `content_profile.py` → `out/content.bin`; `sotc_cpu.py` → `out/sotc-cpu.bin` (function starts
     from `PT_GNU_EH_FRAME` for SSE4a / red-zone CPU patches).
   - `sotc_modes.py` (every launch) → `out/patches.bin` (60 FPS etc., EU 1.01 / US 1.00 only) and
     `out/cmdline.bin` (Bluepoint engine cvars).
2. `out/bb-probe` (`src/probe.c`) maps the image below 2 GiB (the game stores 31-bit pointers),
   applies CPU patches (`gpu/sotc/sotc_patches.cpp`), binds imports, and jumps to the entry point.

**Import binding**: each imported NID goes to `runtime_resolve()` (`src/runtime.c`), which tries
host implementations in order — the per-subsystem `runtime_*_resolve()` tables in `src/runtime_*.c`
(kernel, memory, threads, fibers, files, savedata, pad, audio/AJM, ...; `runtime_sotc.c` holds
SotC-only imports), then `bbgpu_resolve()` in the GPU library. Unresolved imports fall back to the
native export from the linked PRXs (e.g. libc.prx). Matching is by NID only (library/module suffix
letters differ per executable). To add a missing system function, implement it in the matching
`runtime_*.c` following shadPS4's contract and add it to that file's lookup table.

**GPU library** (`gpu/`, C++, `out/gpu/libbbgpu.so`, C API in `gpu/bbgpu.h`; its runtime_* symbols
resolve against bb-probe):
- `gpu/shadps4/` — vendored shadPS4 (`video_core`, `shader_recompiler`, `common`, parts of `core`);
  commit and backports listed in `gpu/VENDOR.txt`. Local edits are marked with `bbport:` or
  `sotc:` comments — keep marking them. Most rendering bugs (water, AMD tint, garbage textures)
  are fixed in `shader_recompiler` (GCN instruction translation) or `video_core/renderer_vulkan`.
- `gpu/shim/` — glue replacing shadPS4's emulator core: settings (`bbport_settings.cpp`, reads
  `BB_*`/`SOTC_*` env and `BB_CONFIG`), window/SDL, overlay, threads.
- `gpu/sotc/` — game-specific CPU patches and TLS handling.
- `bbgpu_handle_fault` is called first by the loader's signal handler (GPU page tracking: mprotect
  and SIGSEGV).

**Behaviour switches** are environment variables (`BB_*` inherited from bbport, `SOTC_*` added
here), set in the environment or `sotc.ini`. Diagnostic ones are listed in `docs/sotc/README-SotC.md`;
newer ones appear in `CHANGELOG.md` entries. Session log goes to `user/last_run.log`.

## Known pitfalls

- **The game's 64 KiB page pool (eboot 0x19e00 allocator, 0x1abf0 release) double-frees by design
  on PC unless `SOTC_POOL_OWNER` is on (default).** Shrinking a block frees pages without unmapping
  them; another block maps them elsewhere; the first block's whole release reads each page back with
  `sceKernelVirtualQuery` and frees it again (two owners: mosaic textures, heap crashes, free tally
  drifting up until the 5th Time Attack). `runtime_memory.c` keeps each physical page's last mapped
  address and answers "not committed" to the release (return address eboot+0x1ac82) for pages that
  moved. Do not remove it; `POOL_FIX` in `sotc_modes.py` only hides the tally drift. Pool bitmap bit
  n is guest address 0x1000300000 + n * 64 KiB (physical 0x100000 + n * 64 KiB). Diagnostics:
  `SOTC_POOL_FREE_TRACE=1` (double frees with both stacks), `SOTC_POOL_WATCH=1`.

- **The shader cache holds host code** (the SRT walkers' x86, which calls the host with its calling
  convention), so the cache folder is `user/cache/<serial>..._sysv`. A cache from the old Windows
  build copied into it overwrote the game's heap within seconds.
- Never keep a Wine prefix inside the repo (`tools/fsr4cap` runs AMD's DLL under Proton): its
  `dosdevices/z:` links `/`, and editor indexers then walk the whole system (VS Code was OOM-killed
  that way).

## Conventions

- Commit subjects are prefixed by area: `shader:`, `shader_recompiler:`, `vulkan:`, `sotc:`,
  `linux:`, `docs:`, `diagnostics:`, `lod stats:`; releases are `Release X.YY: <summary>`.
- A release bumps `VERSION` (sotc.py passes it to the game as `SOTC_PORT_VERSION`: window title,
  in-game menu), the version/table in `README.md` (both languages), and adds a Portuguese
  `CHANGELOG.md` entry.
- User rule: an update turns all its improvements on automatically. The removed Windows launcher
  did it with `DEFAULT_UPGRADES`; on Linux the in-game menu saves its settings into `sotc.ini`, so a
  default changed for the better must not be held back by an old saved value (there is no upgrade
  mechanism for that yet).
- Changes to recompiler/shader output invalidate the user's shader cache; CHANGELOG entries note
  "O cache de shaders é refeito na primeira abertura" when that happens.
- C code: C11, `-Wall -Wextra -Werror`; third-party decoders (LibAtrac9) are compiled separately
  without `-Werror`.
