# Exact fast path for depth-only draws (draw thread)

2026-10-26. Continues [ESCENA-TEMPLO.md](ESCENA-TEMPLO.md) §4 and §9 and closes [PREPASE-PLAN.md](PREPASE-PLAN.md) (step 0: NO-GO). Marks: [M] measured,
[E] estimated, [I] inference. 12 of 12 launches used (§7).

## 0. Summary

- **Step A (cleanup).** The pre-pass trial planner was removed entirely (`sotc_prepass_plan.h/.cpp`, `gpu/sotc/prepass_pairs.inc`, hooks in
  `liverpool.cpp/.h`, `vk_rasterizer.cpp/.h`, `videoout/driver.cpp`, the `top_level` parameter of `ProcessGraphics`; CMake had no entries of its own, it uses
  `GLOB`). The real fix that came out of it is **kept**: `depth_write` in the `RtMemo` key (`PrepareRenderState`), without the `NoteStaleRtMemo`
  counter. The build passes.
- **Result.** An **exact** fast path for depth-only draws (no colour target): it reuses the state work that did not change (the targets memo
  of `PrepareRenderState`, `BeginRendering`'s `RenderState` and the derivation of the dynamic state) when a cheap check
  proves that its inputs are the same. Switch `BbToggle::DepthFastPath` (**bit 28**, `1u << 28`; bit set = old path; **active by
  default**: the default mask in `src/runtime_memory.c`, bits 39, 59 and 60, does not include it).
- **VERIFY: 0 mismatches.** A full replay of the temple (the idle Shrine included): >= 40.3 M checks of `PrepareRenderState`, 24.8 M of
  `BeginRendering` and 34.1 M of dynamic state, and 135 M register chunks compared against the CP (`SOTC_DRAW_OPT_VERIFY`), all with 0 differences (§5).
- **A/B on the same binary, ABBA and BAAB.** Shrine (pooled): **+2.16 ± 0.29 FPS (+4.4%)** and **-1.02 ± 0.15 ms of `draw busy` (-5.4%)**. Temple
  (neighbouring windows of >= 5000 cmds/frame, pooled): **-0.184 ± 0.046 ms of `draw busy` per 1000 cmds (-5.5%) = -1.46 ± 0.38 ms/frame**, +2.7 ± 0.9 FPS; in the
  heavy stretch (>= 7000 cmds, 4 pairs) -2.1 ± 0.8 ms/frame. **It meets the criterion (>= 0.5 ms/frame or >= 2% FPS) in all four A/Bs.** It stays.
- **What is and is not the goal.** The switch groups three things (§4): register transport by differences (needed to know "no render
  register changed"), the targets memo with a check that does not compare registers, and the dynamic state. Per depth-only draw it saves
  **~0.19 µs of ~1.63 [M]** (instrumented), not the goal's 0.8 µs: the rest is per-draw work with data that changes in every draw (§3). The total
  gain is larger than that of the depth-only draws because each op's prefix (-0.035 µs) and the targets memo and dynamic state of the
  G-buffer draws (-0.12 µs) go under the same bit.

## 1. Step A: cleaning up the pre-pass planner

Removed: `gpu/shadps4/video_core/amdgpu/sotc_prepass_plan.h/.cpp`, `gpu/sotc/prepass_pairs.inc`, `Liverpool::PreplanScan/PreplanExecDraw/PreplanExecDispatch`,
`preplan_mutex/preplan_queue`, the `NotePacketIf` calls (10), `EndDcb`, the queue split in `SubmitGfx`, `ProcessGraphics`'s `top_level`,
`Rasterizer::PreplanFill*/PreplanArgsGpuModified` and the `SOTC PREPLAN` block of `driver.cpp`. The new files were not in git (they were simply deleted; see
PREPASE-PLAN.md P0.8). `SOTC_OP_STATS` (the pre-pass analysis of ESCENA-TEMPLO §9) was not touched. Kept: `depth_write` in `RtMemo`.

## 2. Breakdown by phase (depth-only draws, heavy temple) [M]

New instrumentation (diagnostics only, with `SOTC_DRAW_PHASES=1`): fine laps (`Sub`) inside the `DrawPhase` phases (`vk_rasterizer.cpp`; the clock
of the `Pipeline::BindResources` thunk is marked from `vk_pipeline_common.cpp`). The laps take ~8-10 ns each (there are ~28 per draw), so the
instrumented totals are ~10-15% above the real cost; the relative shares hold. `out/depth_table.py` averages the windows. Run `depth-ph`
(temple replay, 184 windows of >= 7000 cmds/frame, 4741 depth-only draws per frame):

| Phase (µs/draw, instrumented) | Base | What it contains |
|---|---:|---|
| `pre` | 0.078 | `PopPendingOperations` (0.046, almost all clock and `Scope`), register filters (0.023) |
| `prep` | 0.071 | `PrepareRenderState` with an RtMemo hit: lock 0.009, register comparison 0.021, LRU touches/`NoteFound` ~0.04 |
| `bbuf` | 0.360 | `BindBuffers`: flat buffer (copy to the ring) 0.036, `ClampRangeSize` 0.066, `ObtainBuffer` 0.169 (~3.5 calls), descriptor + `IsBufferAccessed` 0.074 |
| `btex` | 0.290 | `BindTextures`: ~0.02 without images; the rest are the DEPTH-RO draws with images (~0.8 µs) |
| `brest` | 0.060 | copy/clear checks per compute, user data, `MakeUserData` |
| `begin` | 0.126 | `BeginRendering`: lock 0.009, `FindDepthTarget` 0.079, HTile meta 0.011, `Transit` 0.022 |
| `refresh` | 0.010 | |
| `vtx` | 0.087 | `GetVertexInputs` + memo 0.026 (no vertex bindings), `BindIndexBuffer` 0.051 |
| `args` | 0.020 | |
| `pipe` | 0.117 | `pushConstants` thunk 0.039, `pushDescriptorSetKHR` thunk 0.066 |
| `dyn` | 0.081 | derivation of the dynamic state + `Commit` (the bit 60 memo is off by default) |
| `sched` | 0.050 | `scheduler.BeginRendering` (compares the `RenderState`, 0.021), `bindPipeline` 0.011, `draw` 0.012 |
| `post` | 0.098 | `ResetBindings` 0.075 (`AccessBuffer` per binding), `FlushPeriodic` 0.015 |
| **Total** | **1.444** | + op prefix 0.171 µs/op (a copy of 2.79 chunks, 178 dwords) |

The same run, redundancy against the previous draw: push constants equal 100%, `RenderState` equal 99%, **descriptors 0%** (every draw changes some
offset), pipeline 68%. The `RenderState` is almost always the same, but the targets memo and the dynamic state were not fully reused: the first
compared the targets' register structures and called `FindDepthTarget`/`Transit`/`TestAndTouchMeta` in `BeginRendering` (which had no memo), the second always
derived (the bit 60 memo was off).

## 3. What can be reduced exactly and what cannot

| Part | µs/draw | Verdict |
|---|---:|---|
| `begin` (`FindDepthTarget`, meta, `Transit`) | 0.126 | **Reducible**: a function of the depth registers, the image registry and the image's state. Done (§4.3) |
| `dyn` | 0.081 | **Reducible** when no input register changed. Done (§4.4); 17% of the draws do change (depth/stencil/cull) |
| `prep` (register comparison) | 0.021 | **Reducible**. Done (§4.2); the LRU touches remain, which are effects |
| op prefix | 0.171 | **Reducible** (copying whole chunks): transport by differences, 0.136 µs/op |
| `ObtainBuffer` + clamp + descriptor | 0.30 | **No**: ~3.5 ranges per draw with a new address (constant offset, VB, IB); each needs its CPU-modified pages lookup and its registration in the arena. A memo by (address, size) was already measured without a gain (LOTE-2-RESULTADOS, `SOTC_BUFFER_MEMO`) and here the addresses do not repeat |
| flat buffer (`bbFlat`) | 0.036 | **No**: a copy to the ring with a new offset in every draw (the command changes) |
| `ResetBindings` | 0.075 | **No**: `AccessBuffer` per binding with different ranges in every draw; it feeds the barriers and the readbacks |
| thunks (`pushConstants`, descriptors, `bindPipeline`, `draw`, `bindIndexBuffer`) | ~0.20 | **No** without changing the flow: the arguments change (descriptor offsets) or the command is mandatory; skipping repeated `bindPipeline`/`pushConstants` would change the recorded commands |
| `PopPendingOperations`, `FlushPeriodic`, filters | ~0.06 | Already early-outs; most of the measured cost is the clock |

That is why the goal of 0.5 µs per draw (from 1.3) cannot be reached exactly: of the ~1.2 real µs only ~0.3 µs is state that can be proven equal
(`prep` + `begin` + `dyn`), and ~0.19 is recovered.

## 4. Design

### 4.1 Knowing when no register changed: transport by differences and "relevance serials"

The draw thread receives the registers in each `BackOp`. With the default mask (bit 60 set) whole 64-dword chunks arrived (2.8 per op), so
"the chunk changed" says nothing. Now, with bit 28 clear, `BackAlloc` sends only the dwords that change value (the CP compares against `back_shadow`;
bit 60's code and verification, LOTE-2-RESULTADOS Lote 4), and `ExecuteBackOp` keeps three serials (`Liverpool::DrawRelSerial`): **RelRender** (the depth side's
registers + the depth extension), **RelColor** (`color_buffers`, `color_target_mask` + the colour extensions) and **RelDynamic** (the registers
read by `Update{ViewportScissor,DepthStencil,Primitive,Rasterization,ColorBlending}State`). Each serial goes up by one per op that changed **the value** of a
dword in its mask. The mask is built once from the fields' addresses (`DepthFastEnsureRelevance`; the dynamic list is that of
`CommitDynamicStateOld`, already verified 9.4 M times in Lote 4). `DB_DEPTH_CONTROL` is partial for RelRender (`SetRelevancePartial`, bits 0-2: stencil_enable,
depth_enable, depth_write_enable, the only thing that reaches the targets): without that `depth_func` changed the serial in ~15% of the draws (log `why-regs`:
`depth_control` 98% of the register misses). Until the masks are set each op raises all three serials (conservative). With the bit set (old
path) and bit 60 too, the chunks arrive whole and the serials almost always go up: the fast path does not activate even if forced.

### 4.2 `PrepareRenderState` (every draw class)

The existing memo (`RtMemo`) now keeps the serials (`rel_depth`, `rel_color`). A fast hit = a valid memo, **the same depth serial** (and colour serial if the draw
has colour targets), the same target mask, the same `ImageSetGeneration`, the same `gpu_modified_epoch`: the register comparison is skipped (that is the part
it removes) and the usual effects are repeated (LRU touches, `NoteFound`, the `bound_images` list, `is_target`). Anything else: the old path.

### 4.3 `BeginRendering` of a depth-only draw (`BeginRenderingFast`)

`BeginRendering` for `mrt_mask == 0` produces a `RenderState` that depends on: the depth registers (RelRender), the depth image and its state, the
image registry, the HTile metas, and it has effects on the texture cache. After a full `BeginRendering` without a clear in the state
(`depth_clear`/`stencil_clear` false, no colour target) `df_memo` is **recorded**: serial, image id, `ImageSetGeneration`, `gpu_modified_epoch`, `MetaEpoch`
(new: goes up when a meta is added/removed or a clear bit is set), the linked stencil image (`LastDepthStencil`), the `backing` pointer, the arguments of the
`Transit` and the `RenderState`. The next draw **reuses** it if, under the cache lock (BatchLock), everything holds (each condition counts its cause):

| Miss cause | Check (cheap, per draw) |
|---|---|
| nomemo | there is a memo (one was recorded and not invalidated) |
| regs | `DrawRelSerial(RelRender)` equal: no depth register nor the extension changed value |
| image | `db_desc.first` is the memo's image |
| gen / gpuepoch / meta | `ImageSetGeneration`, `gpu_modified_epoch` and `MetaEpoch` equal: `FindDepthTarget`'s lookups give the same and the HTile bit stays clear |
| flags | image `Registered` and `GpuModified` (`MarkWritten` does nothing), without `needs_rebind` (the `ASSERT`), `UpdateIsNoop` (not `Dirty`, tracked whole: `UpdateImage` does nothing except the touch) |
| backing | the same `backing` (the views and the layout are the memo's) |
| transit | `Image::TransitIsNoop` (new, a read-only mirror of `GetBarriers`, partial or full): there would be no barrier nor state change |

The effects `BeginRendering` does have in that case are repeated: the LRU touch of the image (`GetImage`) and of the linked stencil image, `usage.depth_target`,
`attachment_feedback_loop = false`. `Scheduler::BeginRendering` receives a `token` from the memo and skips the 400-byte comparison of the `RenderState` if the
current pass started with that same token (a new one is assigned at each recording; with another state or outside a pass the path is the usual one).

### 4.4 Dynamic state (every class)

`CommitDynamicState` hits if the previous derivation (of any draw) had the same `RelDynamic` serial, the same pipeline `write_masks`, the same
`attachment_feedback_loop` and the same `is_indexed` (the bit 60 memo did not have this last one). Then it only does `Commit` of what the object already has. Any
derivation through another path (the old path with the bit set, a thread without the draw thread) clears the memo (`df_dyn.valid`), so it does not survive changed values.

### 4.5 What was not touched

`ObtainBuffer`, `BindBuffers`, `BindTextures`, `BindVertexBuffers/IndexBuffer`, `Pipeline::BindResources`, `ResetBindings`, `FlushPeriodic`: they run
the same with the switch active or not. **A draw's Vulkan commands are a function of (RenderState, push constants, descriptors, VB/IB, the dynamic state's dirty
bits, pending barriers); the fast path only replaces the derivation of the first three ends that do not depend on the draw, and only with proven
equality.**

## 5. VERIFY (`SOTC_DEPTHFAST_VERIFY=1`)

Mechanism: on every hit, the old path runs too and is compared.

- **`PrepareRenderState`**: the hit by serial requires the old comparison (memcmp of `depth_buffer`, `depth_view`, `color_buffers`, extensions,
  masks) to say hit too; if not, it is counted, printed and the old result is used.
- **`BeginRendering`**: the hit's effects are reproduced, a snapshot of the image is taken (flags, `usage`, `binding`, `backing`, layout/access/stage,
  subresources, tracked range, the LRU tick of the image and of the stencil one, `tick_accessed_last`, HTile mask, `attachment_feedback_loop`, `needs_barrier`, pending
  image barriers), the **full** `BeginRendering` runs on top and it requires: an identical snapshot (the full path changes nothing else), no
  new barrier and a `RenderState` byte for byte equal to the memo's. The full path's state is used.
- **Dynamic state**: on every hit it is derived again with every dirty bit at zero (like bit 60's verify): any bit that goes up is a value
  the memo would have left behind.
- **Transport** (`SOTC_DRAW_OPT_VERIFY=1`, already existing): the draw thread's registers equal the CP's in every dirty chunk.

**The recorder's thunk stream is not captured** (the original request): running the slow and the fast path for the same draw in the same stream is not possible (the
flat buffer's `Copy` advances the ring, the LRU touches and the write marks are not undone), and the recorded commands are a function of the values
compared above. What is checked are the **recorder's inputs** (and the effects on the cache), not its bytes. It is the weakest part of the proof: an
error in something VERIFY does not look at (e.g. a `RenderState` field that was not memcmp'd) would not be seen; `RenderState` is compared whole (memcmp, no padding).

Results (full replay of the temple with `SOTC_DEPTHFAST_VERIFY=1`; accumulated counters of `SOTC DEPTHFAST ... VERIFY`):

| Run | `PrepareRenderState` | `BeginRendering` | Dynamic state | Register chunks | Note |
|---|---:|---:|---:|---:|---|
| `df-verify` (v1) | 1.7 M, 0 | 0 | 28 M, 0 | | `BeginRendering`'s memo was never recorded: `RenderAttachment::is_clear` is a union with `has_depth` and always said "with a clear"; a single serial too coarse (30% hits) |
| `df-verify2` | 35.3 M, 0 | 21.4 M, 0 | 33.8 M, 0 | | after separating the colour serial and fixing the union |
| `df-verify3` | **40.3 M, 0** | **24.8 M, 0** | **34.1 M, 0** | | after the partial mask of `depth_control` (final binary) |
| `df-verify4` | 38.2 M, 0 | 22.8 M, 0 | 32.1 M, 0 | **135.3 M, 0** | final binary + `SOTC_DRAW_OPT_VERIFY` |

The replay starts with ~100 s of the idle Shrine (5.7 k cmds/frame) and continues with the temple route (a heavy stretch of 7.8-8.4 k cmds/frame), so it covers
both scenes. 0 `SOTC DEPTHFAST VERIFY:` messages and 0 `register chunk ... differs` in all of them.

Hit rates (runs with the final binary, the whole replay; `df-verify3` and `df-verify4` agree):

| | Hit | Misses |
|---|---:|---|
| `PrepareRenderState` (every draw) | **98.5%** | 1.5% registers/images (0.02% where the old memo would have hit) |
| `BeginRendering`, depth-only draws | **90-91%** | `transit` ~8% (DEPTH-RO draws: the texture pass leaves the depth in another layout and the `Transit` is real), `regs` 0.8%, `nomemo` 0.3%, `gen` 0.01%; `image`, `gpuepoch`, `meta`, `flags`, `backing`: 0 |
| Dynamic state (every draw) | **83%** | the rest really changes (depth/stencil/cull: it is derived and `Commit`ted) |

Before the partial mask (`df-phase2`) they were 84% (`BeginRendering`) and 88% (`PrepareRenderState`).

## 6. A/B on the same binary (`out/bb-probe.depthfast.exe`)

`BB_TOGGLE_FILE` switches after each `SOTC FPS` line (A = fast path, bit clear; B = old path, bit 28 set). Scripts: `out/depth_ab.sh` (Shrine,
`BENCH_MEASURE=150`) and `out/depth_ab_temple.sh` (temple replay, alternating every 5 s), `out/rb_stats.py`, `out/depth_pair2.py`, `out/depth_phase_ab.py`.

### 6.1 Shrine (windows from 100 s, 5 s each)

| Run | Order | ON FPS (n) | OLD FPS (n) | ON-OLD FPS | `draw busy` ON / OLD (ms) | ON-OLD busy |
|---|---|---|---|---|---|---|
| `dfs2` | ABBA | 52.46 (14) | 50.53 (13) | +1.93 | 17.59 / 18.51 | **-0.93** |
| `dfs3` | BAAB | 50.98 (13) | 48.72 (14) | +2.26 | 18.40 / 19.46 | **-1.05** |
| Combined | | 51.75 (27) | 49.59 (27) | **+2.16 ± 0.29 (+4.4%)** | 17.98 / 19.00 | **-1.02 ± 0.15 ms (-5.4%)** |

(`dfs1`, the first run, with the default 40 s measurement: 4 ON windows and 2 OLD, +2.8 FPS and -1.12 ms; dropped for too few samples, not in the combined figure.)

### 6.2 Temple (windows from 70 s; each ON window compared with the average of its OLD neighbours, both of >= 5000 cmds/frame)

| Run | Order | Pairs | `busy` per 1000 cmds ON-OLD | `draw busy` ON-OLD | FPS ON-OLD |
|---|---|---:|---|---|---|
| `dft1` | ABBA | 7 | -0.180 ± 0.105 ms | -1.37 ± 0.68 ms/frame | +3.13 ± 1.75 |
| `dft2` | BAAB | 12 | -0.186 ± 0.043 ms | -1.51 ± 0.48 ms/frame | +2.46 ± 0.99 |
| Combined | | 19 | **-0.184 ± 0.046 ms (-5.5% of 3.34)** | **-1.46 ± 0.38 ms/frame** | **+2.71 ± 0.87** |
| Heavy stretch (>= 7000 cmds/frame, both runs) | | 4 | -0.196 ± 0.083 ms | -2.11 ± 0.82 ms/frame | +2.65 ± 1.32 |

Unpaired averages (windows >= 5000 cmds): ON 47.02 FPS, 20.13 ms; OLD 45.27 FPS, 21.18 ms (23 windows each, the same average cmds/frame of 6392). The heavy stretch
lasts 5-6 windows per run: the pairing is what resolves the variation in scene load (the end-to-end A/B without pairing does not resolve it,
ESCENA-TEMPLO §8.4).

### 6.3 By phase, the same run (temple replay with `SOTC_DRAW_PHASES=1` and the bit alternating every 5 s; windows of >= 5000 cmds/frame, ON n=386, OLD n=376) [M]

Instrumented (µs/draw):

| Phase | Depth-only ON | OLD | ON-OLD | G-buffer ON | OLD | ON-OLD |
|---|---:|---:|---:|---:|---:|---:|
| `pre` | 0.103 | 0.111 | -0.008 | 0.132 | 0.129 | +0.003 |
| `prep` | 0.072 | 0.085 | -0.013 | 0.119 | 0.152 | -0.033 |
| `bbuf` | 0.364 | 0.375 | -0.011 | 0.844 | 0.850 | -0.005 |
| `btex` | 0.319 | 0.331 | -0.011 | 0.984 | 1.006 | -0.021 |
| `begin` | 0.079 | 0.171 | **-0.093** | 0.703 | 0.700 | +0.002 |
| `dyn` | 0.055 | 0.098 | **-0.043** | 0.034 | 0.088 | **-0.054** |
| rest (`brest`, `refresh`, `vtx`, `args`, `pipe`, `sched`, `post`) | 0.513 | 0.521 | -0.008 | 0.737 | 0.743 | -0.006 |
| **Total** | **1.446** | **1.632** | **-0.186** | **3.553** | **3.670** | **-0.117** |

Op prefix (the same run): 0.136 µs/op with 2.07 chunks and 29 dwords per op (ON) against 0.171 µs with 2.79 chunks and 178 dwords (OLD): -0.035 µs/op. The CP's `BackAlloc`
0.99 against 1.03 µs (within noise).

Per frame of the heavy stretch [E]: 4710 depth-only draws x 0.186 + 2465 G-buffer x 0.117 + ~8900 ops x 0.035 = 0.88 + 0.29 + 0.31 = **-1.47 ms**, in agreement with
the -1.46 ± 0.38 ms measured end to end (§6.2). The depth-only draws are 60% of the gain.

## 7. Launches (12 of 12)

| # | What | What for |
|---|---|---|
| 1 | `depth-ph`: temple replay, `SOTC_DRAW_PHASES=1`, binary without the fast path | base breakdown (§2) |
| 2 | `df-verify`: VERIFY, first version | found `BeginRendering`'s memo not being recorded and the serial too coarse |
| 3 | `df-verify2`: VERIFY | 0 mismatches; `BeginRendering` hits 75-90% |
| 4 | `df-phase2`: phases + `SOTC_DEPTHFAST_WHY=1` | 98% of the register misses were `depth_control` -> partial bits |
| 5 | `df-verify3`: VERIFY, final binary | 0 mismatches (§5) |
| 6 | `dfs1`: Shrine A/B with 40 s of measurement | not enough samples (dropped) |
| 7-8 | `dfs2`, `dfs3`: Shrine ABBA and BAAB, `BENCH_MEASURE=150` | §6.1 |
| 9-10 | `dft1`, `dft2`: temple ABBA and BAAB | §6.2 |
| 11 | `df-verify4`: VERIFY + `SOTC_DRAW_OPT_VERIFY` | register transport by differences (135 M chunks, 0) |
| 12 | `dftp`: temple, alternating the bit with `SOTC_DRAW_PHASES=1` | table by phase ON/OLD (§6.3) |

No VERIFY run of the Shrine alone was done: the temple replay starts at the idle Shrine (windows of 50-95 s with 5.7 k cmds/frame) and the counters are
accumulated; the binary is the same.

## 8. Kept, removed, what is missing

- **Everything is kept** (bit 28, active by default): transport by differences with relevance serials, a targets memo by serial, `BeginRenderingFast`, a dynamic state
  memo by serial, `Scheduler::BeginRendering(token)`, `MetaEpoch`, `Image::TransitIsNoop`, `TextureCache::UpdateIsNoop/LastDepthStencil/TouchLinked/LruTickOf/MetaClearMask`.
  With bit 60 set (default) and 28 clear the registers travel by differences: that transport's behaviour is bit 60's (verified 135 M chunks, 0
  differences, and 40.9 M in Lote 4); `src/runtime_memory.c` documents that 60 stays off by default and that 28 effectively turns it on.
- **Removed**: the pre-pass planner (§1). Nothing of the new work was removed.
- **A cheap extension not done** (outside the brief, the same mechanism): the G-buffer draws' `BeginRendering` costs 0.70 µs per draw (7 targets: `UpdateImage`, `FindRenderTarget`,
  CMask meta, `Transit` per target; 2465 draws/frame = 1.7 ms) and has no memo. It needs memoising the effects per colour target (`SetBackingSamples`, `download_images`,
  the `hudless` capture, the CMask clear, `is_bound` -> feedback loop) and its own VERIFY.
- The binary with the change has no PGO profile for the new functions (`BeginRenderingFast`, `DepthFast*`); run `tools/pgo_train.sh` before packaging. The shader cache does not change.
- The DEPTH-RO draws (15% of the depth-only ones) do not hit in `BeginRendering`: the depth's `Transit` is real (a barrier) in every draw.

## 9. Reproduce

- Variables (diagnostics only): `SOTC_DEPTHFAST_VERIFY=1` (§5), `SOTC_DEPTHFAST_WHY=1` (which depth register moved the serial, `SOTC DEPTHFAST` line), `SOTC_DRAW_PHASES=1`
  (fine laps, `SOTC DRAWPHASE ... sub us/draw`), `SOTC_DRAW_OPT_VERIFY=1` (transport). A counter line `SOTC DEPTHFAST draws ...` every ~1 M draws in `user/last_run.log`.
- Scripts: `out/depth_table.py <log> [min cmds] [class]` (base table), `out/depth_phase_ab.py <bit> <min cmds> <log> [class]` (ON/OLD by phase), `out/depth_ab.sh` and
  `out/depth_ab_temple.sh <name> 268435456 <ABBA|BAAB> [--env ...]`, `out/rb_stats.py <log> <tmin> 268435456`, `out/depth_pair2.py 268435456 <min cmds> <tmin> <logs...>`.
- Code: `gpu/shim/bbport_toggles.h` (bit), `amdgpu/liverpool.h/.cpp` (serials, `BackAlloc`, `ExecuteBackOp`), `renderer_vulkan/vk_rasterizer.h/.cpp` (`DepthFast*`,
  `BeginRenderingFast`, `CommitDynamicState`, `PrepareRenderState`), `vk_scheduler.h/.cpp` (token), `vk_runtime.h` (`PendingImageBarriers`), `texture_cache/*` (`MetaEpoch`, etc.),
  `image.h/.cpp` (`TransitIsNoop`). Everything marked `sotc:`.
