# Plan: visibility (cull) on a second GPU queue (17 Nov 2026)

Step 5 of `PLAN-AREA-CHANGE.md`, now with the proof it asked for. Goal: the temple's dense stretches
(44–48 FPS) and the area changes, where the game waits for the visibility map the GPU computes in the
same frame. The user's rule: no loss of image or FPS; everything behind `SOTC_CULL_QUEUE` (0 = as
today).

## The proof (the user's playthrough, 22:46, `SOTC_GPU_TIMES=1`)

- Per ~21 ms GPU frame in the stretches at 45–48 FPS: ~10 ms of draws/dispatches, ~3–4 ms of
  barriers/copies, ~6–9 ms of GPU stopped between submissions (the game waiting for visibility).
- The game's readback waits: 20–27 ms per frame, almost all "gpu" (the GPU finishing what is in
  front; the port's queue ~1 ms, submission 0.3 ms).
- **Each dispatch of `0x50784801` (30–86 per frame) starts ~10 ms of GPU time after its inputs are
  ready** (the time between the GPU's last write to the pages it reads and its start); the largest of
  each frame 14–24 ms. It is queue time behind unrelated work.
- `SOTC_IDLE_FLUSH` (submit when the draw thread runs out of work) changed nothing: the GPU stops
  because the game has not sent the work yet.

## Resources of the cull programs (`SOTC CULL RESOURCES`)

| Program | Buffers (written) | Images | Note |
|---|---|---|---|
| `0x50784801` | 4 (1) | 0 | the one that waits most (~10 ms per dispatch); buffers only: **first target** |
| `0xc54081d1` | 4 (1) | 0 | ~200/frame, less slack |
| `0x4defcf7f` | 7 (2) | 0 | shadow |
| `0x2e0f474b`, `0x93aec24b`, `0xf94d23d4`, `0x729c541e` | 2–9 | 1 read | Hi-Z: image layout state between queues; later |

Readers of the result on the GPU: many programs, some 1–4 operations away (`0x9404c951`
dispatch-indirect at 1). The marking is per 64 KiB page (the game puts other data in the same pages):
part of it is a false positive, but there are real readers. So the graphics queue has to wait for the
second queue before the first reader.

## Design (MVP: only `0x50784801`, buffers only)

1. **Queue**: ask for a second queue of the graphics family (NVIDIA: 16 in family 0; the same family =
   no ownership transfer). `SOTC_CULL_QUEUE_PRIORITY` (the queue's priority above the main one).
2. **Its own scheduler** (`CullScheduler`): its own pool, command buffers and timeline semaphore,
   recorded straight on the draw thread (without the recording thread).
3. **Input dependency**: each 64 KiB page written by the GPU keeps the graphics tick of whoever wrote
   it. The cull dispatch waits (semaphore) for the newest graphics tick among what it reads; if it is
   the graphics command buffer not yet submitted, it submits the graphics one first (the cost of one
   submission).
4. **CPU data uploads** (`SynchronizeMemory`) of the cull's buffers go to queue 2's command buffer
   (redirected in `Scheduler::CommandBuffer()` while recording the bind and the dispatch); barriers
   too.
5. **Output**: the written ranges keep "written on queue 2, tick T2". A graphics bind that reads those
   ranges (the exact range, not the page) submits the graphics work up to there and the next graphics
   submission waits for T2.
6. **The game's readbacks** of a range written on queue 2: the copy goes on queue 2 and the game waits
   for T2 (not the graphics one). The same apply path with the heap guard.
7. **Write conflict** (queue 2 writing where pending graphics work still reads): before redirecting,
   check that no graphics op after the dependency tick read/wrote the ranges the cull writes; if one
   did, fall back to the normal path.
8. **Safety net**: any case not covered (images, GDS, conflicting ranges) uses today's path.

## Measurement and approval

- `SOTC_GPU_TIMES`: the culls' slack drops to near 0; the GPU stopped between submissions drops.
- FPS in the temple's stretches (44–48 today) and area entries (`tools/entry_report.py`).
- Image: identical captures (grass, horse, cloak, stairs: the symptoms of a wrong mask in the
  HiddenUserHere fork).
- `SOTC_CULL_QUEUE_VERIFY=1`: runs the cull on both queues and compares the mask byte by byte (0
  differences).
- Stability: the user's route + the ending up to the credits without a crash before it becomes the
  default.

## Risks

- Memory order between queues (the lesson of `SOTC_VIS_DIRECT`: end-of-pipe labels going out early let
  the game reuse memory the GPU was still writing). Here the labels do not change; queue 2 only runs
  ahead.
- The `Runtime`'s barrier tracking assumes one queue: queue 2's commands start after the semaphore
  (everything before is visible); the graphics commands recorded after the dependency and before the
  cull run in parallel — step 7 keeps them off the same ranges.
- Cost: one more submission per cull batch, semaphores per submission.
