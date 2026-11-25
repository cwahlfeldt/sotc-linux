# Shadow of the Colossus — PC (native port)

Native port of the PS4 **Shadow of the Colossus** (CUSA08809, EU version 1.01, or CUSA08034, US
version 1.00) to **Linux**.
The game's code runs directly on the CPU. This is not a full emulator: there is a loader and the
system functions the game needs. The GPU uses the Vulkan video core of the shadPS4 SotC fork. The
base is [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc) (GPL-2.0).

This repository **contains neither the game nor Sony firmware**. You need your own.

## Requirements

- Linux x86-64, a CPU with AVX, BMI1, LZCNT and MOVBE (Intel Haswell / AMD Zen or newer) and a GPU
  with a Vulkan 1.3 driver (Mesa RADV or ANV, or NVIDIA's).
- The build tools and libraries listed in `README.md` (Arch / CachyOS: one `pacman` line), and
  Python 3.
- **Your own dump** of CUSA08809 or CUSA08034 (a folder with `eboot.bin`, `sce_module`,
  `sce_sys`...).
- **Sound:** since 0.75 the port has a **built-in sound mixer**, and the game has sound without
  anything from the console. Optional: `libSceNgs2.sprx` and `libSceUlt.sprx` from **your own
  console**, decrypted (the same as in shadPS4's `user/sys_modules` folder; on a PS4 with GoldHEN
  they are in `/system/common/lib/`, FTP on port 2121). With them the sound is the firmware's:
  `SOTC_SYS_MODULES=/folder/with/the/sprx` in `sotc.ini`.

## How to play

1. Put the dump next to this folder (`../CUSA08809` or `../CUSA08034`) or write
   `SOTC_GAME_DIR=/path/to/the/game` in `sotc.ini`. The 1.01 update (`CUSA08809-UPDATE`) and the
   DLC (`CUSA08809-DLC`) are found next to the game.
2. Run `bash run.sh`: it builds the port (`out/bb-probe` and `out/gpu/libbbgpu.so`) and starts the
   game. `python3 sotc.py` starts it without building.

The first time, the game image is prepared, which takes a few seconds. That is only repeated when
the game or the modules change. Saves and the shader cache are in `user/`, the session log in
`user/last_run.log`.

What you change in the in-game menu (F1) is kept in `user/settings.json` and applies at the next
start, with the same defaults as the Windows releases (16x filtering, high textures, no logos...).
Options can also be environment variables or `NAME=value` lines in `sotc.ini`, which win over the
file; the full list is at the top of `sotc.py`.

## Image and performance

In `sotc.ini` (or the environment):

- **Output** (`SOTC_OUTPUT_RES=2560x1440`, for example): 720p, 1080p, 1440p or 4K. The game renders
  at 1080p, as on the PS4, and the image is scaled to the output with **FSR 1** + sharpening (RCAS)
  or bilinear. The window never goes over 90% of the screen; fullscreen uses the whole monitor.
- **60 FPS** (`SOTC_MODES=fps60` and `SOTC_FPS_CAP=off`; experimental): removes the game's 30 FPS
  limit (GoldHEN patch by illusion), with a 120 Hz vblank.
- **Bind reuse** (on by default; `SOTC_FAST_BIND=0` turns it off): skips rebuilding the descriptors
  when the next draw uses the same pipeline, resources and uniforms. Measured at the Shrine:
  ~25 → 30 FPS. In 0.60.5 it left a grid of black dots on sandy ground; with the fix the demo's
  sand is clean.
- **Sharp textures** (`af16` in `SOTC_MODES`, for example `SOTC_MODES=fps60,af16`): 16x
  anisotropic filtering, almost free.
- **HDR** (`hdr` in `SOTC_MODES`): HDR10 output with the game's own HDR rendering; the desktop has
  to offer HDR. White is at 200 nits (`SOTC_HDR_WHITE` changes it). Works with FSR 1 and DLSS.
- **PS4 Pro mode** (`SOTC_NEO=1`): the game sees itself on a PS4 Pro and offers, in its own menu
  (Options > Display), the **Cinematic** graphics mode (1440p, more detail) or **Performance**. It
  is heavier: ~25 FPS in the open world.
- **Effects** (`fx_vignette=0`, `fx_fog=0`, `fx_ssao=0` in `sotc.ini`, or in the in-game menu): the
  vignette, atmospheric fog and ambient occlusion (SSAO) can be turned off. Motion blur, brightness
  and the filters are in the game's own menu.
- **Engine cvars** (`SOTC_CVARS="NAME=value NAME=value"`): Bluepoint engine variables, for those
  who want to experiment.

The patch modes apply to EU 1.01 and US 1.00 (the executable is the same); on other versions they
are not applied. Each version keeps its own saves (`user/savedata/1/CUSA08809` or `CUSA08034`) and
only uses DLC of the same region.

## Controls

**Mouse:** click the game window to capture the mouse, which then turns the camera; Esc or
switching windows releases it. Left button = R1 (grab), right = □ (attack), middle = L1.
Sensitivity and inversion are in the in-game menu (F1). To remap the mouse buttons, use
`mouse.<input>=left,right,middle,x1,x2`.

**Remapping (`sotc.ini`):** one line per input, with several choices separated by commas (empty =
no key). `key.<input>=` changes the keys (SDL names such as `Q`, `Left Shift`, `Space`) and
`mouse.<input>=` the mouse buttons. Inputs: `cross circle square triangle l1 r1 l2 r2 l3 r3
options touchpad touchpad_right up down left right move_up move_down move_left move_right look_up
look_down look_left look_right`. Examples: attack with the left button and the sword's light ray
with the right one: `mouse.square=left` and `mouse.l1=right` (and `mouse.r1=` to free R1); L1/R1
on other keys: `key.l1=Q` and `key.r1=E`.

A controller (DualShock 4, DualSense, Xbox...) is used automatically. With several connected, pick
one with `BB_GAMEPAD=` (its name or part of it) in `sotc.ini`. The keyboard works together with the
controller:

| Keyboard | PS4 |
|---|---|
| W A S D | left stick |
| arrows | right stick (camera) |
| Space | ✕ |
| Left Shift | ○ |
| E | □ |
| Q | △ |
| 1 / 3 | L1 / R1 |
| R / F | L2 / R2 |
| Z / C | L3 / R3 |
| Enter | Options |
| I J K L | d-pad |
| Tab / Backspace | touchpad (left / right) |

The controller can be remapped in `sotc.ini` too, for example `pad.circle=b`. The inputs are:

- buttons: `cross circle square triangle l1 r1 l2 r2 l3 r3 options touchpad touchpad_right`;
- d-pad: `up down left right`;
- on the keyboard, the sticks: `move_up` `move_down` `move_left` `move_right` and
  `look_up` `look_down` `look_left` `look_right`.

## Status

Working: logos, intro, menus with text, loading a save, exploring on horseback, sound (built-in
mixer, or the console's modules).

Performance measured at the Shrine of Worship, playing, 60 FPS mode, i5-13600KF + RX 6650 XT:
~72 FPS (`tools/sotc_bench_gameplay.py`). In the normal mode the game runs locked at 30 FPS, as on
the PS4.

## Common questions

- **DirectX 11/12?** No. The video core (shadPS4) translates the PS4 GPU to Vulkan; the game's
  shaders become SPIR-V. Every recent graphics card with DirectX 12 also has Vulkan 1.3: update the
  driver. A DirectX mode would mean rewriting the whole video core.
- **AMD and Intel cards?** The optimizations apply to any card. Two of them turn on by themselves
  only on NVIDIA and AMD (the periodic submission of work to the GPU and the readbacks ahead). To
  try them on Intel: `SOTC_FLUSH_US=1000` and `SOTC_RB_AHEAD=1` in `sotc.ini`; if the screen goes
  black, remove both lines.
- **Do I need files from the console for sound?** No, since 0.75: the port's built-in mixer plays
  the sound. `libSceNgs2.sprx` and `libSceUlt.sprx` (Sony firmware, which cannot be distributed)
  stay optional; with them the sound is the firmware's.

## Credits

- [bloodborne_pc](https://github.com/Supermedo/bloodborne_pc) (bbport, deadinside28 and forks): the
  native loader and runtime this port is based on.
- [shadPS4](https://github.com/shadps4-emu/shadPS4) and the shadPS4 SotC fork: the Vulkan video
  core.
- [Pink-shadPS4](https://github.com/luizgustavs/Pink-shadPS4) (luizgustavs): the culling cvars, the
  protection of the game's heap against GPU reads (`bpe_heap_guard`), the periodic flush, the
  readbacks ahead, the wait marker and the Vulkan command recorder on its own thread
  (`cp_record_thread`).

## Diagnostics

These environment variables help investigate problems:

| Variable | Effect |
|---|---|
| `SOTC_FPS=1` | frame rate every 5 s |
| `BB_READBACKS=0/1/2` | GPU readbacks; the default 2 is what the game needs |
| `SOTC_FAST_BIND=0` | turns off reusing descriptor binds between identical draws (default: on) |
| `SOTC_RECORD_THREAD=0` | records the Vulkan commands on the command thread itself (default: a thread of its own) |
| `SOTC_INDIRECT_DIRECT=0` | keeps indirect the draws whose arguments are on the CPU |
| `SOTC_WAIT_MARKER=1/2` | waits for the GPU read a marker it writes (experimental) |
| `SOTC_CMD_STATS=1/2` | draws and dispatches per frame (2: the most used compute shaders) |
| `SOTC_AMD_WAVE32=1` | AMD only, for testing on GCN (RX 470-590, Vega, integrated): the shaders are converted to 32 lanes, as the SotC-AMD-Fix layer does (characters flashing white). The shader cache is rebuilt; the log shows `GPU: AMD wave32 on`. By Lucas-blip-png |
| `SOTC_SLOW_BUILD_MS=500` | the log shows `SOTC SLOW BUILD` for each pipeline built in the background (or waited for by the command recording) that took that long or more; `SOTC SYNC PIPELINE` shows those built on the command thread over 30 ms (`SOTC_SYNC_PIPELINE_MS`). For the long stalls on Intel Arc cards |
| `SOTC_HDR_WHITE=nits` | with HDR: the game's white in nits (default 200; the game's own output has ~100) |
| `SOTC_EVICT_ASYNC=0` | giving back the arenas' cold memory waits for the GPU on the command processor, as before (~44 ms each time) |
| `SOTC_UI_HIRES=0` | with DLSS, the interface (text, logos, HUD) is drawn at the render resolution and scaled again, instead of at the output resolution |
| `SOTC_FSRFG_ASYNC=1` | FSR 3 frame generation: its passes run on a compute queue of their own, beside the game's drawing, at low priority (`SOTC_FSRFG_ASYNC_PRIORITY=0`: the driver's default). Off by default: on an RX 6650 XT it gained no FPS (62.2 vs 61.6) and the generated frame went out ~5 ms later. The log shows `GPU frame generation queue` |
| `SOTC_FSRFG_NO_WORK=1` | measurement only: with FSR 3 on, the game frame is copied in place of the generated one; the two presents and the pacing stay, only FSR 3's GPU work goes |
| `SOTC_PIN=1` / `2` | Linux, test (upstream PR #464): the three heavy GPU threads (draw, command processor, recorder) get a P-core each; with `1` the other thread of those cores stays empty and the game's other threads keep off them, with `2` only the three CPUs are reserved. Released during loads (under 25 FPS). Off by default: on an i5-13600KF it did not change the Shrine FPS (74.8 vs 74.4, five runs each) |
| `SOTC_WINDOW_BEHIND=1` | automated tests: the window opens without asking for the focus (on Linux the compositor decides; COSMIC focuses it anyway) |
| `SOTC_PCORES=0` | Linux, Intel CPUs with P- and E-cores (12th generation onwards): the GPU threads (command processor, draw and recorder) run on any core again (default: only on the P-cores, where they do more) |
| `SOTC_PROFILE=name` | samples the thread with that name every ~1 ms, from `SOTC_PROFILE_DELAY` s (default 20) for `SOTC_PROFILE_SECONDS` s (default 15), and lists where it spends its time. On Linux the name is the first 15 characters (`shadPS4:GpuComm`, `shadPS4:GpuDraw`, `shadPS4:GpuReco`); `SOTC_PROFILE_OUT=file` saves the samples for `tools/profile_functions.py file out/gpu/libbbgpu.so`; `SOTC_THREAD_TIMES=1` shows every thread's CPU time over the same window |
