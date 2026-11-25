# Draw thread: a plan for a steady 30 FPS at area changes

The user's request on 29 Oct 2026, after T48 (local commit `7fde988`): the big stalls are gone (worst
frame 534 ms → 58–75 ms), but each area change still loses 1–6 frames. The previous session's
conclusion was that the limit is structural: the draw thread (`shadPS4:GpuDraw`) shows as busy 28–32
ms of each 33 ms frame.

**This document is only the plan.** Nothing has been implemented. Before any code, the user approves
the order and step 0.

## The order agreed with the user (29 Oct)

Outside the area changes, the game already runs at a steady 30 FPS: the typical frame stays at 33.3
ms and the 5 s windows give 30.0 FPS in every log of 29 Oct. The agreed order is:

1. **Phase 1: polish the 30 FPS.** Remove the 1–6 frames lost at area changes. These are steps 0–4 of
   section 4, measured at 30 FPS.
2. **Phase 2: fix the open failures.** The list comes from the ROADMAP and the user picks which ones
   go in. New since T48: a crash at `guest offset 0x49800` (0xc0000005, a read of
   `ffffffffffffffff`) at 24 min into the 10:00–10:24 session of 29 Oct, with the exe of `7fde988`.
   It is the BPE heap allocator, a neighbour of the 0x497f0 that the heap guard protects. In the last
   window before the crash, the free blocks dropped from 5870 to 3432 and the guard "vouched" for 30
   writes. Log and dump in `E:\...\SotC-PC\user\crashes\2026-10-29_10-24-5*`.
3. **Phase 3: release a new version on the site** (a GitHub release, without deleting the old ones),
   with the user's approval at release time.
4. **Phase 4: get close to 60 FPS.** At 60 FPS each frame has 16.7 ms. According to the 28 Oct profile
   in a heavy area, the draw thread spends ~22 ms of CPU per frame and the command processor ~17 ms
   (15.6 ms just reading commands). Step 0 is repeated in the 60 mode. Steps 5–6 (binds prepared off
   the thread, recording on several threads) become the main path, together with a new item:
   relieving the command processor.

Reference configuration (the user's real launcher, `user/launcher_settings.json` on 29 Oct): 30 FPS
(`fps_mode 30`), PS4 Pro mode, Maximum textures, DLSS Ultra (1600x900 → 1920x1080), Fifo, maximum
VRAM, recording thread on, `SOTC_LOD_FEEDBACK=1 SOTC_MIP_TAIL=0`. i9-13900K, RTX 2060 SUPER (8 GB).

## 1. What the numbers already show (and a problem in the measurement)

### 1.1 "draw busy" does not measure work

The line `SOTC threads per frame: draw busy` (`core/libraries/videoout/driver.cpp:777`) is
`(window time − idle time) / flips`. Idle time only counts when the draw thread's queue is **empty**
(`Liverpool::BackLoop`, `liverpool.cpp:130`). Everything the thread does *inside* an operation counts
as busy, **waiting** included:

- the flip runs on the draw thread (`SubmitFlip` → `SendOrderedCommand` → `SubmitFlipInternal` →
  `Presenter::PrepareFrame` → `GetRenderFrame`, which waits for a free frame and for the presentation
  fence with Fifo);
- the GPU readbacks (`BeginAsyncReadback`/`FinishAsyncReadback`) and the flushes requested by other
  threads (`SendCommand<true>`) run there, between two operations;
- `scheduler.Finish()`, `Scheduler::Wait`, `waitIdle` and the memory lock waits too.

Proof in the user's log of 29 Oct (`E:\...\SotC-PC\user\last_run.log`, 293 windows of 5 s):

| windows | commands per frame | average "draw busy" |
|---|---|---|
| 4 | under 500 | 28.8 ms |
| 188 | 3000 or more (up to 13,711) | 28.3 ms |

With 25 times more commands, the number does not change. So it measures the frame's pace (locked at 30
FPS), not how much the thread works. **"The draw thread is saturated" is not proven yet.**

### 1.2 The real CPU time is lower, but not small

The 28 Oct profile of every thread (`out/prof_all_trans.run.txt`, `SOTC_PROFILE=*`, ~10 s in a heavy
area, 6000 commands per frame) has each thread's CPU time (`GetThreadTimes`):

| thread | user + kernel | per 33 ms frame (≈) |
|---|---|---|
| `shadPS4:GpuRecorder` | 8,938 + 859 ms | ~32 ms (almost all busy-waiting) |
| `shadPS4:GpuDraw` | 5,391 + 1,172 ms | ~22 ms |
| `shadPS4:GpuCommandProcessor` | 4,391 + 734 ms | ~17 ms (`command parse 15.6 ms`) |
| 4 × `BPE JobWorkerTh` (game) | ~4.2–4.5 s each | ~14 ms each |

Even those ~22 ms include busy-waiting: the draw thread spins 4096 `pause` before sleeping, and the
recorder spins too (`RECORDER_PAUSE`). In the GpuDraw samples, ~22% are inside a kernel wait
(`KERNELBASE+0x22a58`, `ntdll+0x1659c4`). The names of small functions in the LTO build are not
reliable (ICF merges identical functions), so a small function's address is not enough to blame
anyone.

Conclusion: the draw thread has real slack only if its work is well below 22 ms; today neither can be
claimed.

### 1.3 What weighs in the lost frames

The `SOTC FRAMES` line of the windows with a frame above 40 ms in the same log (each window's worst
frame, with the cause). The timers (`SotcStats::FrameTimer`) count on any thread:

| worst frame | biggest cause | others |
|---|---|---|
| 816 ms | GPU readback 599 ms | shader 90, idle 90 |
| 384 ms | GPU readback 112 | shader 60, pipeline 59, idle 77 |
| 250 ms | GPU readback 133 | idle 85, shader 25 |
| 200 ms | GPU readback 74 | idle 61, shader 36 |
| 200 ms | idle 94 | pipeline 37, readback 34 |
| 200 ms | idle 67 | buffer 23, io 17, upload 13 |
| 87–92 ms | new image 27–57 | — |
| 68–73 ms | new image 52–62 | — |
| 74–108 ms | texture upload 53–61 | alloc 7–8 |
| 159–192 ms | idle 48–136 | DMA 44, buffer 16–20, io 19 |
| 58–67 ms (the most common) | idle 10–78 | nothing above 10 ms |

"Idle" (`FrameIdle`) is the command processor waiting for the game to send work: in those frames the
**game** was late, often waiting for a GPU readback, a file (io) or the BPE workers themselves. In
several long frames, drawing was not on the critical path.

**Summary:** the lost frames have three mixed origins: (a) the game's long GPU readback waits, (b)
one-off work on the draw thread when entering a new area (shader, pipeline, new image, texture
upload, DMA) and (c) the continuous load of 5–10 thousand commands per frame. Splitting the draw
thread helps (b) and (c), but not (a). That is why step 0 measures before touching anything.

## 2. Step 0 — measure for real (mandatory before choosing)

A new switch `SOTC_DRAW_SPLIT=1` (off by default; counters only, it does not change behaviour). A new
line in the log every 5 s:

```
SOTC DRAW SPLIT per frame: cpu 14.2 ms (cycles), draw 6.1, indirect 3.0, dispatch 1.2,
  bind 4.4 [buffers 1.9, textures 2.1, dma 0.4], flip 0.3 (waited 9.8), readback 0.6
  (waited 2.1), commands 0.4, other waits 1.7; recorder cpu 4.0 (spin 20.1); cp→draw drains 4
```

How to measure each part:

1. **Real CPU per thread:** `QueryThreadCycleTime` of GpuDraw, the command processor and the recorder,
   at each flip, minus the time in the busy-wait loops (a counter of its own around the
   `CpuRelax`/`RECORDER_PAUSE`).
2. **Time per operation type:** in `ExecuteBackOp`, accumulate by `BackOp::Kind` (Draw, DrawIndirect,
   Dispatch, Func) and, inside `Rasterizer::Draw`, the `BindResources` blocks (separating
   `BindBuffers`, `BindTextures`, `SynchronizeDmaBuffers`), `BeginRendering` and the recording.
3. **Waiting inside the operation:** time separately what blocks: `GetRenderFrame`, the
   `Scheduler::Wait`/`Finish`, the memory lock waits seen by GpuDraw, `waitIdle`. That comes out of
   "busy".
4. **Who was on the critical path in the frames > 40 ms:** keep, together with the worst frame,
   GpuDraw's CPU, the command processor's CPU, the draw thread's queue (`back_head − back_tail`) and
   how long the game waited for a GPU readback.

Cost: one `QueryThreadCycleTime` and `NowNs` per block, only with the switch on (like `SOTC_FPS`).

**Implemented on 29 Oct (not committed), installed on E: at 11:04.** Lines `SOTC DRAW SPLIT per
frame`, `worst frame` and `frames > 40 ms` every 5 s (`sotc_stats.h`/`.cpp`, `driver.cpp`). The game's
GPU readback waits add up all of the game's threads, so they can exceed 33 ms. First test, in a light
scene (~290 commands per frame): "draw busy" 28.9 ms, but the draw thread's real CPU is **6.8 ms**.
The thread spends **25.3 ms per frame stopped at the flip** (`GetRenderFrame`, waiting for a free
presentation frame), and during that time the GPU readbacks the game waits for are stopped too (a
"finish" phase of 28–70 ms summed over the threads). It still has to be measured in the heavy areas.

### Result of step 0 — the user's route (29 Oct, 11:06–11:14)

The user's launcher (30 FPS, Pro, Maximum, DLSS), Shrine → load the save → two area changes →
colossus; 86 windows of 5 s. Values per frame (ms):

| stretch | commands | draw CPU (spin) | command proc. CPU | binds | wait at the flip | the game's readbacks (sum) |
|---|---|---|---|---|---|---|
| Shrine / menus | 150–1,500 | 6–11 (1–2) | 5–10 | 2–5 | 19–25 | 4–17 |
| open field, medium areas | 1,200–3,000 | 15–17 (2.5) | 7–10 | 5–6 | 13–16 | 28–32 |
| heavy areas, 30 FPS | 4,000–7,400 | 20–24 (2) | 15–24 | 8–13 | 3–10 | 45–55 |
| frames > 40 ms at the changes (21–22 per change) | 6,000–7,000 | 33–36 (4) | 24–39 | 13–22 | 0 | 60–70 |

Reading:

1. **In the heavy areas the draw thread has 3–10 ms of slack, not zero.** The real work stays at
   18–22 ms; the rest of the old "draw busy" is waiting at the flip.
2. **At the entry of each new area (~1 s, 21–22 frames) it goes over the limit**: 29–32 ms of real
   work, 0 waiting at the flip, frames of 40–50 ms. The binds are most of it (13–22 ms per frame, half
   of the draw operations); the command processor also reaches 24–39 ms in those frames.
3. **The few 100 ms frames are texture uploads inside `BindTextures`**: 108 ms (t=356) with textures
   59 ms and "upload" 55 ms; 99 ms (t=401) with textures 64 ms and upload 56 ms, for only 19–28 MB
   copied (~0.5 GB/s). One of 108 ms (t=110) was a shader (59 ms) and one of 84 ms (t=85) was the game
   waiting for a file (io 172 ms).
4. GPU, submission and recorder hardly wait (≤ 1.5 ms); the draw thread's queue is full (512) in every
   heavy stretch.

### Step 1 — texture uploads (29 Oct, installed at 11:35)

Second route (11:23, upload phases measured): in the 90–175 ms frames the upload's time is almost
all in the **copy** from the game's memory to the staging area: 41–58 ms for 12–20 MB. Reserving the
staging area, detiling and recording add up to less than 9 ms. In those windows the game maps the new
area's memory (`batch_map2` holds the table lock 330–440 ms every 5 s), and the copy
(`CopySparseSerial`) looked the table up twice per contiguous piece (`runtime_memory_region` and
`runtime_memory_backing_pointer`). Each lookup the region cache could not answer waited for the whole
batch. Moving the upload to another thread would not help: it would wait just the same.

Fix: `SOTC_COPY_LOCK_ONCE=1` (`runtime_memory_copy_out`, `src/runtime_memory.c`). The pieces the
region cache already knows are copied without the lock; the rest, under a single read lock for the
whole copy. The result is the same as before (through the `backing` view; reserved or unmapped memory
becomes zero). It also applies to buffer uploads (the "buffer" spikes of 50–90 ms). On only in the
user's launcher; off is the behaviour of `7fde988`.

**Result (the 11:35 and 11:45 routes): no gain.** The new copy almost never waited for the lock
(`runtime_memory_copy_out` ~0 ms in the waits), but the 11:35 route still had two copies of 41–45 ms
for 14–19 MB. The lock was not the cause. The 11:45 route (130 s, shorter) also measured the page
faults: it had no slow copy; the slowest were 12.5 ms (24.5 MB) and 17.4 ms (88.5 MB), with ~5,500 of
the process's page faults in the frame, against ~200–1,500 in the others. In the menu, 25.8 MB were
copied in 0.9 ms. Provisional conclusion: the slow copy is rare (2–3 frames per long route) and
coincides with many page faults, but the cause is not proven. The averages in the heavy areas were
the same on all three routes (draw 21–22 ms, binds 9–10 ms). The ~20 frames of 40–50 ms of each change,
which lose more frames in total, come from the binds and the command processor.

### Step 2 — profile of the draw thread (the 11:56 route, 30 s–2 min of play)

`SOTC_PROFILE=GpuDraw` (54,938 samples; data in `out/prof_draw_rota_29-10.txt`, symbolised with
`llvm-symbolizer` on the same build's `out/gpu/bb-probe.exe`). The thread's time:

| part | samples |
|---|---|
| waiting for a free frame at the flip (`GetRenderFrame`, Fifo) | 28% |
| without work (waiting on the queue) | 9–10% |
| waiting for the GPU (`SubmitAheadAndWait`, `Semaphore::Wait`), the memory lock, `yield` | ~8% |
| compute dispatches (`DispatchDirect`/`Indirect`) | 15% |
| indirect draws (`DrawIndirect`) | 8% |
| inside them: `BindBuffers` 6%, `BindTextures` 4%, `FindTexture` 3%, `SynchronizeDmaBuffers` 3% | |
| page protection (`ZwProtectVirtualMemory` via `protect_fast`/`PageManager::Protect`) | 4% |
| the heap guard when applying readbacks (`BpeHeapGuard`, `FinishAsyncReadback`) | 4–6% |
| copies from the game's memory (`CopySparseSerial`) | 3.5% |

There is no hot spot in the binds: the work is spread over a dozen functions of 3–6% each. The heap
guard cannot change behaviour. The ~20 slow frames of each change come from the sum of these costs on
the draw thread and the command processor (which also reaches 24–39 ms in those frames), not from a
single function.

**Conclusion of phase 1 (29 Oct):** what could be removed with a small, safe fix already came out in
T48. What is left (1–6 frames per area change, ~20 frames of 40–50 ms over ~1 s) only goes away with
options A/C's structural change: preparing binds in parallel and recording on several threads. It is
the same work phase 4 (60 FPS) needs, where it pays twice. Left off and unused: `SOTC_COPY_LOCK_ONCE`
(no gain). The `SOTC_DRAW_SPLIT` measurement stays (counters only).

### Profile of every thread (the 12:14 route, 30 s–2 min of play)

`SOTC_PROFILE=*` (data in `out/prof_all_rota_29-10.txt`). The average of the whole 90 s window, with
one area change:

| thread | waiting | main work |
|---|---|---|
| draw (`GpuDraw`) | 44% at the flip (`PrepareFrame`), ~9% without work, ~5% GPU | operations 19% (dispatch 11, indirect 10, binds 6+4), the game's readbacks (`FinishAsyncReadback`, heap guard) ~6%, page protection ~3% |
| command processor | 63% waiting for the game to send, ~7% waiting for the draw thread | reading the commands 21%, JIT code 20%, pipeline lookup 6% |
| the game's workers (`BPE JobWorkerTh`, 4) | the game's mutex 33%, events ~25% | **24% of the time inside GPU readback page faults** (`vectored_fault_impl` → `ReadMemory`) |

On average neither of the two GPU threads is full. The lost frames are in the ~1 s bursts of each
area change, when both reach 33–40 ms at the same time (`SOTC DRAW SPLIT` counters), and the sampling
profile does not separate those bursts from the rest.

### Structural options, with honest cost and risk

| | what it is | expected gain in the bursts | size | risk |
|---|---|---|---|---|
| A1 | the command processor (63% idle on average) already reads the sharps: it would decode T#/V#/S#, `ImageInfo`/`ImageViewInfo` and the buffers' mapped size with each operation; the draw thread only looks things up in the caches and records | 3–6 ms per burst frame (the decoding part of the binds) | 3–5 days | medium: sharps read too early (the same rule as `WaitBackWrites`); in the bursts the command processor is full too, so part of the gain goes away |
| A2 | cache lookups (`FindTexture`, `ObtainBuffer`) done in batches by a preparation thread | +5–8 ms | 1–2 weeks | high: the texture and buffer caches are not thread-safe (T48's lesson: a misplaced lock created the worst stalls) |
| C | recording on 2–4 threads (separate passes, secondary command buffers) | the only one that removes 10–15 ms | weeks | high: the whole rasterizer state (barriers, layouts, HUD without UI, DLSS observing the draws) built for a single thread |
| D' | GPU readback page faults on the game's threads (24% of their time) | the game sends work earlier (frames with high "idle") | large (it is the "PC memory model") | high: it goes around the heap guard, which cannot change behaviour |

No option alone removes the losses: in the bursts the draw thread and the command processor both go
over 33 ms. A1 is the first step of A2 and of C, and the only one of medium risk.

**Decision (table above: real CPU 15–25 ms):** B first, starting with the texture uploads that make the
100 ms frames; then take work out of the binds (option A), which is what overflows in the ~20 frames of
each change. The wait at the flip in front of the game's readbacks (option D) comes later: in the heavy
stretches it drops to 0–7 ms.

**Step 0's measurement:** the user plays the usual route with their launcher (30 FPS, Pro, Maximum,
DLSS), with `SOTC_FPS=1 SOTC_DRAW_SPLIT=1` in `extra_env`: Shrine → ride out on the horse → two area
changes → a colossus. I only read `user/last_run.log` afterwards. For a profile by address,
`SOTC_PROFILE=* SOTC_PROFILE_DELAY=<s> SOTC_PROFILE_SECONDS=10 SOTC_PROFILE_OUT=...` in the same run,
symbolised with `llvm-symbolizer` on the **unstripped** `bb-probe.exe` (only large functions are
reliable).

**Decision after step 0:**

| if GpuDraw's real CPU in the heavy areas is... | then |
|---|---|
| under ~15 ms | the thread is not full: go straight to options B and D (spikes and readbacks); option A is kept for later |
| 15–25 ms | B and D first, then A |
| over ~25 ms | A comes in early, B and D in parallel |

## 3. Options to take work off the draw thread

### Option A — prepare the binds off the thread (a two-phase pipeline)

Today each draw does, in sequence on GpuDraw: apply registers → `BindResources` (`BindBuffers` +
`BindTextures`: look up buffers and images in the caches, synchronise, build `set_writes`/`push_data`)
→ `BeginRendering` → record. `FASTBIND` already skips ~58–63% of the repeated binds.

Proposal (`SOTC_BIND_PREP=1`): the command processor already resolves the pipeline (`CaptureBackOp`).
A "preparation" thread between it and GpuDraw computes what is **read-only**: the FASTBIND hash,
`MakeUserData`, reading the V#/T#/S# (sharps) from the game's memory, the image/buffer lookup keys.
GpuDraw receives the op with those keys already and only does the lookups that touch the caches and the
recording.

- Expected gain: the sharp reading and hashing part (to be measured in step 0; an estimate of 20–35%
  of the bind).
- Risks:
  - the sharps are in the game's memory, which changes; reading them early needs the same rule as
    `WaitBackWrites` (wait for the last op that writes memory), otherwise the draw uses old resources
    (wrong texture, flicker);
  - the texture cache and the buffer cache **are not thread-safe**; the preparation thread can only
    read immutable structures or ones with a generation counter (like `BindGeneration`);
  - one more queue increases the latency of the GPU readbacks the game waits for.
- What does not change: the heap guard, `POOL_FIX`, the pool rule (none of that is in the bind).

### Option B — take a new area's one-off work off the thread

In the lost frames, the spikes of "new image" (27–62 ms), "upload" (53–61 ms), "buffer"/"dma"
(16–45 ms) and "hash" happen **on GpuDraw**, in the middle of the frame, when a draw finds something
that does not exist on the GPU yet.

Proposal, in three independent parts, each with its own switch:

1. `SOTC_IMAGE_AHEAD=1` — create images ahead: when the command processor reads a new T# (it already
   reads the sharps to find the pipeline), it requests the creation of the `VkImage` + VMA memory on a
   worker thread. When the draw arrives, the image already exists; it only registers and uploads.
   Image creation is what shows up most on its own in the 68–92 ms frames.
2. `SOTC_SYNC_WORKER=1` — the copies from the game's memory to the staging area (DMA, buffer uploads,
   the textures' `memcpy`, the content hash) go to the 4 copy threads that already exist
   (`bbport_copy.cpp`). GpuDraw only records the `vkCmdCopy` after the copy has finished, as is already
   done with the upload budget (`SOTC_UPLOAD_BUDGET_MB`).
3. Shader and pipeline: `ASYNC TRANSLATE`/`ASYNC COMPUTE` already exist, but the shader (16–90 ms) and
   pipeline (28–59 ms) spikes still appear at an area entry. Measure which stages still compile on the
   thread (a counter per reason) and cover those cases.

- Expected gain: remove the 50–60 ms spikes that remain in changes without a long readback; it is the
  closest thing to "a frame lost to one big job".
- Risks:
  - **an image created for a T# the game changes before the draw**: only memory and time lost (the
    image is discarded); limit how many per frame;
  - VRAM: creating ahead raises the usage peak (today 5.9–6.9 GB of a 6.5 GB budget); respect the
    budget and the emergency collection;
  - a copy made before a write by the game: it needs the same page protection DMA uses today (the
    write after the copy marks the page and the draw redoes it); **without it green blocks/garbage
    appear**, which must not come back;
  - the upload budget stays: a postponed texture stays black for a frame, as today.

### Option C — record on several threads

The most radical one: split a frame's draws (by render pass, for example shadow / G-buffer / post)
among 2–4 bind+record threads, each with its own secondary command buffer, and the recorder joins
everything in order.

- Gain: it really scales with 5–10 thousand commands per frame, if the bind's CPU is the limit.
- Risks (high):
  - the rasterizer's state (`render_state`, barriers, the images' layouts, `fast_bind`,
    `needs_barrier`, the HUD without UI, the UI shadow, DLSS observing the draws) all belongs to a
    single thread; splitting it requires separating state per thread and a phase that joins the
    barriers;
  - the texture and buffer caches would need fine-grained locks, which can cost more than they gain
    (T48's lesson: misplaced locks created the worst stalls);
  - write order in the game's memory and GPU readbacks: a draw that writes and another that reads in
    the same pass cannot go to different threads;
  - weeks of work, and many places where the heap guard and the readback meet.
- Only worth it if, after A and B, GpuDraw's real CPU still exceeds ~25 ms in the heavy areas.

### Option D (not the draw thread, but it weighs more) — shorter GPU readbacks

In the worst frames (200–816 ms) the biggest cause is the game waiting for a GPU readback. The path
(`BufferCache::ReadMemory` with `SOTC_RB_ASYNC`): the game's thread requests the copy on GpuDraw
(`BeginAsyncReadback`), waits for the command buffer to be submitted (`WaitSubmitted`), waits for the
GPU, and asks GpuDraw again to apply it (`FinishAsyncReadback`, where the heap guard is).

Proposal (`SOTC_RB_PRIORITY=1`): when there is a readback waiting, GpuDraw submits the command buffer at
once (today it can wait for the next periodic flush) and the final apply runs before the next op.
Measure first: in step 0, separate how much of the wait is GpuDraw's queue, how much is submission and
how much is GPU.

- Risks: more submissions per frame (the driver's cost); **the apply still goes through
  `ApplyDownloads` with the heap guard, changing nothing in it.**

## 4. Proposed order

Each step sits behind its own switch, off until the user approves; each is measured before the next. I
build, check that the game starts (without running anything while the user plays), install directly in
`E:\GAMES\Shadow Of The Colossus\SotC-PC` with a backup of the exe beside it and say "installed at
HH:MM".

| # | Step | Switch | Measurement (the user playing, their launcher) | Done when |
|---|---|---|---|---|
| 0 | Split measurement of the draw thread | `SOTC_DRAW_SPLIT=1` | the standard route (Shrine → 2 area changes → colossus); read `SOTC DRAW SPLIT` and `SOTC FRAMES` | we know GpuDraw's real CPU and who is on the critical path of the frames > 40 ms |
| 1 | Images created ahead | `SOTC_IMAGE_AHEAD=1` | the same route; compare "image" in the frames > 50 ms and VRAM | "image" disappears from the lost frames, VRAM within the budget, no wrong texture |
| 2 | GPU readbacks with priority | `SOTC_RB_PRIORITY=1` | the same route + the ending (the 15-defeated save, slot 4) up to the credits | the worst frames drop; the ending without a crash; the heap guard protecting as before |
| 3 | Copies and hashing on the copy threads | `SOTC_SYNC_WORKER=1` | the same route; "buffer", "dma", "upload", "hash" and GpuDraw's CPU | GpuDraw's CPU lower in the heavy areas; no green blocks |
| 4 | Shaders/pipelines still compiling on the thread | (extends `SOTC_ASYNC_TRANSLATE`) | the first visit to an area without a cache | "shader"/"pipeline" ~0 in the lost frames |
| 5 | Preparing the binds | `SOTC_BIND_PREP=1` | the same route; GpuDraw's CPU and "late" in the `SOTC FRAMES` line | only if step 0 shows GpuDraw > 15 ms after steps 1–4 |
| 6 | Recording on several threads | `SOTC_MT_RECORD=1` | — | only if it still exceeds ~25 ms after step 5; a plan of its own first |

Steps 1, 2 and 3 do not depend on each other and can change order depending on what step 0 shows (the
one that weighs most in the lost frames goes first).

**Final criterion (a steady 30 FPS):** on the standard route, with the user's launcher, `late 0 of
150` and no frame above 50 ms in the area change windows, in two runs in a row; and the ending up to
the credits without a crash.

Automated tests (harness, 60 FPS with `BB_VBLANK_HZ=120`, Maximum + Pro) only with the user out of the
game and told beforehand, checking `tasklist | grep bb-probe`. They serve to see the thread's slack (at
60 FPS the 16.7 ms limit shows without the 30 FPS pace hiding it), not to approve the step.

## 5. Constraints that apply to every step

- Do not touch the semantics of the BPE heap guard (`BpeHeapGuard`, `ApplyDownloads`), `POOL_FIX` or
  the pool rule: the ending depends on them.
- No green blocks or textures with garbage: any copy or readback done earlier needs the same page
  protection as today.
- Maximum quality stays: PS4 Pro, Maximum textures, DLSS. No gaining FPS by lowering quality.
- Every change behind an environment switch, and with the switch off the behaviour is identical to
  `7fde988`.
- After each step, update T48 in `ROADMAP.md` and show the user.
