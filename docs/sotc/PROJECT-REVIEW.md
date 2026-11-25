# Shadow of the Colossus PC — full project review

Status on 12 Oct 2026 (branch `sotc`, commit `e5d6233` and following). Public repository:
<https://github.com/AjncSystem/ShadowOfTheColossus-PC> (versions 0.0.8 and 0.0.9 released).

This document gathers in one place what the project is, how it works, everything done so far, the
performance numbers, the known problems and the next steps.

---

## 1. What it is

A **native Windows port** of the PS4 *Shadow of the Colossus* (CUSA08809, EU, executable version
1.01). It is not a full emulator like shadPS4: the game's code runs **directly on the PC's
processor**, and only what is exclusive to the PS4 is recreated:

| PS4 part | How the port handles it |
|---|---|
| CPU (AMD Jaguar, x86-64) | the game's code runs **natively** on the PC's x86-64 (the same architecture). Only the few instructions Intel lacks (SSE4a) and the use of the *red zone* are fixed at load time. |
| Operating system (Orbis OS) | its own runtime (`src/runtime_*.c`) implements the system functions the game calls: memory, files, threads, saves, audio, controller, dialogs… |
| GPU (AMD GCN "Liverpool") | **emulated**: the game's PM4 commands and GCN shaders are translated to **Vulkan** (shadPS4's video core, with our fork's fixes). |
| The game's libraries (libc, Fios) | those of the dump itself are linked natively during preparation. |
| Sound (libSceNgs2 / libSceUlt) | the modules **from the user's own console** are linked (never distributed). |

Base: the *bbport* project (a native port of Bloodborne, GPL-2.0), adapted to SotC.

## 2. How it works (execution flow)

1. **`SotC.exe`** (the launcher, Python/Tkinter frozen with PyInstaller): first-time setup, game
   library, image/controls options, and then it calls `sotc.py`.
2. **`sotc.py`**: prepares the game once (and again only when something changes):
   - `scripts/prepare.py` turns `eboot.bin` (SELF) into a flat image;
   - `link_modules.py` / `link_libc.py` link libc, Fios and the user's sound modules;
   - `content_profile.py`, `sotc_cpu.py` (CPU fixes), `sotc_modes.py` (60 FPS, 16x AF, engine cvars);
   - if there is an update (`CUSA08809-UPDATE`/`-patch`) with an `eboot.bin`, its image is used.
3. **`bb-probe.exe`** (the "game"): a loader in C (`src/probe.c`) + the runtime + the video core
   (`gpu/`). It loads the image **below 2 GiB** (the game keeps pointers in 31 bits), creates the
   game's threads/fibers and starts.

### Directories

| Folder | Contents |
|---|---|
| `src/` | loader and runtime (memory, files, saves, audio, pad, services, fibers, SotC) |
| `gpu/shadps4/` | video core (video_core, shader_recompiler, gnmdriver, videoout) |
| `gpu/shim/` | bridge between the runtime and the video core, SDL window, ImGui overlay |
| `gpu/sotc/` | CPU fixes (SSE4a, red zone) ported from the fork |
| `scripts/` | game preparation |
| `launcher/` | `SotC.exe` (sotc_launcher_win.py, sotc_discovery.py, icons) |
| `tools/` | automated tests, benchmark, A/B, profiler |
| `packaging/windows/` | `package_sotc.sh` → `dist/SotC-PC.zip` (refuses `.sprx/.prx`) |
| `docs/sotc/` | this document, the package README, the "path B" plan |

## 3. Timeline

### 7 Oct — the game starts
- Imports matched by NID; SotC's functions in a file of their own (`runtime_sotc.c`).
- An extra memory window `0x700000000–0x800000000` (the game maps at a fixed address).
- The game reaches its own initialisation.

### 8 Oct — playable
- **Fibers** (`runtime_fiber.c`), **CPU fixes** (SSE4a, red zone) and **the image below 2 GiB** →
  first frames (the hawk in the canyon).
- The fork's GPU fixes applied to bbport's core → the intro without black polygons.
- **Turning point:** the video core of **our shadPS4 fork** in place of bbport's → logos, menus with
  text, the save loads, open world at 30 FPS, 10 min without a crash.
- A silent crash solved: the page tracker protected the fibers' stacks.
- **Real audio** with the user's modules; the `sotc.py`/`SotC.bat` launcher; a Windows package.
- **Modes**: 16x AF and 60 FPS (a patch at load time, `BB_VBLANK_HZ=120`).
- `SotC.exe` (graphical launcher), bbport 0.4's controls (keyboard + controller together,
  remapping), mouse camera, 720p–4K output resolution, PS4 Pro mode, engine effects.

### 8–9 Oct — performance
- A fixed benchmark: the **title screen demo** (always the same route).
- Gains: a shader information cache, HLE of the compute that fills tables, a per-thread memory
  pointer cache, Pink's culling cvars, the BPE heap guard, buffer sync without a lock, indirect draws
  with arguments on the CPU become direct, Vulkan recording on its own thread, image
  description/lookup caches, fewer write faults, periodic submission by time (`SOTC_FLUSH_US=500`).
- Result in the demo (60 FPS, i9-13900K + RTX 2060 SUPER): **average 37–45 → ~67 FPS**, the heaviest
  stretch (the canyon bridge) **~17 → 29–34 FPS**.

### 12 Oct — launcher, release, saves, textures
- **0.0.8 public**: game library, automatic search, key remapping, a new icon, an option for
  submitting work to the GPU (AMD/Intel).
- **0.0.9 public**: an initial setup screen (only asks for the main folder, like shadPS4), updates
  like shadPS4 (`-UPDATE`/`-patch` over the base game), **DLC** in a folder or **`.pkg` without
  installing** (the 6 DLC listed to the game).
- The project gathered in a **single folder** (`SotC-PC`).
- **Saving fixed**: the game never saved ("no space").
- **Texture streaming** (`GET_LOD_STATS`): sharp textures up close, waterfalls with their water
  curtains, the water surface rippling.
- **A save list on screen** to load and save, with **save deletion**.

## 4. Current features

- **Launcher** (`SotC.exe`): setup on the first start; finds the game, update, DLC, shadPS4 saves and
  sound modules; library; image options (output resolution, FSR 1, sharpness, 16x AF, 60 FPS, PS4
  Pro, effects), controls (keyboard/controller/mouse, remapping), submitting work to the GPU; a
  desktop shortcut with the game's icon.
- **Game**: runs from start to finish in the normal mode; real audio; saves (save, load, delete);
  DLC; update 1.01; PS4 Pro mode (Cinematic/Performance in the game's menu).

## 5. Main technical fixes

| Problem | Cause | Fix |
|---|---|---|
| Silent crash without a message | a fiber stack page protected by the GPU tracker | fiber stacks registered and excluded from tracking |
| The game's pointers broken | the game keeps pointers in 31 bits | image loaded below 2 GiB |
| Black polygons in the intro | the fork's GPU fixes missing | the fork's video core |
| Intermittent black screen | bbport optimizations incompatible with SotC | the fork's core; precise GPU readbacks |
| The game never saved | the port said each save took 1 GiB | the saves' real size |
| Loading went into a loop / each save created a new slot | the list dialog "finished" without a choice | a list drawn on screen (ImGui overlay) |
| Blurred textures, black water, waterfalls without a curtain | the `GET_LOD_STATS` command ignored → the game never loaded the fine mips | statistics emulated from the textures used; textures uploaded again when the game maps new memory |
| The GPU queue hung with threaded recording | the presenter waited for a tick before it was submitted | wait for the submission before presenting |

## 6. Known problems (by priority)

1. **Memory corruption with texture streaming.** Asking for the maximum resolution (mip 0/1) for
   everything makes the game corrupt its own memory within 1–4 minutes; with the current limit
   (mip 2, 512×512) the demo runs to the end, but **loading another save without restarting the game
   can close it**. Recommendation: restart the game before switching saves. Tested and **ruled out**
   as the cause (12 Oct): EOP labels written early (`SOTC_EOP_DEFER=1` writes when the GPU finishes:
   FPS halves and the failure continues), the HLE copy marking the whole range as written by the GPU
   (fixed to mark only the pieces; the failure continues) and memory refusals by the runtime (there
   are none). The symptom is always memory the game reused still read/written with old data (heap
   nodes, descriptors and shaders with garbage) around 250–270 s into the demo with mip 0/1.
2. **Black shadows**: areas in shadow without ambient light (did not get worse with the recent
   changes). Lead (a RenderDoc capture of the intro's temple, ~178 s): a half-resolution input of the
   lighting passes (960×540, A2B10G10R10, read by ~16 light draws) **is never written in the frame
   and stays at zero** — probably missing ambient occlusion/indirect light. It is not yet known which
   pass should write it (no write as an image nor as a buffer found).
3. **Water**: the lake opaque/flat in some places; the wave motion not confirmed.
4. **Closing in the title screen demo** after several minutes (the same family as item 1).
5. Old saves copied from shadPS4 show the label "Profile" (the label is fixed when saving over it).
6. AMD/Intel: the submission optimizations are off by default and little tested.

## 7. Diagnostics (environment variables)

| Variable | Purpose |
|---|---|
| `SOTC_FPS=1` | FPS and GPU readbacks in the log every 5 s |
| `SOTC_SAVE_TRACE=1` | logs the save calls |
| `SOTC_LOD_STATS=0` / `SOTC_LOD_LEVEL=n` / `SOTC_LOD_TRACE=1` | texture streaming: off, requested level, log |
| `SOTC_MAP_INVALIDATE=0` | does not upload textures again when the game maps memory |
| `BB_WRITE_LOG=1` | logs the port's writes to the game's memory (dumped on a fault, with totals per source) |
| `SOTC_RDOC_TRIGGER` + `SOTC_PLAY_WRAP` | a RenderDoc capture of a GPU submission (`renderdoccmd capture`) |
| `SOTC_SHOT_OVERLAY=1` | screenshots with the overlay (save list) |
| `BB_FRAME_DUMP_TRIGGER` | a screenshot of the frame when the file appears |
| `BB_PAD_FILE` / `BB_PAD_RECORD` / `BB_PAD_REPLAY` | controller through a file, record/replay a route |
| `SOTC_PROFILE=<thread>` | sampling profiler |
| `SOTC_FLUSH_US`, `SOTC_RB_AHEAD`, `SOTC_RECORD_THREAD`, `SOTC_INDIRECT_DIRECT`, `SOTC_FILL_HLE` | optimizations (on/off for tests) |

Tools: `tools/sotc_play.py` (script: `t:cross`, `t:shot`, `t:rdoc`…), `tools/sotc_bench_attract.sh`
(benchmark), `tools/sotc_intro_ab.sh` (A/B on the intro's river), `tools/profile_sym.py`.

## 8. Build, package, test

```bash
# build (MSYS2 CLANG64 in I:\msys64)
TMP=$(cygpath -w /tmp) PATH=/i/msys64/clang64/bin:/i/msys64/usr/bin:$PATH ninja -C out/gpu bb-probe bb-gpu-capabilities
cp out/gpu/bb-probe.exe out/gpu/bb-gpu-capabilities.exe out/
# package (dist/SotC-PC.zip and dist/SotC-PC/ with the saves kept)
bash packaging/windows/package_sotc.sh
# benchmark (60 FPS, with the real game's culling cvars)
BENCH_CVARS="doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0" bash tools/sotc_bench_attract.sh
```

Project rules: commits as `AjncSystem <AjncSystem@users.noreply.github.com>`; never distribute Sony
firmware (`.sprx`); large dumps on drive I:.

## 9. Next steps

1. **Streaming stability** (problem item 1): EOP labels written when the GPU finishes ("path B", a
   step already prototyped with `VK_EXT_external_memory_host`), then unlock the maximum texture
   resolution.
2. **Shadows and ambient light**: capture a scene with RenderDoc and follow the lighting pass.
3. **Water**: the surface shader (the draw found in the capture) and the wave animation.
4. A progress indicator with % on the initial black screen.
5. Tests on AMD and Intel.

### About DirectX 12

The port **is already native x86-64 on Windows**: the game's code runs directly on the processor. The
only "emulated" part is the GPU, which is translated to **Vulkan** today. Switching to DirectX 12
would mean rewriting the whole video core (thousands of files translating commands and GCN shaders →
SPIR-V) for D3D12/DXIL, without a real gain: Vulkan works on every Windows card (NVIDIA, AMD, Intel)
and performance depends on the translation, not the API. A "full" reverse engineering (recreating the
game's renderer in DirectX, without GPU translation) would be another project, of many months. The
path that brings results is to keep fixing the current translation.
