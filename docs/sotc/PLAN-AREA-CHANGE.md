# Plan: area changes without an FPS drop (17 Nov 2026)

The user's rule: **no loss of image quality or FPS**. Each step has a switch to turn it off (`=0`) and
an approval criterion measured before it becomes the default.

Basis of the plan: the port's measurements (ROADMAP T48/T50, PLAN-DRAW-THREAD, PC-MEMORY-MODEL), a
web study of emulators and Vulkan, and an independent review of the code (three queries in parallel,
cross-checked and verified in the code on 17 Nov).

## The problem in one sentence

Every frame the GPU computes the objects' visibility (6 cull shaders) and the game reads the result
**in the same frame** to build the draw list. On the PS4 that read is free (unified memory). In the
port it becomes an emergency readback: the game hits a protected page, the port records a copy,
submits, waits for the GPU to finish **everything** that was in the queue before, and applies it. At
an area change this repeats page by page: 30–65 ms per slow frame. The GPU is not slow (without Pro
mode the wait is the same): it is **queueing and serialisation**.

## Today's path (checked in the code)

| Step | Where | Cost measured in the slow frames |
|---|---|---|
| 1. The command processor reaches the cull dispatch (it is behind the rest of the frame) | `liverpool.cpp` SubmitDispatch :841, BackAlloc :327 | not measured (step 0) |
| 2. The draw thread records the dispatch and marks the mask's pages as written by the GPU | `vk_rasterizer.cpp` DispatchDirect :2513; `buffer_cache.cpp` :1303 | — |
| 3. The label (EOP) is written **at recording time**, before the GPU runs | `liverpool.cpp` :1793, :2360 | — |
| 4. The game reads, page fault → the readback request goes to the draw thread's queue, which only serves it **between** operations (a BindTextures of 20–55 ms at the area entry) | `buffer_cache.cpp` ReadMemory :244; `liverpool.cpp` BackLoop :195 | queue 1–20 ms |
| 5. Records the copy in the current command buffer and asks for a submission | BeginAsyncReadback :459 | — |
| 6. The recorder submits everything since the last submission | `vk_scheduler.cpp` :514 | < 1 ms |
| 7. The GPU finishes the whole submission (a single queue, in order) | — | 10–180 ms |
| 8. Back to the draw thread's queue and applied (with the heap guard) | FinishAsyncReadback :554 | 10–60 ms |
| 9. The mask's next page that was not included repeats 4–8 | GatherDownloads :779 | multiplies everything |

## What has already been ruled out (and why)

- The previous frame's mask (the HiddenUserHere fork): horse, cloak, grass and stairs shaking; objects
  vanish for 3 frames when the camera turns. The same family of failures in yuzu ("guessed"
  flushes), RPCS3 ZCULL Relaxed, Xenia "fast".
- Visibility computed on the CPU: needs tables the GPU writes; a frustum-only computation draws too
  many objects (8–17 FPS with XPR off).
- `SOTC_EOP_DEFER` (every label only with the GPU done): FPS halved.
- `SOTC_VIS_DIRECT` v1 (without waiting): crashes and a corrupted heap; v2: 58.8 → 41.8 FPS.
- ReBAR memory (VRAM visible to the CPU) for the CPU to read: NVIDIA and AMD advise against it, reads
  up to 1000× slower.
- Global queue priority on NVIDIA: needs administrator privileges on Windows.

## Our idea: a "delivered readback", not a "requested readback"

The game says exactly **which shader** writes the mask and **where**. So the port does not need to
wait for the game to hit the page: right after recording the cull dispatch, it already records the
copy of the ranges that dispatch writes to PC memory, and submits everything together at the label
the game waits for. When the game reads, the copy is already done or on its way; only it is waited
for, once per set, not a whole queue per page. The image is **identical** (the mask is the right
frame's, byte for byte), and today's emergency path stays underneath as a safety net.

## Steps

### Step 0 — Measure what is still unmeasured (without changing anything)
- The user's route on 0.76.1 with `SOTC_DRAW_SPLIT=1 SOTC_SLOW_OPS=1` (launcher already prepared).
- New counters (`SOTC_RB_AGE`): the time from the cull dispatch being published to the label; from
  the label to the fault; and, per fault, whether the data was already in a readback in progress. Says
  how much of the time is step 1 (a late command processor) and how much is GPU.
- Approval: numbers per stretch in `tools/entry_report.py`.

### Step 1 — Group by shader (`SOTC_RB_GROUP`, the smallest and safest)
- Each 64 KiB page written by the GPU keeps the program that wrote it (today only with `SOTC_RB_AGE`;
  it becomes permanent, cheap).
- On the first fault in a cull mask, the readback brings **every** range written by that program in
  the current and the previous submission along (the same apply path, with the heap guard and the
  skipping of pages the CPU wrote).
- Gain: step 9's repetition goes away (several waits become one). Risk: low. A byte limit per readback.

### Step 2 — Delivered readback (`SOTC_RB_PUSH`, the heart of the plan)
- List of cull programs: seeded with the 6 known ones (`0x50784801, 0x93aec24b, 0x2e0f474b,
  0x4defcf7f, 0xf94d23d4, 0x729c541e`), plus the learnt ones (a program whose ranges the game read
  while still being written).
- After those programs' `cmdbuf.dispatch` (the `AfterVisDirect` point, `vk_rasterizer.cpp`
  :2628/:2684): a compute→copy barrier and a copy of the written ranges (only the resident ones, like
  `GatherDownloads`) to HOST_CACHED memory; registered as an "ownerless" asynchronous readback in
  `inflight_readbacks`.
- Submitted once, at the EOP/ReleaseMem label (`liverpool.cpp` :1728/:2334), if there are pending
  delivered copies; never one submission per dispatch (`0x50784801` runs ~280 times per frame).
- The game's side: the fault finds the readback in progress (`FindInflightReadback`, the "dependent"
  path that already exists, `buffer_cache.cpp` :476/:555), waits only for its tick and applies as
  today. Nothing is written to the game's memory without a fault: zero speculative writes.
- If another pass rewrites the mask afterwards, `MarkInflightReadbacksDirty` already marks the
  delivery as old and the normal path takes over.
- `SOTC_RB_PUSH_VERIFY=1` (test): compares the delivery with the normal readback byte for byte; it
  has to give 0 differences.
- Expected gain: the frame's first fault no longer pays for the request's queue and the resubmission;
  the following ones find the data ready. Risk: low-medium; one more submission per label with
  deliveries (tens of µs).

### Step 3 — Apply without waiting for the long operation (`SOTC_RB_SAFEPOINT`)
- The draw thread also serves readback **finish** requests (which record no GPU commands) at safe
  points inside the long operations: between pieces of the texture upload (`CopySparseSerial`) and
  between buffers in `BindBuffers`. Starting a readback stays between operations only.
- Gain: step 8 (10–60 ms) no longer waits for a BindTextures of 20–55 ms. Risk: medium (only audited
  points).

### Step 4 — Texture uploads off the visibility path (`SOTC_UPLOAD_QUEUE`)
- The area entry's large copies (19–28 MB, ~55 ms; textures of 64–128 MB "across chunks") go to a
  separate copy queue, with a semaphore before the first draw that uses the texture (no pop-in: the
  draw waits for the texture, not the other way round).
- Gain: the GPU no longer has tens of ms of copies ahead of the cull. Risk: medium (transfers between
  queues).

### Step 5 — Only if step 0 shows it pays: cull on a second queue
- A second queue of the same graphics family with a higher priority (no privilege), waiting only for
  the ticks of the cull's inputs. It only helps if the inputs (Hi-Z, pre-shader) are ready well before
  the dispatch; step 0 measures that.
- High risk, weeks; on the Vega 8 it can compete with drawing. It comes last and only with proof.

## How to approve each step (without loss)
- Image: `SOTC_RB_PUSH_VERIFY` with 0 differences; side-by-side captures at the title screen, the
  Shrine and the forest.
- FPS: the Shrine standing still, the opening demo and the 60 FPS route the same or better (Maximum +
  PS4 Pro, 60 FPS).
- Area changes: frames > 50 ms and the worst frame on the user's route, before and after, with
  `tools/entry_report.py`.
- Stability: a long user session without a crash before it becomes the launcher's default
  (DEFAULT_UPGRADES).

## Order
0 → 1 → 2 → (measure) → 3 → 4 → 5 only with proof. Steps 1 and 2 together should bring most of the
gain.

## Sources of the study
- shadPS4 PR #3404 (preventive flushes, never merged), RFC #4316 (batched readbacks).
- RPCS3 `VKGSRender.cpp` (early submission with a limit), `texture_cache_predictor.h`; PR #4973
  (ZCULL).
- Ryujinx: periodic early submission and on target changes (#3689, #4667, #4387).
- Xenia-canary PR #1325 (copying whole ranges back erased CPU writes: apply only what changed).
- NVIDIA "Vulkan Do's and Don'ts", AMD RDNA Performance Guide, VK_EXT_global_priority, Blender PR
  #165812 (HOST_CACHED memory for readbacks).
