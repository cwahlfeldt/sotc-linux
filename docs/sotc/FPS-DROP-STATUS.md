# FPS drop: status on 17 Nov 2026 and the way forward

The problem, in the user's words: **the FPS drops sharply** at the forest's area change (the user's
correction on 18 Nov: the stretch I called "the forest" is the forest's entrance).
While it drops, nothing has improved. The only criterion that counts: **in the user's playthrough, in
those stretches, the FPS does not drop.**

## 1. Test rules (so hours are not lost)

### Forbidden
- **The "standing" harness (`I:/tmp/dense/idle.py`)**: it never reached the save. It stopped at the
  title screen or in the demo, because the `st_gameflow() starting game` line also appears at the
  title. Every number taken with it on 17 Nov (`gt1`, `if1`, `dep1`, `dep2`, `idle1`, `idle2`) is
  from the title screen (~480 commands/frame, 90–130 FPS), not the forest (5–8 thousand
  commands/frame, 44–48 FPS). It only served to see whether the exe started.
- **The "skipping" harness (`tools/sotc_bench_shrine.py` with the save-template)**: the save does not
  start in the forest; the script pressed X endlessly and got stuck at a gate. It does not represent
  the problem.
- **The opening demo (`gather_ab.sh`, `cold_run.sh`)**: the intro has neither the area changes nor the
  dense stretches.
- Running any test with the user's game open, or starting the game on their PC without telling them.

### How to measure (the only way that counts)
1. I change the variables in `E:\GAMES\Shadow Of The Colossus\SotC-PC\user\launcher_settings.json`
   (only with `SotC.exe`/`bb-probe.exe` closed, a backup in `I:/lixo-sotc-05-11/`), install the exe
   with a backup and open the launcher. I say "installed HH:MM" and what changed.
2. The user plays **2–3 minutes** in the stretch that drops (the forest) and closes the game.
3. Before looking at any number in `user/last_run.log`, check that it is the right playthrough:
   - the `md5sum` of `bin/bb-probe.exe` = the exe I installed;
   - `SOTC FPS ... cmds/frame` lines with **3,000+ commands/frame** (the dense forest: 5–8 thousand).
     With ~500 it is the title or the demo: it does not count;
   - the tested switch shows as active in the log (e.g. `SOTC CULL QUEUE: on`).
   - **how the session ended**: a "game crashed" / "Crash at" line in `user/events.log` or a
     `Crash dump` = it crashed. The launcher's "game stopped by the launcher" line is the user closing
     it from the launcher (it appears in normal playthroughs). When in doubt, ask the user.
   - **the user's "drop" = an FPS drop.** The drop that matters is the **forest's area change, always
     in the last stretch of the test**: compare each playthrough's last 5 s windows, not averages of
     the whole playthrough.
4. **The number the user sees is the on-screen counter** (the average of the last ~20 frames,
   `bbport_overlay.cpp`). Since 18 Nov 22:16 the log has the line `SOTC SCREEN FPS <s>: lowest X, now
   Y` every second: **compare by that line's "lowest" in the area change's stretch**, not by the 5 s
   `SOTC FPS` average.
5. A short answer to the user: **FPS in the same stretches before × after** (the 5 s windows with 5+
   thousand commands/frame), frames > 50 ms, crash/drop. It went up or it did not.
6. One change per playthrough. If it does not go up, turn it off and move on to the next; no extra
   measurement rounds.

### "Before" reference (the user's playthroughs, 17 Nov, exe without the FPS changes)
Forest stretches with 5–8 thousand commands/frame: **44–48 FPS** (21:59, 22:04, 22:19, 22:23, 22:30,
22:38, 22:47); 57–60 in the other stretches.

### A harness that still counts
- `I:/tmp/ride/ride.py` (an automated `setPlayerPos` ride, the 15-defeated save): really loads the
  save (checked: the plan finishes, ~14 thousand frames). Good for area-change hitches with a
  cold/warm cache, **not** for the forest. Uses `RetailBuild=0` (debug menu): 1 `0x1a2c0` crash in 5
  runs (T41's family).

## 2. What was measured (the user's playthroughs; valid)

| Measurement (the forest's dense stretches, 44–48 FPS) | Value |
|---|---|
| GPU per frame (`SOTC_GPU_TIMES`) | ~10 ms draws/dispatches, ~3–4 ms barriers/copies, **~6–9 ms stopped between submissions** |
| GPU busy (`SOTC_TICKWATCH`) | 71–76% (15–17 ms per frame) |
| The game's threads (`SOTC_PROFILE=*`) | 13.5% in the game, ~35% spinning on locks, ~24% waiting for a GPU readback |
| The game's readback wait | 20–27 ms per frame summed; almost all "gpu" (the port's queue ~1 ms, submission 0.3, apply ~1.5) |
| Visibility computation `0x50784801` (30–86 per frame) | starts **~10 ms of GPU time after** its inputs are ready; the largest per frame 14–24 ms |
| The port's threads | draw ~17.6 ms, command processor ~14.5 ms per 22 ms frame: they are not the limit |

**Cause:** every frame the game waits for the visibility map the GPU computes in the same frame; that
computation sits in the queue behind the previous frame's drawing. The GPU finishes, stops, the game
receives it and only then sends the rest.

## 3. What was done (nothing committed except `SOTC_TEX_GATHER`)

| Change | Switch | Result | Status |
|---|---|---|---|
| Textures gathered by the GPU | `SOTC_TEX_GATHER` | area entry 7–9 → 1 frame > 50 ms | **commit `fc20cf11`**, default in the launcher |
| Pre-translating the compute shaders | `SOTC_COMPUTE_PREFETCH` (default 1) | shader hitches on the 1st visit (cold ride > 50 ms 94 → 67); **does not touch the drop to 48** | working tree |
| The shader cache kept between updates | launcher `SHADER_CACHE_VERSION`; `SOTC_CACHE_CLEAR_EVERY_UPDATE=1` returns to before | 7 cases tested; only arrives with a new `SotC.exe` | working tree |
| A log of translations in the frame | `SOTC_SYNC_COMPILE_LOG=1` | diagnostics | working tree |
| GPU time per stage, causes, dependencies | `SOTC_GPU_TIMES=1` (`sotc_gpu_times*.h`) | diagnostics (table above) | working tree |
| Submitting when the draw thread runs out of work | `SOTC_IDLE_FLUSH` (default 0) | **no gain** (46–55 FPS, the same) | working tree, off |
| Visibility on a second queue | `SOTC_CULL_QUEUE` (default 0), `_VERIFY` | written by another session; 0 differences in the comparison **only at the title screen**; **never tested in the forest** | working tree, off; exe ready in `out/bb-probe.exe` (23:30) |
| Delivered readback (step 2 of the forest plan) | `SOTC_RB_PUSH` | took the GPU down in the game | patch kept in `I:/tmp/rb_push_work.patch`, out of the code |

Installed on E: now: the 22:46 test exe (measurements, without the queue). The official 0.76.2 in
`I:/lixo-sotc-05-11/bb-probe-0.76.2-oficial-1841.exe`.

## 4. The most efficient path

There are two problems with different causes; each has its own order.

### A. Dense stretches at 44–48 FPS (what the user feels)

**Result of step 1 (18 Nov): the separate queue did not raise the FPS; turned off and stopped.** What
remains for the forest's entrance is the plan's order (B below), starting with step 1.

The measured cause is the GPU wait (~10 ms per visibility computation). Steps 1–3 of
`PLAN-AREA-CHANGE.md` cut the port's queue, submission and apply, which add up to ~3 ms of the 20–27
here: **on their own they do not remove the drop to 48.** What attacks the cause is the separate
queue, which is already written and built.

1. **The decisive test of the separate queue** (one 2–3 min playthrough in the forest): install
   `out/bb-probe.exe` (23:30) with `SOTC_CULL_QUEUE=1 SOTC_GPU_TIMES=1`.
   - If the FPS in those stretches goes up and there is no image error (grass, horse, cloak, stairs):
     extend it to the other culls (`0xc54081d1`, `0x4defcf7f`; then those that read the Hi-Z image)
     and do the long session + the ending before it becomes the default.
   - If it does not go up: turn it off, put the exe back, record it and stop this line (it stays in
     the code, off).
2. Only afterwards: cutting the port's cost in the copies (~1 ms recoverable).

### Result of step 1 (18 Nov 21:09, `SOTC_RB_GROUP`)
The user's playthrough at the forest's entrance, compared by load band with those of 17 Nov:

| Playthrough | 4–6 thousand commands/frame | 6 thousand+ |
|---|---|---|
| 17 Nov 22:30 / 22:38 / 22:48 | 56.3 / 57.4 / 53.6 FPS | 46.9 / 50.3 / 44.8 |
| 18 Nov 21:02 (separate queue) | 49.0 | 40.8 |
| 18 Nov 21:09 (step 1) | 55.7 | 41.9 |

**It did not go up.** It acted (300–1,100 readbacks per 5 s brought along the same shader's other
ranges), but it brought much more data (up to 213 MB every 5 s: these shaders write large ranges) and
the game's waits stayed at 12–30 ms of GPU per frame. Turned off (the 22:46 exe back on E:); code in
the working tree with the default on: **set the default to 0 before any commit**.

Reading the numbers: in the heaviest stretch (6 thousand+ commands) the GPU is already busy 15–17 ms
per frame and the game waits for it inside the frame. Steps 1–3 only cut the port's part of the wait
(queue ~1 ms, submission 0.3, apply ~1.5). What is left to gain is the emulation cost on the GPU
(barriers/copies ~3–4 ms, ~1 ms recoverable) and the CPU/GPU overlap, which the separate queue did
not achieve.

### Result of step 2 (18 Nov 21:23, `SOTC_RB_PUSH=1`)
Reapplied from the patch `I:/tmp/rb_push_work.patch` onto the current code, with the probable cause of
the 17 Nov "device lost" fixed: the delivered copy sat in a submission not yet sent and the deferred
release unbound the memory before it ran (`PushTickInRange` in `ReleaseBlocks`: waits for the copy
before the unbind; 0 waits in this playthrough). A playthrough at the forest's entrance: no crash
(the "game stopped by the launcher" line also appears in the 17 Nov 22:48 reference playthrough: it is
the user closing from the launcher). **4–6 thousand commands 50.7 FPS, 6 thousand+ 45.0: it did not go up.**
~92% of the copies went stale before the game read them (another pass rewrites them), `0x50784801`
was turned off by itself (the game read 3–6 of every 1,000 of its copies), up to 35 thousand copies
every 5 s. Turned off (the 22:46 exe back); code in the working tree, only on with `SOTC_RB_PUSH=1`.

### The last stretch (the forest's area change), 17–18 Nov

| Playthrough | FPS in the last 5 s windows |
|---|---|
| 17 Nov 22:38 (reference) | 46.4 · 46.5 · 47.3 |
| 17 Nov 22:48 (reference) | 41.7 · 46.3 · 45.7 · 45.2 |
| 18 Nov 21:02 separate queue | 39.3 · 41.1 · 40.8 · 39.3 · 40.0 |
| 18 Nov 21:09 step 1 | 44.0 · 42.9 |
| 18 Nov 21:23 step 2 | 45.0 · 45.0 |
| 18 Nov 21:37 step 3 (`SOTC_RB_SAFEPOINT=1`) | 48.7 · 40.4 · 42.1 · 44.4 · 44.0 |

**Step 3** (`SOTC_RB_SAFEPOINT=1`, default off): applying the finished readbacks has its own queue
(`Liverpool::SendFinish`/`ServeFinishes`) and also runs between the buffers of a bind and between the
buffer bind and the texture bind (only the clean ones: a dirty one, a dependent one or one from the
separate queue waits for the normal point). It acted (100–650 applies per 5 s in the middle of the
bind), without a crash; **the last stretch did not go up.** Turned off.

**Diagnosis without PS4 Pro mode (18 Nov 21:47, only to measure):** the last stretch 51.9 · 49.7 ·
**40.5 FPS** — the same drop; GPU busy 76–83% (14–19 ms per frame), the same as Pro. Less resolution
changes nothing: the GPU's time in that stretch does not depend on the resolution, but on the number
of commands (5–8 thousand per frame), dispatches and barriers. Pro turned back on after the test.

**Who the GPU waits for (18 Nov 21:59, `SOTC_TICKWATCH`, the new line `SOTC GPU IDLE BY`):** in the
last stretch (44.4 · 43.3 FPS) the GPU is stopped 6.7–7.1 ms per frame and, during that time, **the
draw thread was busy 6.2–6.6 ms**; command processor 0.0; the game (both idle) 0.4–0.5. **The drop's
bottleneck is the port's draw thread** (recording 5–8 thousand commands per frame), not the game nor
the GPU. Path: `PLAN-DRAW-THREAD.md` (reduce the draw thread's cost per command); next step: a profile
of the draw thread alone in the last stretch.

**Measurements turned off (18 Nov 22:06, the same exe, extra variables only `SOTC_TEX_GATHER=1`):**
the draw thread's profile in the slow frames (`SOTC_PROFILE=GpuDraw SOTC_PROFILE_SLOW_MS=20`) showed
the measurements weighing on it (`SOTC_DRAW_SPLIT`'s `Ticks`/`SplitTimer`, `SOTC_SLOW_OPS`'s counters,
`SOTC_GPU_TIMES`'s maps). Without them: the middle of the route 54–57 → **59–60 FPS**; area change
40–47 → **49–55 FPS** (6–9 thousand commands/frame). The gain is taking our own measurement out of the
user's game (other players do not have those variables). **Rule: measurements only in the
playthrough that measures; afterwards, take them out of the launcher.** The drop to ~49 at the
heaviest point remains (9 thousand commands): keep relieving the draw thread (next lead: "show FPS"
turns on `SOTC_FPS`, which activates the internal `kFpsLog` timers on that thread).

**Clean profile (18 Nov 22:10, only `SOTC_TEX_GATHER=1` + a draw thread profile in the frames > 20
ms):** the last stretch 56.4 · **53.4** FPS and the rest 56–60; **the dynamic FPS did not drop to 48
even once** (not in the 22:06 playthrough either; in the playthroughs with the measurements on it
locked at 48). In the slow frames that remain, the draw thread spends **~16% in page protection**
(`Protect`/`VirtualProtect`, watching what the GPU writes) and ~20% waiting for the flip's time
(`SubmitFlip`, pacing, not work; `SOTC GPU IDLE BY` counted it as "busy"). The next real target:
batching the page protection calls.

**What the user sees (18 Nov 22:15): the 5 s average hides the dips.** In the same playthroughs, at
the area change, there are frames of 30–49 ms (1% low 24–32 FPS) — that is what the on-screen counter
shows. **Compare per frame (the `SOTC FRAMES` line: p99, 1% low, worst), not by the `SOTC FPS`
average.** In those frames the port hardly works (buffer 1–3 ms, dma 1–8 ms) and the command
processor is **idle 17–30 ms waiting for the game** to send commands: the hitch comes from the game's
side at the area change (the game's threads waiting for GPU readbacks and locks, see section 2). Next
diagnosis: what exactly the game's threads do in those frames (a profile of every thread only in the
frames > 25 ms).

**A profile of every thread triggered by the drop (18 Nov 22:20, `SOTC_PROFILE_TRIGGER_FPS=50`, new
in `src/probe.c`; it triggered at 36.9 FPS at the area change):** the game's worker threads 57%
inside the readback (`ReadMemory`: ~29% waiting for the GPU, ~8% waiting for the draw thread to serve
the request, ~11% handling the page fault), ~24% spinning on locks, 13% in the game; the game's main
threads waiting for those. The draw thread **not** saturated: ~36–47% working, ~16% without work,
**~13% blocked in `SubmitFlip`** (waiting for the presentation to accept the previous frame:
`SOTC_FLIP_QUEUE`, default 1). The command processor almost all stopped. A correction of what I said
before: `SOTC GPU IDLE BY`'s "draw thread busy" included those waits. Next test: `SOTC_FLIP_QUEUE=2`
(only a variable; +1 frame of delay at most).

**`SOTC_FLIP_QUEUE=2` (18 Nov 22:24):** on screen at the area change 41 · 42 · 47 · 47 (reference
45 · 40 · 41): **it did not help**; removed.

**The GPU in the drop (18 Nov 22:28, `SOTC_GPU_TIMES=1 SOTC_GPU_TIMES_EVERY=10`, dependencies now only
with `SOTC_GPU_TIMES_DEPS=1`):** drops on screen at 23–39 s (39–48, the dynamic FPS locked at 48) and
82–83 s (39). Per frame: at 60 FPS, GPU 16–17 ms from the 1st to the last command (~11–12 of work,
~5 stopped); in the drop 18–20 ms (~13 of work, 5–7.5 stopped). **The GPU is not overloaded in the
drop.** Readbacks 1,100–1,500/s in the drop against 700–850/s at 60. The picture: at the area change
the game makes more CPU→GPU→CPU round trips, one after another, and its threads wait in series
(readbacks + locks). The 18 Nov attempts shortened pieces of each round trip, not their number.

**The separate queue covering new ranges (18 Nov 22:38, `SOTC_CULL_QUEUE=1`, page table
`SOTC_CULL_QUEUE_PAGES`):** harness with `SOTC_CULL_QUEUE_VERIFY=1`: "learning" 0 (4500–7300/5 s
before), ~10 thousand dispatches on the new queue every 5 s, 0 differences in ~30 thousand
comparisons, no crash. The user's playthrough: on screen at the area change **38 · 39 · 42**
(reference 40–45): **it did not help** — the game's readbacks almost all still went through the
graphics queue (113–488 every 5 s through the new queue, of ~5000). Turn it off.

**The dynamic FPS prolongs the drop:** after each dip the screen stays **locked at 48 for 10–15 s**
(40–56 s and 96–108 s in this playthrough): `SOTC_FPS_DYNAMIC` locks at 48 after 1.5 s below 50 and
only tries 60 every 10 s. In the 22:16 playthrough (without the lock) the dip lasted ~3 s and went
back to 60. A cheap test: `fps_dynamic` off.

**Dynamic FPS off (19 Nov 15:12, `fps_dynamic: false`, only `SOTC_TEX_GATHER=1`):** no lock at 48 at
any point. After the save's load 44–56 for a few seconds and back to 58–60; area change 56 → **39 ·
42** → 52 → 58 → 60 from 87 s. The dip (~2 s) remains, but it ends there; with the dynamic FPS on the
same dip became 10–15 s at 48. Pending: decide whether the dynamic FPS leaves the launcher's defaults
(or whether it only locks after a long drop and tries 60 again sooner), and the ~2 s dip itself.

**Dynamic FPS tuned (19 Nov 15:16, `driver.cpp`):** locks at 48 only after **5 s** accumulated below
50 FPS (`SOTC_FPS_DYNAMIC_SLOW_MS`, was 1.5 s) and tries 60 again after **4 s**
(`SOTC_FPS_DYNAMIC_HOLD_S`, was 10 s), doubling at each failed try up to 10 s. The user's playthrough
with the dynamic FPS on: **no lock at 48**; area change 40 · 40 · 40 · 46 · 48 · 48 · 54 → 60 from
108 s; the rest 57–60. The dip itself remains (~3 s at ~40 and ~3 s coming back). In the test exe;
not committed.

**256 KiB readback window (19 Nov 15:22, `SOTC_RB_NARROW=256`, only a variable):** area change 45 · 37
· 39 · 43 → 60 in ~7 s (before 40 · 40 · 40 → 60 in ~7 s); readbacks ~1000/s in the dip (1100–1400
before); the rest 59–60. **It did not help**: the number of round trips is not what limits it.
Removed.

**Where the dip is (summary, 19 Nov):** ~3 s at ~37–40 FPS on screen and ~4 s coming back, at the
forest's area change. In those frames the port hardly works (buffers/copies 2–8 ms) and waits for the
game 20–36 ms; the game's threads wait for GPU readbacks and for each other's locks; the GPU is not
overloaded (~13 ms of work). Tested without a gain: the separate queue (2 versions), steps 1–3,
`IDLE_FLUSH`, `FLIP_QUEUE=2`, the 256 KiB window, without Pro mode. Real gains: taking the
measurements out of the launcher (the rest of the route 54–57 → 59–60) and the tuned dynamic FPS (no
10–15 s stuck at 48).

**Conclusion of the 4 attempts of 18 Nov:** no change to the readback path (the separate queue, steps
1–3) moved the drop at the forest's area change. The port already delivers the readbacks in ~1–3 ms;
what holds the last stretch back is the GPU busy 15–17 ms per frame with the game waiting for it
inside the frame (section 2).

### B. Hitches at area changes (the forest)
Here the queue and the apply weigh (queue 1–20 ms, apply 10–60 ms on 3–5 Nov), so the plan's order
holds: **step 1** (`SOTC_RB_GROUP`, grouping readbacks by shader) → **step 2** (fix `SOTC_RB_PUSH`
from the patch; first, find out why it took the GPU down) → **step 3** (`SOTC_RB_SAFEPOINT`). Each
one: a user playthrough on the forest route, the same rule as section 1.

### Before any commit
Review the whole working tree (19 files), split it into commits by topic (prefetch + launcher;
measurements; the separate queue off), and only with the user's OK.
