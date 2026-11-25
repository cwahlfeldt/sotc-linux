# Changelog

## Unreleased (Linux)
- ⚙️ **Settings kept between starts**: the in-game menu's choices (FPS mode, texture quality,
  frame generation, volume and the ◆ settings) are saved in `user/settings.json`, with the
  defaults the Windows releases used. Variables set in `sotc.ini` or the environment still win.
- 🌑 **Soft shadows and ambient occlusion around Wander on AMD cards** (upstream #461): the
  shader translator read the wrong address for the characters' capsule records, so they flickered
  or were missing with direct memory access off (the AMD default). A GPU-written image whose small
  mips overlap the next one is no longer freed every other frame.
- 🛡️ **Shader variants keep their own resource layout** (upstream PR #422): a variant that
  declares other textures than the first one of its program was created against the first one's
  pipeline layout (`SOTC PERMUTATION ... images 16/13` in the log), invalid Vulkan that can read
  garbage on AMD. FMask textures and ordinary ones now get separate variants.
- 🛡️ **Two crash guards** (upstream PR #464): a game-heap block found already unlinked while saving
  (`0x499cc`, after about an hour of play) is skipped like the other cleared objects, and the
  statistics and eviction-compare threads fall back to working inline when a thread cannot be
  created.
- 🖥️ **Dynamic FPS on 75/100/165 Hz screens** (upstream #454): the step divides the refresh rate
  (75 Hz → 37.5, 100 Hz → 50, 165 Hz → 41.25). **Textures above 1080p** (upstream #455): the
  texture pool reserve is 0 at any render size above 1920×1080. `SOTC_FPS_DYNAMIC_SLOW_FPS` sets
  the rate under which a frame counts as slow. The F1 menu logs it when a setting cannot be saved.
- **The shader cache is rebuilt on the first start.**
- Tools: `tools/sotc_ride_bench.py` (a world-streaming benchmark: Wander carried along a fixed
  5.8 km loop by the engine's own commands, frame-time stats at 60 FPS) and a gameplay benchmark
  that ignores the player's saved FPS limit and frame generation. `SOTC_WINDOW_BEHIND` works on
  Linux.
- Off by default, measured without a gain on an RX 6650 XT / i5-13600KF: `SOTC_FSRFG_ASYNC=1`
  (FSR 3 frame generation on a compute queue of its own), `SOTC_PIN=1/2` (upstream PR #464's GPU
  thread placement); `SOTC_FSRFG_NO_WORK=1` measures FSR 3's GPU cost.

## 0.76.2 — 2026-11-17
- 🛠️ **Intel CPUs: the hero falling through the floor and the crash at the title screen fixed** (since 0.76). When the game is prepared, the function list of the linked modules (read for the BMI1/LZCNT/MOVBE emulation) replaced the game's own (55,790 functions became 731). Without it, SSE4a emulation (every Intel CPU) went in without the stack protection of 3 game functions: broken physics and, with frame generation off, the game closed ~10 s after starting (guest 0xf42ce0). The lists now add up. The game does not need to be prepared again.

## 0.76.1 — 2026-11-17
- 🌌 **Dashed lines in the sky on AMD Radeon cards fixed** (#432, #433): one sky shader read values from neighbouring pixels in a way AMD's driver does not guarantee at triangle edges, and drew a grid of lines over the sky (title screen and in game). It now uses quad operations, which every driver guarantees. No change on NVIDIA. The shader cache is rebuilt on the first start. `SOTC_QUAD_SWIZZLE=0` restores the old behaviour.

## 0.76 — 2026-11-16
- 🎮 **New F1 menu**, laid out like ZooT-PC's: Display, Performance, Grass, Sound, Controls, Game and Debug tabs (Q/E or L1/R1), values between arrows, help for the chosen option on the right, in the game's colours. What can change while playing changes at once; what only applies on the next start (marked ◆) is saved in the launcher's settings and a band asks for a restart. Texts in the launcher's languages.
- 🖥️ **Older CPUs without BMI1/LZCNT/MOVBE now run the game** (Oussama268 and Lucas-blip-png, #49, #88, #200): those instructions are emulated at load time (Intel Sandy/Ivy Bridge, Xeon E5 v1/v2). AVX is still required. Open-world FPS is lower on these CPUs.
- 🔊 **Music at the right volume** (Oussama268, #426): the built-in mixer played music and 5.1 sounds up to 20-30 dB too quiet. Compared channel by channel with the console's module, it is now within ~1 dB (filters left over from the previous sound, side chain summed in, the game's effects off, LFE twice).
- 🔊 **Volume above 100% no longer squashes the sound**: a real limiter (down in ~1 ms, back in ~250 ms) instead of clipping each sample; in fights the music no longer disappears behind the impacts. `SOTC_AUDIO_LIMITER=0` restores the old one.
- 🦅 **5th colossus (Avion) flying up forever** (#421, #425): in PS4 Pro mode at 60 FPS with the Cinematic graphics mode the game ran on a 30 FPS clock and physics ran twice as fast. The 60 FPS mode now covers that path too.
- ⚡ **Fewer hitches when an area loads** (Oussama268): 768 MB of staging buffers kept on PCs with 12 GB of RAM or more (#435); large buffer uploads on the copy threads (#437); the memory comparison when cold buffers are given back on its own thread (~40 ms less at the Shrine approach). On the demo: frames > 50 ms from 7 to 2, worst frame from 566 to 70 ms.
- 🎨 **Colours in dark areas at high brightness** (joaobatista235, #427): a continuous gamma curve, no red/green in the shadows.
- Vulkan validation fix in colossus 6's depth copy (Oussama268, #436).
- **RecompLauncher** (elripalda, #439): the port can be installed and updated from RecompLauncher; the launcher takes the game folder it hands over.
- Diagnostics (off by default): texture copy reasons, `SOTC_SLOW_OPS` with other threads' commands, `BB_AUDIO_STATS` with sound levels.

## 0.75 — 2026-11-12
- 🔊 **Sound without the console's modules: the PS4 files are no longer required** (Oussama268, from HayatoG/tlg_pc, GPL-2.0): when libSceNgs2.sprx and libSceUlt.sprx are missing, a built-in NGS2 mixer plays the game's sound (ATRAC9 through LibAtrac9). **It is the default for everyone**; to use the firmware's sound instead, tick "Use my console's sound modules" under Game & saves. Tested: normal sound and the same FPS either way (69.7 with the mixer, 69.5 with the modules). `SOTC_NGS2=native` restores the old behaviour.
- 🎧 **Sound page in the launcher:** output in **Stereo 2.0**, **Surround 5.1**, **Surround 7.1** or Automatic (the game mixes in 7.1; for 2.0 and 5.1 the port mixes down itself, ITU coefficients, no clipping), subwoofer bass in stereo, the **sound device** (headset, TV, speakers) without changing the Windows default, **volume up to 500%** (also in the in-game menu, F10; peaks softened) and the sound engine.
- **"What's new" in English** for launchers in other languages than Portuguese (#410).

## 0.74.2 — 2026-11-12
- **Crashes on AMD Radeon fixed** (Oussama268, #413): a graphics pipeline the driver refuses no longer closes the game; its draws are skipped (`SOTC PIPELINE FAILED` in the log). It was the crash of the RX 6600/6700 XT/6750 XT near the 4th colossus's arena and on the 9th's bridge (#397, #408, #393). Two causes of the refusal found with the Vulkan validation layers: a shader variant created with one binding fewer than its layout (the LOD feedback buffer of the High/Maximum textures) and the game's bytes uploaded to a depth buffer kept in another format.
- **Random colours on AMD GCN** (RX 470–590, Vega) fixed (marko0905, #411): a compute shader read a "lane" that does not exist on 64-lane cards. `SOTC_WAVE64_ABSENT_LANES=0` turns it off.
- **Silent crash of the heap guard** fixed (mrgroeff, #409): the game heap's fields are now read through the backing view, which is never protected.
- **The game closing on load with Windows' Control Flow Guard** on (Oussama268, #414, #322): the game's fibers carry the TEB's stack limits. `SOTC_FIBER_TEB=0` turns it off.
- **Hardened updater** (Oussama268, #415): the update repository is in a file of the package, so no merge changes the address any more.
- The shader cache is rebuilt once (version 40). Side-by-side test in the open world (the same route, an empty cache in both): the same FPS as 0.74.1 (57.0 against 57.8) and fewer stalls (18 frames above 50 ms against 29).

## 0.74.1 — 2026-11-10
- **Updating through the launcher fixed:** in the merge of Oussama268's 0.72.1-opt13 (v0.73) the updater's releases address (`launcher/sotc_update.py`) became his fork's, so the v0.73 and v0.74 launchers looked for updates there and never offered the new version. It is this repository again, with a test (`tests/test_update_repo.py`) that prevents the change from happening again. Anyone on v0.73 or v0.74 has to download v0.74.1 by hand once.

## 0.74 — 2026-11-10
- **A lighter draw thread: Lukto02's fast paths (#308)** for depth-only and G-buffer draws: when no render register, image or state changed since the last draw, the targets' preparation, the start of rendering and the dynamic state are reused (99% hits in the open world). Verification: 0 differences in more than 45 million checks. Demo with Maximum textures and PS4 Pro: 83.0 → 85.4 FPS, minimum 62.6 → 66.2; in the open world the game stays at 60 FPS 40–50% of the time (23–32% before). Can be turned off through bits 28 and 29 of `BB_TOGGLE_FILE`.
- **DLSS-G frame generation 3x, 4x, 6x and Dynamic** (Lucas-blip-png, #314): a "DLSS-G multiplier" option in the launcher (default 2x, as before); limited to what the card accepts (RTX 50 up to 6x, RTX 40 stays at 2x). `SOTC_DLSSG_FRAMES` / `SOTC_DLSSG_MODE=dynamic`.
- **Thread priorities on CPUs with 4 threads or fewer** (Lucas-blip-png, #312, #267): the game's workers below normal, sound at the top, file reads above normal. Larger CPUs do not change. `SOTC_JOB_PRIORITY=0` turns it off.

## 0.73 — 2026-11-09
- **The ending without crashes:** the heap guard's two shortcuts (`SOTC_GUARD_STALE`, `SOTC_GUARD_USER_POINTER`), turned back on in 0.72, damaged the game's memory at the ending (zeroed objects, the allocator at `0x499cc`), as T49 already suspected for `0x49800`. They are off again; with them off the ending and the intro skip went through without any crash and with nothing to repair.
- **Crashes at the ending (the "End" screen and the passage to the intro) fixed the same way as `0x564d24`:** the game was about to destroy an object whose memory was already zeroed (`0x144c60`, `0x14934f`) or release a reference to an object that does not exist (`0x14cce7`); the port skips that object as the game does when it does not exist (`SOTC_FIX_NULL_OBJECTS=0` turns it off).
- **Mosaic in Time Attack fixed** (it came from the ending's fix, `SOTC_POOL_FREEZE`): when entering an arena the game puts new textures where the old ones were, and the fix kept the old content for 400 frames. Now a load (save, area, arena) releases everything it held and it does not act for the following 90 s; at the ending, where it is needed, there is no load in between.
- **The game frozen on the same image (normal FPS) fixed:** the compute queue's read pointer, which lives in the game's memory, was moved with a direct write; when the GPU page tracking protected the page again before the write repeated, it failed endlessly (`SOTC FAULT LOOP` in `ProcessCompute`), the compute queue stopped and the game froze. It is now written like the end-of-pipe labels, straight into the game's memory (`SOTC_RPTR_BACKING=0` returns to the old way).
- **The `0x564d24` crash fixed** (the most frequent: 4 times since 3 Nov, always 30–40 s after loading a save): the game walks a list of objects and asks each one for a component (eboot 0x660fc0), which comes back empty for a deleted object or one of another type, and read that component without checking. The item is skipped as the game skips an object that does not exist (`SOTC_FIX_564D24=0` turns it off).
- **Exe built with ThinLTO and PGO, like Oussama268's:** the usage profile was recorded over two laps of the open world (camera turning, 60 FPS) and the compiler optimized what runs most there. The code was the same and our FPS stayed below his because of that; in the user's test it was "the same or better". (The profile is in `pgo/`, outside the repository; `tools/pgo_train.sh` redoes it.)
- **Dynamic FPS (on by default in the 60 FPS mode; a box in the quick settings):** when the game stays below 50 FPS for 1.5 s the limit drops to a step that matches the screen (48 at 144 Hz, 40 at 120 Hz, 30 at 60 Hz) and stays steady instead of swinging; every 10 s it tries 60 again. The game's logic follows real time, so it does not go into slow motion.
- **Merges Oussama268's 0.72.1-opt13:** far fewer hitches when travelling the world (fewer memory locks on the draw thread, the game heap's guard and memory tables in blocks), temporary render targets reused at the heavy colossi (`SOTC_RT_STASH`), a dirty GPU readback redone by the game's own thread (`SOTC_RB_REQUEUE`, in place of our experimental `SOTC_RB_DIRTY_RETRY`), the texture upload limit turned off (black textures), frames that do not pile up behind the limiter (controller lag at 30 FPS, #128), a retry on error 487 at start (#110), DLAA in the launcher and rare crashes fixed (the SnormNz format, a nested failure in the exception handler). Our lock-free memory lookup (`SOTC_CLAMP_GAP`) was replaced with his (`SOTC_CLAMP_FAST`).
- **Extreme mode sharp again:** 0.72.2 had put High and Maximum at mip 2 and Maximum (the Extreme mode's textures) became blurred. High goes back to mip 1 and Maximum to mip 0 (light profile: Maximum 1, High 2), now without the 3 s of kept banks and with the page pool's protection, which caused copies of up to 1.1 GB in one frame in the forest.

## 0.72.2 — 2026-11-05
- **The window title with the port's version and the play time:** `SHADOW OF THE COLOSSUS™ · v01.01 · Port v0.72.2 · 60 FPS · 0:12:34`.
- **Updating the port clears the shader cache once** (the launcher keeps the version that built the cache in `user/cache/port_version.txt`): shaders built by the previous version could conflict with the new one. The first session after the update hitches a little while the cache is rebuilt. The "Clear shader cache" button stays in the settings.
- **The strong FPS drop at area changes came back in 0.72; fixed.** The finer textures 0.72
  turned on (High at mip 1, Maximum at mip 0 with the banks kept 3 s and without the pool's protection) made the game
  copy up to 1.1 GB of textures in one frame when entering a new area: a worst frame of 134–293 ms at the forest's
  entrance, against 58–75 ms in 0.70. With mip 1 alone the hitch remained. High and Maximum go back to
  0.71's behaviour (mip 2, without the 3 s, with the pool's protection): "much smoother, a drop of 2–3 FPS for
  2 s" in the user's test. Anyone who wants the finer textures can use `SOTC_LOD_LEVEL=1` or `0` in the
  extra variables.
- **Area changes: a lock-free memory table lookup** for buffers that go past the mapped area
  (`SOTC_CLAMP_GAP=0` turns it off) and **a cap of 128 MB per frame** for the textures whose postponement expired, which
  used to all upload in the same frame (`SOTC_UPLOAD_EXPIRED_MB`, 0 = no cap).
- **Diagnostics (off):** `SOTC_DRAW_SPLIT=1` separates the binds (clamp, buffer lookup, decoding,
  image and view lookup) and the game's readbacks done on the draw thread; `SOTC_RB_DIRTY_RETRY=1` hands
  the re-read of a dirty readback back to the game's thread (experimental: a crash at `0x94c71` in one of the two runs).
- **Experimental (off): the visibility map straight in the game's memory** (`SOTC_VIS_DIRECT=1` with `SOTC_PC_MEMORY=1`): the shaders that rewrite the map the game scans every frame write into the game's memory, without the GPU readback. With `SOTC_VIS_PROGRAMS=0x2e0f474b,0xf94d23d4,0x93aec24b,0x729c541e,0x4defcf7f` the forest's entrance went from 31 to 14 frames above 50 ms in the user's test. Diagnostics `SOTC_SLOW_OPS=1` (the most expensive shaders of the slow frames) and `tools/entry_report.py` (a summary of the log by stretch).
- **Experimental (off): textures read by the GPU straight from the game's memory** (`SOTC_TEX_DIRECT=1`, with `SOTC_PC_MEMORY=1` and `SOTC_PC_MEMORY_PREIMPORT=1`, which imports the game's 10 GB of memory at boot in ~2.6 s): without the CPU copy on an area's first entry. The forest's entrance in the user's test: 14 → 9 frames above 50 ms.
- **Experimental (off): releasing the unmap's memory without waiting for the whole GPU** (`SOTC_RELEASE_DEFER=1`): at an area change each release waited for all of the GPU's work, 28–63 times per frame (10–20 ms per frame). **Also fixed** the hang when loading a save with `SOTC_VIS_DIRECT=1` (end-of-pipe labels written out of order).
- **The ending without stretched textures and without closing in the passage to the intro (on by default)** (`SOTC_POOL_FREEZE=1`, T51): at the end of the game the game gives back the memory of textures it still draws; when another texture takes that memory the port reloaded the new content into the texture still in use (stretched textures, flicker and the crash in the passage from the ending to the intro). Those textures now stay as they were for 400 frames.
- **Less video memory held after area changes (on by default):** textures of 2048×2048 or more get memory of their own and go back to the driver when they leave; before, up to 1.8 GB stayed reserved and empty, going over the limit on 8 GB cards (`SOTC_IMAGE_DEDICATED=0` turns it off).
- **Memory release without waiting at area changes and textures read directly by the card (on by default; the direct textures only with 24 GB of RAM or more).**

## 0.72.1 — 2026-11-03
- **Cards with less than 8 GB of video memory: an automatic light profile.** 0.72's texture improvements
  (Maximum at mip 0 with the banks kept 3 s and without the pool's emergency protection, High at mip 1) used
  5–7 GB on an 8 GB card and overflowed 6 GB ones. Now, with less than 8 GB, Maximum stays at mip 1 (without the
  3 s, with the protection), High goes back to mip 2 (as in 0.71), "Video memory use" High/Maximum (the Extreme
  mode's) becomes Default and there is no staging area reserve in video memory. Cards with 8 GB or more
  keep everything.
- **Launcher: "Card memory" in the quick settings** (Play tab): Automatic (by the card, default), Light or
  Full, with a line saying what applies to the card found. The session log shows the profile.

## 0.72 — 2026-11-03
- **Improvements the T38 fix unlocked, now on by default** (tested on every Time Attack
  colossus, at Maximum with PS4 Pro mode, without a crash and without mosaic). They were off because
  they crashed the game or caused mosaic, and the cause was the same double release of pages:
  - **Fast GPU readbacks** (`rb_hot`): about 25% more FPS at the Shrine (the update turns it on
    in old installations too).
  - **Sharper textures:** the mips measured on screen (`SOTC_LOD_FEEDBACK`) and finer mips,
    mip 1 at High and mip 0 at Maximum (2 for both before).
  - **Maximum:** the texture banks stay sampled for 3 s before leaving (`SOTC_LOD_LINGER=180`).
  - **The heap guard's shortcuts** back (`SOTC_GUARD_STALE`, `SOTC_GUARD_USER_POINTER`).
- **A new upscaler: AMD FSR 4.1 (experimental).** Through AMD's official SDK (FSR SDK 2.4.0, Vulkan), with
  AMD's signed DLLs next to `bb-probe.exe` (`amd_fidelityfx_loader_vk.dll`,
  `amd_fidelityfx_upscaler_vk.dll`; licence in `bin/licenses-amd`). The SDK picks the version the card
  runs: **FSR 4.1** (machine learning) on Radeon RX 6000, 7000 and 9000 and recent Ryzen AI;
  **FSR 3.1.6** on the other cards (NVIDIA, Intel, older Radeons). It uses the same inputs as DLSS (the scene
  before the HUD, depth, motion vectors, camera), the same resolution modes and the same
  sharpness. Launcher: Upscaler > "AMD FSR 4.1". Tested on the RTX 2060 Super (FSR 3.1.6, 1280×720 → 1080p,
  ~57 FPS at the Shrine, no errors); still to be tested on a Radeon RX 6000 or newer. `SOTC_FSR_VERSION=3`
  forces FSR 3.1 on a Radeon (comparison); `SOTC_FSR_JITTER` and `SOTC_FSR_DEBUG=1` for tests.
- **Area changes: one stall fewer.** The staging area for uploads to the GPU now keeps a reserve
  (128 MB in system memory, 64 MB in video memory), created gradually at the start of the game. Before, it was
  released after a few seconds without use and recreated in the middle of the area change: with video memory
  near the limit, that cost 95 ms in one frame. `SOTC_STAGING_KEEP_MB` / `SOTC_STAGING_KEEP_VRAM_MB` (0 =
  as before).
- **Area changes: texture copies with fewer page faults.** Before copying a large block of texture,
  the port asks Windows for the pages at once (`PrefetchVirtualMemory`) instead of one fault per 4 KiB
  page. At the forest's entrance, 311 MB went through with 6.5 thousand faults (175 MB with 59 thousand before). A small
  improvement. `SOTC_COPY_PREFETCH=0` turns it off.
- **The game modes leave the grass as on the PS4.** Pro and Extreme no longer change the grass, the weeds and the
  grass shadows (that is now only for Custom). The update sets the grass of anyone who already had
  the setting saved back to "As on the PS4".
- **Integrated GPU (AMD/Intel): the right video memory budget.** It used to be 2 GB (the dedicated
  cards' formula); it is now at least the local memory the driver announces (`SOTC_IGPU_BUDGET_MB` sets it by
  hand). On a Ryzen 7 5700U: 3.9 GB instead of 2 GB, without the texture collections at every load.
- **Launcher:** the Advanced tab's buttons are on two lines ("Clear shader cache" disappeared in a narrow
  window); an extra variable written with `=` in front still counts; "Clear cache" warns if the game is open.
- **Diagnostics (off by default):** `SOTC_FORMAT_LOG=1` (formats the card does not support),
  `SOTC_FORMAT_FALLBACK=1`, `SOTC_NAN_GUARD=1`, `SOTC_AMD_AS_NV=1` and its parts (each shader test switch
  gets a cache folder of its own, without needing to clear the cache), `SOTC_RB_AGE=1` (which of the
  game's instructions wait for GPU readbacks and who wrote the page), `SOTC_CLEAN_GUEST_READS=1` (the game's simple reads
  of bytes the GPU did not write come straight from memory, without waiting for the GPU; experimental).

## 0.71 — 2026-11-02
- **Textures in coloured mosaic and crashes after loads (T38, fixed):** the problem existed in every
  version and was much worse in **Time Attack**, where the game always closed around the 5th colossus. Cause:
  the game's 64 KiB page pool freed some pages twice. When shrinking a texture
  (dropping mips), the game gives the pages back without removing them from its address; another texture (or the heap)
  takes them; when the first texture is discarded whole, the game asks the system (`sceKernelVirtualQuery`)
  which page is at each address and frees again the ones that already belong to the other. Each such page had
  two owners: pieces of other textures on screen, an overflowing heap (crashes `0x490a0`, `0x490e0`, `0x1d8bf`,
  `0x5fc064`), garbage texture descriptors (`data_fmt` 36/54) and the free page count rising at every
  load. The port now remembers the last address each physical page was mapped at, and the release skips the
  pages that have already gone to another block. Test: every Time Attack colossus at Maximum, without mosaic and
  without a crash. `SOTC_POOL_OWNER=0` turns it off. New diagnostic tools (off):
  `SOTC_POOL_FREE_TRACE=1`, `SOTC_WRITE_TRACE=1`, `SOTC_ALIAS_LOG=1`, `SOTC_VIEW_CHECK=1`.
- **Launcher: updating turns the improvements on in old installations too.** Before, an option that
  started coming on by default (like "Frame generation without the interface", which removes the shaking of the HUD and
  the letters) stayed off for anyone who already had the setting saved. Now each version turns its
  improvements on once: in this one, a HUD that does not shake with frame generation, motion blur off (no trail
  of the shadow in dark areas) and the opening logos skipped.
- **Launcher: "Game mode" in the Play tab.** Four modes: **Normal** (as on the PS4: 30 FPS, high
  textures, the console's grass and shadows, without Pro mode), **Pro** (PS4 Pro mode at 30 FPS, high textures,
  16x filtering, fuller grass), **Extreme** (Pro mode at 60 FPS, maximum textures, shadows and grass up to
  farther away, video memory at the maximum, DLSS on RTX and FSR 1 on other cards; needs a strong card)
  and **Custom** (everything as you leave it). Changing a mode's setting by hand switches to Custom.
- **A new look for the launcher**, in the style of bloodborne_pc's launcher and with Shadow of the
  Colossus's face: dark stone, golden Cinzel titles, the sword light's blue on what is active, toggles
  in place of check boxes, rounded fields, icons in the menu and the game's banner with a soft gradient.
- **Launcher: Saves tab.** Lists the saves with their progress (area, colossi defeated, play time) and the
  date; exports the chosen ones or all to a .zip (to keep or take to another PC); imports from a .zip,
  from a folder (one save, another installation's savedata folder) or from shadPS4; makes a backup with one click in
  `user/backups` (the 10 newest are kept), and always before replacing a save on import. The old
  "Game and saves" tab became "Game".
- **Launcher: an automatic backup of the saves when the game closes**, also after a crash (Saves tab,
  on by default; the 10 newest are kept in `user/backups`).
- **Launcher: a "Report" button** in the bottom bar: a .zip with the logs of the last sessions, the last
  crashes (with the dump), the settings (without the player's name) and a summary of the PC, to attach to an issue.
- **Launcher: a "What's new" window** on the first start of each new version, with what changed.
- **Launcher: search (Ctrl+F)** at the top of the side menu: finds any option by its name, its explanation or
  everyday words ("shaking hud", "no sound", "vsync"), opens the page, scrolls to it and highlights it.
- **Launcher: its own title bar** in the theme, with the minimise, maximise and close buttons (Windows
  still moves, snaps and resizes the window).
- **Launcher: "Advanced view"** in the side menu: off, the Advanced and Debug tabs are hidden (the
  search still finds their options).
- **Launcher: a Help tab** with the most common problems and what to do, in cards: asking for help (report
  and issues), a game that does not start, black screen, no sound, stalls, low FPS, shaking HUD, coloured
  or blurred textures, controller, saves and updating. Each topic has buttons that go straight to the right option, and the
  search (Ctrl+F) finds the topics.
- **Launcher: a first-time setup in five steps** (I The Awakening, II The Shrine, III The Ancient Sword,
  IV Agro, V The Forbidden Land), in the style of bloodborne_pc's wizard: language and what is needed, the game
  (found by itself, with the update, DLC, saves and sound), **the PC check** (processor, memory, graphics
  card and whether the game is on an NVMe, SSD or HDD) that **picks the Game mode** the PC can handle, controls
  and the summary. "Set up again" in the side menu opens the wizard.
- **Launcher: a controller test** in the Controls tab: a drawing of the controller (PlayStation, Xbox or Switch) with
  the buttons lighting up, the triggers filling and the sticks moving, read through the same SDL as the game.
- **The game's monitor** (Display and FPS > Screen, with two monitors or more): the window and fullscreen open on the
  chosen monitor (`SOTC_MONITOR_AT`), and the frame pacing follows its rate.
- **Launcher: minimise to the Windows tray** (Advanced): an icon near the clock, with Open and Quit.
- **Flexible memory:** when splitting a flexible mapping, the right half pointed at the left half's
  storage (it did not happen in this game in the tests, but it was wrong).
- **Launcher: opening logos skipped by default** (new installations).
- **Launcher: motion blur now comes off by default** (Effects > "Motion blur", it can be turned back on). It was the
  cause of the character's shadow leaving a trail when moving in dark areas; the fix only existed in the
  local configuration and did not go into the package. Equivalent to `r_motionBlurEnable=0`.
- **Launcher: frame generation without the interface now comes on by default** (`fg_hudless`), so letters and
  icons do not shake with FSR 3 (F8). Before, it only applied to those who ticked the option, so the new package
  did not carry the fix. A "HDR (experimental)" option in the Screen section.
- **Fewer stalls at area changes (from Oussama268's fork, opt12):** v0.70's shader cache pack
  no longer wins over the new files (thousands of shaders were translated again every session, ~900 ms
  stalls), small textures written by the CPU are now checked whole (old/coloured textures),
  the game's mutexes spin 20 µs before sleeping (`SOTC_MUTEX_SPIN_US=0` turns it off) and large staging buffers
  are kept between frames (`SOTC_STAGING_LARGE_POW2=0` turns it off). The shader cache is rebuilt on the
  first start.
- **DLSS: a current colour bias over the whole scene (`SOTC_DLSS_BIAS`, default 0.4; 0 turns it off).** The
  character's shadow has no motion vector, so DLSS kept it in the history and left a trail in
  dark areas, even with preset E. DLSS now favours the current frame more. If there is still a
  trail, try `SOTC_DLSS_BIAS=0.7`; if the image turns grainy, use a lower value.
- **DLSS: preset E by default (`SOTC_DLSS_PRESET`)**. The letters E to O force a preset of the DLSS model
  in every mode; `default` returns to NVIDIA's default preset per mode. Without the switch, the game uses
  preset E.
- **Shadow/character leaving a trail in dark areas (fixed):** there are two causes. (1) The **game's own
  motion blur**, visible in dark scenes and at 60 FPS: off by default (`fx_motionblur`).
  (2) **DLSS's default model** left ghosting in dark scenes, Quality included; with preset E
  (the CNN model) the trail goes away and DLSS stays active. Presets K and J (transformer) did not solve it.
  The launcher's default DLSS mode went from Ultra Performance to Quality.

- **HDR10 for the SDR game (#347), experimental:** `SOTC_HDR=1` shows the game on an HDR10 screen (PQ,
  Rec.2020), expanding the SDR in the final pass: SDR white sits at `SOTC_HDR_PAPER` nits (default 200)
  and the highlights gain up to `SOTC_HDR_GAIN` times (default 1.5; 1 = no gain). `SOTC_HDR_WHITE` is
  accepted as another name for `SOTC_HDR_PAPER` (like Oussama's fork). Needs HDR turned on
  in Windows and an HDR monitor; without that the game says so in the log and stays in SDR. **Not tested on
  an HDR screen yet** (the development monitor has no HDR). In the launcher: Video > Screen > "HDR (experimental)".
  The shader cache is rebuilt on the first start.
- **Docs: remapping keys and mouse buttons (#333):** `key.<input>=` and `mouse.<input>=` in
  `sotc.ini` already worked (L1/R1 included); they are now documented with examples. There is no in-game
  remapping menu (the menu is the game's own).

## 0.70-opt12 — 2026-11-01 (Oussama268's fork)
Everything in 0.70, plus the work against the small hitches (stutter):
- **Frames at a regular pace (tabnul):** frames go out at the pace the game delivers them, instead
  of waiting for the next vblank. The variation between frames dropped from 5.2 ms to 1.2–1.8 ms and the
  stalls above 100 ms from 15 to 2 per 5 min demo. Also from tabnul: the `SOTC MEM` memory scan
  left the presentation thread, GPU readbacks finished in parts and a
  deeper swapchain against the NVIDIA driver's periodic pause.
- **The 60 FPS mode with the same pace:** below 60 the frames alternated 16.7 / 25 ms. They now go out
  when they are ready, without going over 60. Demo at 60 FPS: frames above 50 ms 23 → 12, worst
  frame 194 → 113 ms, 1% low 22.3 → 26.3 FPS.
- **No ~900 ms freezes from 0.70's shader cache:** the cache pack won over the
  newer files, and thousands of shaders were translated again every session. The newer file
  now wins (HiddenUserHere's fix, PR #339 of the main repository).
- **Old small textures or ones with coloured stains:** the whole texture is checked, not just the
  first 8x8 pixels; and the per-frame texture upload limit no longer leaves black textures
  behind (PR #339).
- The game's locks wait 20 µs before sleeping (`SOTC_MUTEX_SPIN_US`, `0` turns it off) and the large
  upload buffers are kept between frames (`SOTC_STAGING_LARGE_POW2=0` turns it off), from PR #339.
- Shrine: 40.1 → 43.5 FPS. A 45 min session without failures.
- The shader cache is rebuilt on the first start.

## 0.70 — 2026-10-29
> ⚠️ **Note: install the game on an SSD (NVMe if possible).** Every new area reads hundreds of MB
> of textures and models from the game's folder; on an HDD the area changes stall much more and can
> stop for seconds. Put the game's folder (the dump) and, if you can, the port's folder on an SSD.

- **Area changes without the FPS dropping to near zero.** Before, each area change brought the FPS down and
  sometimes forced 1–3 s loading screens; the worst frame went over half a second (534 ms).
  Now the worst is 58–75 ms, without a forced loading screen, and the ending goes up to the
  credits. Each change still loses 1–6 frames: that is the next job. The causes were the
  game's memory table lock, memory copies remapping gigabytes, the GPU's region lookup
  redone on every write, the protection of the game's memory walking the same stretch
  thousands of times and many new textures in a single frame. Now at most 32 MB of
  new large textures go in per frame, and those left for the next frame appear black for
  an instant. Each fix has a switch to turn it off (`SOTC_LOCK_WAKE=0`,
  `SOTC_VIEW_CHUNK_MB=0`, `SOTC_REGION_LOG=0`, `SOTC_REGION_FAST=0`, `SOTC_PROTECT_FAST=0`,
  `SOTC_WRITE_FAST=0`, `SOTC_BATCH_SPLIT=0`, `SOTC_GUARD_DEDUP=0`, `SOTC_UPLOAD_BUDGET_MB=0`).
- **A rare crash in the game's allocator after a load** (`0x49800`): two shortcuts of the game memory's
  protection could let the GPU write into a block the game had just freed. They come
  off (`SOTC_GUARD_STALE=1` and `SOTC_GUARD_USER_POINTER=1` turn them on). A 36 min session with
  6 loads without a crash; if it crashes, send the log.
- **DLSS in PS4 Pro mode at 30 FPS without the image shaking:** the repeated frame showed the image without
  DLSS.
- **Frame generation (F8) with FSR 1: the HUD stays still.**
- **LOD feedback** (`SOTC_LOD_FEEDBACK=1`, experimental) no longer costs ~7 FPS.
- Diagnostics: `SOTC_DRAW_SPLIT=1` (with the FPS on screen) shows in the log where the draw thread's time
  goes.

## 0.60.6-C3 — 2026-10-27
- **The stamina bar with DLSS (C2's fix):** the bar's area now uses the width of a
  1080-line screen in the output's aspect (1080 × W/H) instead of the render width. With
  DLSS the render is smaller (1704x720 at 2560x1080) and the yellow bar again stopped far from the
  circle; at 16:9 with DLSS without PS4 Pro mode C2 also broke it.
- **The 30 FPS limit:** "30" (F1 menu or F7) holds 30 FPS even when the game asks not to
  limit (PS4 Pro mode); before, it stayed at ~42.

## 0.60.6-C2 — 2026-10-26
- **Wide screen (21:9, 32:9): the right health and stamina bars (#301, #202).** The health bar
  had an extra grey piece and the yellow stamina bar stopped far from the circle and filled
  backwards. The aspect of the game's screen object stays 16:9 (the game draws the health bar with
  it) and two 1920-wide rectangles of the interface now use the screen's width.
- **Controller rumble can be turned off (#292, Lucas-blip-png):** in the launcher (Controls) and
  in the F1 menu (Controller section), at once.
- **More FPS at the Shrine (Lucas-blip-png):** the GENERAL storage image barrier is
  done once per fence instead of before each draw (each one ended the render
  pass, ~20 thousand per second), and the depth buffer read while the stencil is written
  stays in a single layout. `SOTC_GENERAL_SYNC=0` / `SOTC_DEPTH_RO=0` turn them off.
- **Frame generation without the interface (Lucas-blip-png's option, experimental):** Display and FPS →
  "Frame generation without the interface". The letters and the bars no longer shake with FSR 3
  (it also works in PS4 Pro mode). It may fade the title screen's logo.
- **DLSS Ultra Performance (3×) (#306)**; DLSS only upscales 2× + FSR 1 when no mode accepts the
  scale (Pro mode at 4K).
- Tests: `SOTC_RENDER_KEEP`, `SOTC_RENDER_EXTRA` and `SOTC_WIDE_ASPECT` (finding the game's screen
  size values).

## 0.60.6-C1 — 2026-10-26
A community version: fixes and features from tabnul, Oussama268, NathanMBR and
JihedMrouki, tested with **Maximum textures + PS4 Pro mode + 60 FPS** (RTX 2060 SUPER).

- **Fix of the game's page allocator (tabnul, PR #288 / fork #112):** the game's free page
  counter drifted from the real map and the game read before the start of the map (crash
  `0x1a371`). With the fix and the texture memory reserve at 0 (also in PS4 Pro mode), the
  streamer no longer drops every texture to level 3 every second. Result: **an
  hour at Maximum + Pro without a crash** and almost all the coloured garbage after loads is gone.
- **Maximum texture in PS4 Pro mode (experimental):** applies again (the launcher replaced it with High).
  `SOTC_MAX_IN_PRO=0` returns to the old behaviour.
- **NVIDIA DLSS (RTX 20 or newer), from tabnul (fork PR #81):** the game renders smaller and
  DLSS upscales; the interface is drawn at the output resolution, the game's TAA off, the vignette
  after the upscale. New here: **it works in PS4 Pro mode** (Pro's final composite has the
  scene and the interface in another order and size) and **at 4K** (DLSS upscales 2x and FSR 1 completes it;
  the screen used to go black). In the F1 menu the upscaler shows as "NVIDIA DLSS" and only changes in the
  launcher (it used to write "fsr1" over it). The files `sl.dlss.dll` and `nvngx_dlss.dll` (NVIDIA
  Streamline 2.14.16) included.
- **Grass (tabnul):** the grass and weeds' distance, height and detail change at once in the F1 menu;
  the grass's shadows and fading in the launcher; grass buffers 4x larger (the distant grass no longer
  disappears in strips).
- **More FPS: fast GPU readbacks (experimental),** a new option in the quick settings, with
  Oussama268's final check and per-page locking (`SOTC_RB_HOT=1`). Off by default.
- **Bind reuse** on again by default (Oussama268; the sandy ground fix
  was checked). Also from Oussama268: the command processor does not wait for empty queues and the
  arenas' cold memory comes back without waiting for the GPU.
- **The US version CUSA08034 (NathanMBR, PR #270)** — details below.
- **Weak CPUs and GTX 10xx (JihedMrouki, PR #258):** an invariant position in the pipelines with
  barycentric emulation (a texture/depth difference on the ground) and the shader cache does not read
  files that do not exist from the disk. The shader cache is rebuilt on the first start.
- **F7** goes through **30 → 60 → unlimited** (it used to only turn the 30 limit on/off).
- **The launcher's Debug tab:** Bluepoint's debug menu (**F6 or Start+Select** on the controller; Select
  alone still opens the map), **skip the opening logos**, **go straight to the
  game** (`+nointro`, also skips the Start screen), a texture memory watch, F5 (a capture of the frame's
  textures, limited to 1 GB) and F9 (reloads the textures; with "Compare DLSS" on,
  switches DLSS / FSR 1).
- F1 menu: the grass's shadows and fading show the game's value when they have not been saved yet.

### US version (CUSA08034), NathanMBR
- **The US dump CUSA08034 (1.00, the only US version) works.** The executable is the
  same as the European version 1.01 (code and data identical byte for byte; the `.psarc` files
  too), so all the fixes, the patch modes (60 FPS, 16x filtering, render
  size) and the red zone protection apply to both. Only the logos and legal screens change
  (the game picks the region through `gameversion.txt`). Tested up to the second colossus.
- The GPU fixes formerly restricted to CUSA08809 (LDS barriers, wave64, T# tables,
  early depth tests of the decals, periodic flush) now apply to both
  serials (`IsSotc()`). Without the early tests, the decals behind an object painted the
  whole box over it (edges and background textures in front). The log shows
  `SOTC early fragment tests: on`.
- **Saves separated by version** (`user/savedata/1/CUSA08034`) and a shader cache of its own
  (`user/cache/CUSA08034`). **DLC only of the same region** (folder `addcont/CUSA08034`, content ID
  `UP9000-CUSA08034_00-...`).
- **Launcher:** finds the US dump through `param.sfo`'s `TITLE_ID`, with any folder name
  (like `CUSA08034-app`), shows "✓ CUSA08034 version 01.00: all modes available" and no longer
  marks the dump as unsupported. With both dumps, the European one comes first.
- The tools (`tools/`) and the benchmarks' save template accept both serials. New tests
  (`tests/test_games.py`) fail if any code goes back to testing a single serial.
- The US version does not have the 3 Arabic texts of the European update 1.01.

## 0.60.6-opt11 — 2026-10-24 (Oussama268's fork)
- **+25% FPS at the Shrine and steadier frames:** the GPU readbacks ahead
  ("hot readbacks", from the 8 Oct merge) come back on by default (`SOTC_RB_HOT=1`; `=0` turns it off).
  Before writing, each page is checked under its region's lock: if the game has already written
  to it, the copy is skipped. That was the race that left the rainbow on the textures in 0.60.5.
  Shrine 34.6 → 43.3 FPS, the title screen demo 54 → 60.7.
- Reused descriptors on by default (`SOTC_FAST_BIND`, `=0` turns it off).
- tabnul's fixes: grass, HDR, the DLSS menu, skipping the logos (#91, #92, #94, #96).
- Launcher: a low memory warning (#95).
- From upstream #258 (JihedMrouki): the shader cache checks whether the file exists, a work hint
  in Liverpool's queue, an invariant position in the vertex shaders (GTX 10xx).
  **The shader cache is rebuilt on the first start.**
- Diagnostics: `SOTC_PROFILE_SLOW_MS=<ms>` only keeps samples of the frames longer than that.
- The stall when riding remains: in the slow frames the game's threads wait for each
  other (the game's own mutexes and event flags) and there are ~200 MB copies at scene changes.

## 0.60.6 — 2026-10-22
- **The end of the rainbow noise on the textures and of the crashes "out of nowhere" (`0x49500`).** The cause was the
  GPU's "hot" readbacks (`SOTC_RB_HOT`): together with each readback, the port wrote into the game's
  memory, speculatively, regions read before; after loading a save or a new area the game had already
  reused that memory for new textures and for its heaps, and the GPU's old drawing
  landed on top. They now come off (the demo's average FPS drops ~4%). Found with the
  user's recipe: new area → wait → leave → reload the save.
- **A grid of black dots on sandy ground** (0.60.5): PR #232's bind optimization comes
  off by default (`SOTC_FAST_BIND=1` turns it on; its fix awaits a test).
- **PR #219 (memory leak) off by default**: with it, coloured noise and giant black
  polygons ("exploding vertices") appeared much more often
  (`SOTC_CP_FREE_TASKS=1` turns it on).
- **The game's menu (F1):** only what works in SotC (the upscaler, preset, resolution and
  effects options inherited from Bloodborne did nothing); **FPS (30/60/unlimited), Upscaler and Sharpness**
  change at once; the **Maximum** texture disabled in PS4 Pro mode (it closed within minutes); a hint explains
  what applies at once.
- **Hard disk:** after the game loads, the game's files (13.7 GB) are read once in
  order and stay in RAM: new places no longer stall waiting for the HDD (`SOTC_PREFETCH=0` turns it off).
- **Loads:** at each save or new area, the unused textures are discarded
  (`SOTC_LOAD_FLUSH=0` turns it off).
- **Event log `user/events.log`:** the full configuration, the system (CPU, RAM, HDD/SSD), menu,
  keys, controller, loads, textures, performance per minute, explained errors; the launcher's
  language; the last 5 sessions and a copy in `user/crashes` after a crash.
- PRs: #215 (pipeline preloading on the workers: new driver 106 s → 7 s), #198 (4-thread
  CPUs), #205 (LDS barriers on AMD GCN), #207, #212.
- Code review: the world heaps' guard, the hang watchdog, memory on PCs with little RAM,
  the launcher's "Unlimited" preserved, a translucent loading screen on short stalls.

## 0.60.5 — 2026-10-21
- **A texture quality selector: Off / High / Maximum** (#235), in the launcher
  (Quick settings → Textures) and in the game's menu (changes at once). **High (stable)**, the default,
  keeps 0.60.3/0.60.4's protection (textures one level coarser when the game's texture memory
  is running out); since that memory is almost always full in large areas, 0.60.4
  was less sharp than 0.60.3. **Maximum (sharp)** removes the protection: always the finest level,
  but it **may close in very wide views** (the sword against the sun, the Shrine, the last
  colossus's area; `0x1a371`, #186), mainly in PS4 Pro mode; if it happens, go back to High.
  **Off** = only the game's 256×256 versions. The old "High quality textures" box becomes
  High (or Off).
- **Memory leak** (~60 MB per minute, more than 7 GB in half an hour; hitches in long
  sessions): each nested command buffer left its coroutine in memory (PR #219,
  Oussama268).
- **More FPS:** the previous draw's descriptors are reused when the next draw uses
  the same pipeline and the same resources (PR #232, Tadomikaari312-Hy): demo +3.3% on average, +12% on the
  minimum (72.8 / 37.1 → 75.2 / 41.7). `SOTC_FAST_BIND=0` turns it off.
- **Loading after updating the graphics driver: 106 s → 7 s** (the saved pipelines are
  built by the helper threads; PR #215, Oussama268). `SOTC_ASYNC_PRELOAD=0` returns to the old way.
- **AMD GCN** (RX 470–590, Vega, APUs): shared memory barriers those cards did not
  get, a probable fix for the white characters and smoke (PR #205, Lucas-blip-png; to be tested
  on GCN cards by the players). `SOTC_AMD64_LDS=0` turns it off.
- **4-thread CPUs:** the command recorder and the command processor no longer take a whole
  core waiting (stuck at the loading screen → 73 FPS; PR #198, Lucas-blip-png).
- **Launcher:** does not stop when the console refuses writes (#104, PR #207); a dump or modules still
  encrypted say which file it is (PR #212).
- **Loading screen:** short stalls in the game only darken the image; it becomes opaque after 3 s
  without a frame (it used to flash black on 1 s stalls).
- **Hang watchdog:** after 15 s without a frame from the game, the threads' stacks go to the log
  (`SOTC_WATCHDOG=0` turns it off), to find the "closed out of nowhere".
- **Code review:** the world heaps' protection skipped the guard on the heap's following pieces
  and left new pieces unguarded for up to 2 s; PCs with little RAM got the memory size
  before the reduction; the menu's 60 FPS button turned "Unlimited" into "60".
- The game's menu and shortcuts (F1, F7, F8, F10, F11) explained in the README, with an image.

## 0.60.4 — 2026-10-20
- **Cyan blocks on the stones and flickering flowers** (with "High quality textures"): 0.60.3's
  adjustment that avoids the crash switched the textures' level of detail every one or two seconds in
  large areas (4, 3, 2, 3, 2…), and each switch made the game discard or reload textures that
  were being drawn. It now only lowers the detail with less than 8% of free memory and only
  returns above 16%. Tested from New Game+ to the 2nd colossus: 3 switches instead of ~8, no cyan
  blocks, no flickering flowers and no crashes.

## 0.60.3 — 2026-10-20
**The game can be beaten from start to finish.** Played from the save before the last colossus to the fight with
Malus, the final scenes and the credits, with "High quality textures", PS4 Pro mode and 60 FPS
on. Thanks to **Lucas-blip-png**.

- **A crash with "High quality textures" in wide views** (the sword raised against the sun, the last
  colossus's area; `0x1a371`, #186): when the game's texture memory starts running out, the
  visible textures ask for one level of detail less (two when it is almost full) and the game frees
  space before it fails. Still sharper than with the option off (PR #191, Lucas-blip-png).
- **A crash in the load after the credits** (`0x49500`): the protection of the game's memory did not
  see the pools the world creates, because they grow in scattered 1 MB pieces;
  each one is now protected where its free blocks are (#146).
- **+2.7% FPS in the temple:** GPU readbacks in 64 KB windows (PR #196, Lucas-blip-png).

## 0.60.2 — 2026-10-20
- **Quick settings inside the game:** in the menu (Insert, F1 or L3+R3), without leaving the game: 60 FPS,
  frame generation (off / DLSS-G / FSR 3), high quality textures, reusing
  distant shadows and volume. They apply at once and are saved in the launcher for next time. 16x AF,
  PS4 Pro mode, resolution and video memory use stay in the launcher (they need a restart).
- **The mouse in the menu:** with the menu open the mouse is free and visible for clicking; on closing, it goes back
  to controlling the camera.
- **An animated loading screen also while the shaders are built** when starting the game (the window used
  to sit still, sometimes for minutes after updating the driver), with an opaque black background and an
  animation in the centre (a spinning circle, a pulsing title, "Loading…").
- The menu with a title and the quick settings in the launcher's language.

## 0.60.1 — 2026-10-20
Thanks to **nosekefik, Oussama268, plassardewen-cpu and lunar-me**.

- **A menu inside the game** (Insert, F1 or L3+R3): FPS, card and video memory, fullscreen,
  resolution, scale and sharpness, camera and mouse, effects (fog, vignette, occlusion, the water's
  reflections). It was Bloodborne's menu, hidden in the port; it is now SotC's and comes on
  (`BB_OVERLAY_MENU=0` turns it off). Texts in English (PR #94, nosekefik).
- **Bloodborne leftovers removed** (~11,700 lines: the old launcher, Bloodborne's patches and mods,
  icons, documents), based on Oussama268's PR #60. The game's executable
  (`bb-probe.exe`) now has SotC's icon.
- The search for the game ignores Windows' `WpSystem` folder (PR #110, plassardewen-cpu).
- The GitHub page in English only.

## 0.60 — 2026-10-20
Thanks to **Lucas-blip-png, Einar and KingJhoss**.

**Fixes**
- **Textures on the GTX 1060/1070/1080 (Pascal):** surfaces without texture, flat or almost
  black colours (#57, #68, #102). Pascal lacks the interpolation feature the game uses; it is
  imitated with a geometry shader (PR #169, Lucas-blip-png).
- **The game hanging or closing at the title screen** on some PCs (CPU cores with different
  clocks): the game's clock now comes from Windows (PR #174, Einar).
- **It did not start on PCs with little memory** (a 0.59 regression): if Windows refuses the 9152 MB,
  the game uses the console's size and says so in the log.
- **FSR 3: black squares in the generated frames** on AMD RX 7000 (PR #177, KingJhoss).
- **The PLAY button cut off** with Windows scaling above 100% (PR #171).
- A fix in the code inherited from shadPS4: a decimal atomic min/max on cards without
  `VK_EXT_shader_atomic_float2` ran two operations instead of one.

**New**
- **The 60 FPS mode using the game's own Performance mode** (the PS4 Pro's): the game now targets
  60 FPS, so its timing follows. It should fix wrong physics at 60 FPS (#100, #120); still
  being tested at those colossi (PR #183, Lucas-blip-png). `SOTC_MODES=af16` returns to the old mode.
- **Each copy of the port has its own `user` folder** (saves, cache, logs and the launcher's
  settings in `user\launcher_settings.json`). Before, all of them used the first copy's folder. The
  first time, the new copy inherits the settings and **copies** the saves and sound modules.
- **+6% FPS in the temple:** the protection of the game's memory is no longer redone every frame
  (PR #168, Lucas-blip-png).
- Frame generation without the interface (a health bar that does not shake), **experimental and off**:
  `SOTC_FG_HUDLESS=1` (PR #154, Lucas-blip-png).
- Playing through `SotC.bat`, the log also goes to `user\last_run.log` (PR #175, Einar);
  measurement tools fixed (PR #181, Einar).

**Known:** "High quality textures" can still close the game in very wide views
(the sword raised against the sun, the last colossus's area; #186): turn it off if that happens. White
characters on AMD GCN (RX 470–590, Vega, APUs): under investigation.

## 0.59.1 — 2026-10-20
Thanks to **Lucas-blip-png and Oussama268**.

- **Distant shadows flickering** (#178, #157, #163; AMD and NVIDIA GTX 1080, RTX 40/50): the
  shadow reuse (since 0.58) redrew the distant shadows only every other frame and
  the game does not keep the skipped frame's one. It now comes off (PR #170, Lucas-blip-png). Measured over the
  whole demo: off 61.8 FPS average / 37.2 minimum, on 59.5 / 35.6, so it did not
  gain FPS. A new **Distant shadows** option in the launcher (Off / On / Automatic).
- **AMD: stripes on the shadows and the water** (Oussama268's fork, opt8): direct memory access
  comes off by default on AMD cards (it can be turned on in the launcher).
- **Intel, partial fixes** (Oussama268): valid dispatch sizes and layouts, no
  64-bit integers when the GPU lacks them, a fixed subgroup size.
- **The log shows the graphics card and the driver** (the `GPU:` line), for the reports in the issues;
  `SOTC_GPU_VENDOR=10de|1002|8086` picks the GPU on laptops with two (Oussama268).
- Minor review fixes (Oussama268).

## 0.59 — 2026-10-20
Thanks to **Oussama268, Lucas-blip-png and EdouardSence**.

**Performance**
- **More FPS and fewer stalls** (Oussama268's fork, opt5–opt7): the draws are prepared on a
  thread of their own (#99 Lucas-blip-png), direct memory is uploaded gradually and the shaders and
  compute pipelines are translated on helper threads (the object waits a few frames instead
  of the screen stalling). The title screen demo: average 63 → 65–67 FPS, minimum 30 → 34–37, bridge
  30–32 → 37–40.

**Stability**
- **A crash at the ending and when loading saves** (`0x1a371` / `0x49500`): the GPU sometimes returned
  old data to memory the game had already freed, corrupting the allocator. Pink-shadPS4's
  protection covered only one of the game's memory pools; it now covers all of the
  same kind, including those created when the world loads (the last colossus's area). The game also
  gets 9152 MB of direct memory in every mode (#146, #149). Cause found with logs of
  real crashes; the full playthrough up to the credits is still being tested.
- **6 GB cards** closing for lack of video memory: it tries the exact size and the PC's RAM
  before giving up (#137).
- **The launcher on Chinese Windows** broke with the "™" in the title (#151).

**New**
- **F11** toggles window / fullscreen (#118, EdouardSence).
- **Video memory use:** Economy, Default, High and Maximum (the game used to clear textures
  from 60% of the card, the "6 GB limit" of 8–16 GB cards) (#143).
- **Volume:** 100 to 300%, without clipping (#95).
- **Automatic update:** the launcher says when a new version is out and installs it by itself, keeping
  saves, the shader cache and sotc.ini (#136, Oussama268). Applies from this version on.
- **Ultrawide with PS4 Pro mode:** 21:9 and 32:9 had black borders with Pro mode on;
  the wide screen now takes priority (#142, #145).

## 0.58.1 — 2026-10-19
- **High quality textures** (on by default in the quick settings): since 0.0.13 the port
  never told the game which textures were in use, and it did not load the high
  resolution versions (the leaves of the intro's tree and the blurred stones). Off, it returns to the old
  behaviour, for cards with little video memory.
- **The game window's icon:** a drawing of the port's (the boy raising the sword), so it does not look the same
  as the launcher's in the taskbar. In Display and FPS: default, the game's icon or an image of your own.

## 0.58 — 2026-10-19
A community version: it brings together the pull requests and forks of several people, reviewed and tested together.
Thanks to **Lucas-blip-png, Gabriell-os, Oussama268, jownatan, xeodeo, nakaionyt/y7ngboy and tabnul**.

**Stability**
- **Crashes for lack of video memory** (`EnsureResident: Assertion Failed`, AMD cards and
  4–6 GB cards): buffer memory comes in 64 MB blocks (thousands of allocations before, above the
  drivers' limit) and idle memory is given back with use, checking the data first
  (Gabriell-os #98, Oussama268 #59/#83/#103).
- **The game freezing** ("GPU hook queue overflow"): the memory notification queue grows on demand.
- **A crash after the 1st and the 2nd colossus in PS4 Pro mode** (`0x1a371`): Pro mode gets a
  PS4 Pro's memory (Lucas-blip-png #106).
- A fill packet in the compute queue that corrupted the next packet; RTZ rounding
  off on NVIDIA (the driver hung); a region lock without deadlock on Windows (jownatan #81).

**Performance:** the title screen demo 54–55 → **62 FPS average**, minimum 26 → 31; video
memory ~4.3 → ~2.7 GB (command processor cuts, pipelines compiled in the background,
caches read in parallel, distant shadows reused).

**AMD:** a black block in the screen's corner on RDNA3/RDNA4 (#43) and BC5/BC6H textures (xeodeo);
wave64 uniform branches and periodic submission turned on on AMD (Gabriell-os #98). Still untested
on an AMD here: tell us in the issues.

**New**
- **Widescreen / ultrawide:** 16:10, 21:9 and 32:9 with a wider image, not stretched (tabnul #54).
- **FPS: 30 / 60 / unlimited** in the launcher.
- **Xbox button icons** in the game (A B X Y, RB, LT/RT, Menu, View), drawn for the port;
  a PlayStation / Xbox option in Controls (xeodeo's texture replacement mechanism).
- **Frame generation (experimental):** FSR 3 on any card and DLSS-G on RTX 40/50 (NVIDIA's official
  runtime in the package, with the licences), with the game at 30 → 60 on screen (nakaionyt/y7ngboy).
  It only makes a difference with the FPS at 30, and the health/stamina bar may shake.
- A performance overlay (F10), F7 turns the 30 limit on/off, F8 switches frame generation.
- **The launcher in Spanish, Chinese, Korean and Russian.**
- A window with the game's icon and, in the title, the version and the FPS.
- **A save list with each save's image**, as on the PS4 / shadPS4.
- **A loading screen** with a percentage bar while the shader cache is read.
- The language chosen on the launcher's first screen; PS4 Pro mode and Sharpness (RCAS) in the quick settings.
- The shader cache is rebuilt on the first start.

## 0.57 — 2026-10-14
- **AMD cards: the green/pink colours fixed** in the fog, on Wander and on Agro (issues #6, #7, #9,
  possibly #10). AMD reports 64-thread groups, but only lets that size be fixed in
  compute shaders; the port required 64 in every stage and stopped converting the compute
  shaders. AMD cards now use the same 32-thread path as NVIDIA (compute fixed at 32,
  shared memory barriers, without the uniform branch optimization that left the
  characters black in the shadow). Diagnosis by raulbezerro-dev in issue #7. Nothing changes on NVIDIA.
  **Not tested on an AMD card yet:** tell us in the issue whether it improved.
- **A new option in the launcher:** "Full water reflections (direct memory access)", on by
  default. Off, it gains ~10% FPS (the title screen demo: 54 → 59), but the distant water
  is flatter. Each mode has its own shader cache folder.
- The shader cache is rebuilt on the first start.

## 0.56 — 2026-10-13
- **Open-world water with waves:** the lakes and rivers below the waterfalls were mirror-flat,
  without movement. That water's shader saves the active thread mask with `s_wqm_b64 vcc, exec`
  and then decides from it whether to apply the flow map (the waves). The recompiler treated
  `S_WQM_B64` as "do nothing", VCC held garbage and the shader always wrote a normal pointing
  straight up. The instruction now does what the hardware does: it expands the mask to whole
  2×2 pixel quads. A plain copy fixed the water, but left "coloured garbage" in the canopies
  of distant trees, which use the expansion in the alpha test. Details in
  `docs/sotc/WATER.md`.
- **Direct memory access (DMA) on by default,** as in Pink-shadPS4's configuration for
  SotC. Reads of tables with an index computed in the shader (the *probe* records used by the
  screen-space reflection) always read position 0; they now read the right address. With that the
  upper lake ripples and reflects into the distance. `BB_DIRECT_MEMORY_ACCESS=0` turns it off.
- The shader cache is rebuilt on the first start (the first load stalls).

## 0.0.13 — 2026-10-13
- **A fix for a 0.0.12 crash:** the game could close at the opening or in the menu (a fault at `0x1a371`,
  1 in 3 tests). Cause: the port marked every texture seen as "still in use" for ~3 seconds, and the
  game tried to load more textures than fit in its pool. Now only the textures used
  since the last request count (as in Pink-shadPS4). Tested: 0 crashes in 5 runs of the opening and a
  session of almost 40 minutes walking around the map, with two save loads.
- **Much larger water reflections:** the lake now reflects cliffs, temples and vegetation over almost
  the whole surface, with ripples. A loop safety limit in the shaders cut the
  screen-space reflection's rays short; the limit is now per loop.
- Under investigation: where the water should reflect the sky, it is still dark and flat.

## 0.0.12 — 2026-10-13
- **Sharp textures back, without the game closing:** the memory corruption that made the game close
  right after loading a save (a fault at `0x1a371`) and left textures with "coloured garbage" came
  from the emulator copying GPU data into memory the game was freeing. That was fixed,
  and texture streaming is back on at level 2 (2048 textures up to 512×512): stones and
  walls much sharper. Tested for over 25 minutes near the waterfall, without a crash.
- **Water:** splashes, rings and foam around Wander when swimming; the lake reflects the sky and the
  sun's glare. The environment reflections (the local IBL pass) now use the right *cubemap* for
  each *probe*, a fix brought over from Pink-shadPS4 (`dynamic_tsharp_array_size`).
- Under investigation: the water near the camera still has no ripples.
- Options for testing: `SOTC_LOD_STATS=0` (streaming off), `SOTC_LOD_LEVEL`,
  `SOTC_UNMAP_READBACK=1`, `SOTC_TSHARP_ARRAY=0`.

## 0.0.11 — 2026-10-13
- **A fix for 0.0.10, grass with a "coloured garbage" texture:** at streaming level 3 the
  game freed mips the GPU still used (seen on the grass near the waterfall). Texture
  streaming now comes **off**, as in 0.0.9: normal grass, the waterfalls' curtains visible and
  no crashes when loading a save. To test streaming: `SOTC_LOD_STATS=1` (with
  `SOTC_LOD_LEVEL=2` it is sharper, but may close the game).
- Under investigation: the still water (a mirror-like lake, without waves) and the waterfalls' spray.

## 0.0.10 — 2026-10-13
- **Saving fixed:** the game could never save ("no free space"); it saves now.
- **A save list on screen:** "Load game" and "Manual save" show the saves (region,
  play time, date) to choose from, with "+ New save" when saving. Arrows/d-pad to
  choose, Enter/X to confirm, Esc/O to go back, double click with the mouse.
- **Deleting a save:** in the list, Delete (keyboard) or Triangle/Y (controller), with confirmation.
- **High resolution textures (streaming):** the port now answers the GPU's texture
  statistics command (`GET_LOD_STATS`) the game uses to decide what to load.
  At level 2 the 2048 textures reached 512×512 and the waterfalls gained their water curtains.
- **The game closing by itself after loading a save:** streaming at level 2 corrupted the
  game's memory (3 crashes in 4 tests near the waterfall). The default is now level 3, which ran
  4 of 4 tests without a crash; at it the 2048 textures stay at 256×256, as before streaming
  (the waterfalls' curtains have not been checked at this level yet). `SOTC_LOD_LEVEL=2` returns to the
  sharper level, with the risk of a crash.
- **Black shadows fixed:** grass, stones and walls in shadow were black. Three shader
  recompiler fixes brought over from Pink-shadPS4 (the fetch shader's 1.0 constants that were
  ignored, `V_ALIGNBIT`/`V_ALIGNBYTE` with a shift of 0, `V_CVT_PK_U8_F32`).
- **GPU particles:** shared memory barriers in groups smaller than a wave; a
  particle system that never appeared came back. The waterfalls' spray and foam still do not
  appear (under investigation).
- The launcher writes the game's log to `user/last_run.log`, with the exit code.
- Diagnostic tools: F12 captures a frame when the game runs under RenderDoc.
- A new icon (a colossus's face).
- **Note:** if switching saves in the same session closes the game, restart before loading another.
- A full review of the project in `docs/sotc/PROJECT-REVIEW.md`.

## 0.0.9 — 2026-10-12
- **Automatic first-time setup:** the first time, `SotC.exe` opens on a welcome screen
  that only asks for the game's folder (or offers the one it found on the PC). Then it sets up by itself
  the DLC (inside the game's folder and next to it), the saves (it copies a shadPS4 save if the port
  does not have one yet) and the sound, and shows the result. **Set up again** repeats the process.
- **A main folder as in shadPS4:** you point to the game's main folder and it finds the
  subfolders of the base game (CUSA08809), the update and the DLC.
- **Update:** the `CUSA08809-UPDATE` or `CUSA08809-patch` folder next to the game is used as in
  shadPS4: its files take priority over the base game's (`SOTC_UPDATE_DIR`). If it has
  `eboot.bin`, that is the one that runs.
- A cleaner main screen: the game's log became a discreet link; the check shows the DLC.
- **A DLC folder** in the launcher (Game and saves), as in shadPS4. It is also found by the automatic
  search: shadPS4's `addcont` folder or a folder with one subfolder per DLC.
- The runtime lists the installed DLC to the game (`sceAppContentGetAddcontInfoList`), reading the
  `CONTENT_ID` from each one's `param.sfo` (`SOTC_DLC_DIR`).
- **DLC in .pkg without installing:** the DLC packages (type `0x1b`) are read straight from the header,
  without extracting. That is enough for the game's DLC, which only unlock items (the ancient bow, the cloak,
  the sword, horses). The search looks in the chosen folder, the game's folder and the neighbouring folders.
- **PS4 Pro mode:** the game's log shows whether it was opened as a PS4 Pro
  (`sceKernelIsNeoMode -> 1`). The option only unlocks the PS4 Pro's Graphics Mode: you need to choose
  **Cinematic** or **Performance** in the game, under Options > Presentation.

## 0.0.8 — 2026-10-12

The first public version.

### Launcher (`SotC.exe`)
- **Automatic search** on opening: it finds on the PC's drives the game (CUSA08809), the user's sound
  modules in an installed shadPS4 (copied to the port's data folder) and shadPS4 saves
  (it asks before importing). **Search the PC** repeats the search.
- **A game library** like shadPS4's: game folders, a list with icon, title, ID and version.
- **Key remapping:** click the action and press the new key (saved as `key.<input>=` in
  `sotc.ini`).
- **A new icon** (original art). The window and the desktop shortcut use your dump's
  `icon0.png`.
- **GPU work submission:** Automatic (NVIDIA), On for any card (AMD/Intel,
  experimental) or Off.

### Performance
The title screen demo, 60 FPS mode, i9-13900K + RTX 2060 SUPER: average 37–45 → **~67 FPS**,
heaviest stretch ~17 → **29–34 FPS**.
- Vulkan commands recorded and submitted on a thread of their own (Pink-shadPS4's `cp_record_thread`).
- Periodic GPU work submission by time (every 0.5 ms), instead of by command count.
- Indirect draws with arguments on the CPU become direct draws.
- Caches: image descriptions per T#, image lookups, shader binary information and
  a per-thread memory pointer.
- A lock-free buffer sync check when nothing changed; `RangeSet::Add` does not reinsert
  intervals already marked.
- Write faults: the faulting page and the following ones, without GPU data, are released together
  (~50 thousand → ~4 thousand faults per second).
- Readbacks:
  - ranges read recently are downloaded together;
  - "clean" reads of the shaders' resource tables, with the bitmap following the pages'
    real protection;
  - the descriptor table fill (compute `0x50784801`) is done on the CPU;
  - reads ahead.
- From Pink-shadPS4: the cvars `doIndexBufferCulling=0 doSunShadowIndexBufferCulling=0` and the BPE
  heap's protection against GPU writes.
- Optional, for testing: asynchronous readback (`SOTC_RB_ASYNC=1`) and a wait marker
  (`SOTC_WAIT_MARKER=2`).

### Fixes
- A GPU queue hang with recording on its own thread: presentation waits for the frame
  to reach the queue.
- A silent death from page protection on a fiber's stack.
- A black screen at boot; a crash in PS4 Pro mode (`alt_tile` in the video buffers).

## Before (development, 07–08/10/2026)
- The game boots in bbport's loader (imports by NID, fibers, SSE4a, an image below 2 GiB).
- The video core from the SotC shadPS4 fork; sound with the user's modules.
- 60 FPS and 16x AF modes as loader patches; a frozen Tkinter launcher (`SotC.exe`).
- Keyboard and controller together, mouse camera, 720p–4K output, PS4 Pro mode, engine effects.
