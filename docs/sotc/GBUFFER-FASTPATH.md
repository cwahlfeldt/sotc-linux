# Exact fast path for G-buffer draws (colour + depth): design

2026-10-26. Phase 1 (read-only: no file in `gpu/`, `src/`, `tools/`, `scripts/` touched; nothing built or launched). Continues
[DEPTH-FASTPATH.md](DEPTH-FASTPATH.md) §8 ("a cheap extension not done"). Marks: [M] measured (logs `out/run-dftp.txt`, `out/run-depth-ph.txt`),
[C] read in the code, [E] estimated, [I] inference. The line numbers are from the current tree (with the depth path's uncommitted changes).

## 0. Summary

- The G-buffer draw (class "G-buffer" = `mrt_mask` with bit 4, `ClassOf`, `vk_rasterizer.cpp:290`; ~7 colour targets + depth) leaves
  `BeginRenderingFast` through the `mrt_mask != 0` gate (`vk_rasterizer.cpp:4011-4014`) and runs the full `BeginRendering`
  (`vk_rasterizer.cpp:4112-4290`) in every draw: per target `GetImage`, `UpdateImage`, `SetBackingSamples`, `FindRenderTarget`, `TestAndTouchMeta`,
  `Transit` and filling in the `RenderState`; then the depth (`FindDepthTarget`, HTile meta, `Transit`). The dynamic state (`dyn` 0.03 µs) and
  `PrepareRenderState` (memo by serials, 99% hits) are **already** covered by the depth path: what is left is `BeginRendering`.
- [M] A G-buffer draw's `RenderState` is identical to the previous draw's in ~100% of cases (`same%: rstate=100`, `run-dftp.txt`,
  `run-depth-ph.txt`), and `PrepareRenderState` hits in 99.3% of all draws (`prep hit 1041427 miss 7149` of 1.05 M). The mechanics of
  `BeginRenderingFast` extend to N targets with the same serials (RelRender + RelColor), `ImageSetGeneration`, `gpu_modified_epoch` and `MetaEpoch`, plus
  per-target checks (flags, `backing`, `TransitIsNoop`, `binding.is_bound`, the pipeline key's samples).
- **Realistic saving: 0.15-0.35 µs per G-buffer draw = 0.4-0.8 ms/frame in the heavy temple [E], not the ceiling's 1.7 ms** (0.70 µs x 2465). Reason (§5): the
  0.70 µs are with `SOTC_DRAW_PHASES` and carry ~42 `rdtsc` reads inside `BeginRendering` (5 laps per target), and the repetition is not free
  (~0.2-0.25 µs for 7 targets + depth). **Step 0 is mandatory before implementing: measure `BeginRendering` without the laps** (§6). If the real cost is
  < ~0.35 µs, the benefit does not justify the risk and the better lever is `BindTextures` (§7).
- Implementation: its own memo `gb_memo` (it does not share a slot with `df_memo`), a new switch `BbToggle::GBufferFastPath` (bit 29 if it is free, §4.1; if not, bit 31),
  a VERIFY that reproduces the effects, runs the full `BeginRendering` on top and compares a per-target snapshot + the `RenderState` byte for byte.

## 1. What a G-buffer draw does today and what the depth path already covers

Order in `Rasterizer::Draw` (`vk_rasterizer.cpp:1760-1877`; `DrawIndirect` `:1879-2102` repeats the same sequence and calls the same `BeginRenderingFast`, `:1944`).
Cost per G-buffer draw, instrumented µs [M] (`run-dftp.txt`, `run-depth-ph.txt`; windows with 11-12 k G-buffer draws): `begin` 0.59-0.70, `prep` 0.11-0.14,
`bbuf` 0.85-0.89, `btex` 0.94-1.16, `pipe` 0.25-0.29, `post` 0.19-0.23, total 3.44-3.79.

| Step | Where [C] | Depth path (today) | G-buffer (today) |
|---|---|---|---|
| `PrepareRenderState`: `RtMemo` memo by the serials `rel_depth`/`rel_color`, `mrt_mask`, `ImageSetGeneration`, `gpu_modified_epoch` | `:892-1060`, hit `:913-922`; the hit's effects (`GetImage`, `NoteFound`, `bound_images`, `is_target`) `:974-993` | covered | **covered** (`num_cb != 0` also requires `rel_color`, `:917-918`). Residue: the `active_mask` loop (`:906-908`, 7 `GetMask`) is computed on the hit too although only the miss uses it; the effects loop touches 8 images (~0.05-0.07 µs) |
| The gate to `BeginRenderingFast` | `:4002-4014` | memo `df_memo`, 90-93% hits | **`mrt_mask != 0` -> full `BeginRendering`** |
| `BeginRendering` per colour target: `GetImage` (LRU touch) + the `needs_rebind` check (a new lookup with `FindImage` that also **mutates `cb_descs[cb].first` and `bound_images`**) | `:4137-4141` | n/a (no colour) | every draw |
| `UpdateImage` (`LockCounted`, `TrackImage`, `TouchImage`, `RefreshImage`) | `:4142`, `texture_cache.h:419-426` | `UpdateIsNoop` in the check | every draw |
| `runtime.SetBackingSamples(image, key.color_samples[cb])` | `:4144`, `vk_runtime.cpp:644-719` (returns at once if `backing->num_samples` matches) | n/a | every draw; **depends on the pipeline key**, not on registers |
| `FindRenderTarget(update=false)`: `MarkWritten` (`GpuModified` flag; with `MipTailMode()` it looks for overlaps if it is not set yet), the `download_images` queue if `readback_linear_images` and the image is linear/<=8 px, `usage.render_target`, `surface_metas.emplace` of CMASK/FMASK (bumps `MetaEpoch` if it inserts), `image.FindView(view_info, false)` | `:4146`, `texture_cache.cpp:896-940` | n/a | every draw |
| `TestAndTouchMeta(col_buf.CmaskAddress(), slice)` -> `is_clear` (consumes the CMASK bit) | `:4155`, `texture_cache.h:522-531` | HTILE: memo with `MetaEpoch` | every draw (a hash lookup per target even with `fast_clear` off, because `CmaskAddress()` comes from the register: `image_info.cpp:77` only sets `meta_info.cmask_addr` with `fast_clear`) |
| The target's transition to `ColorAttachmentOptimal` (`ColorAttachmentOutput`, `Write\|Read`, range = `desc.view_info.range`) or, if `image->binding.is_bound`, to feedback-loop/`General` with a prior `FlushBarriers()` and `attachment_feedback_loop = true` | `:4162-4181`, `vk_runtime.cpp:171-177`, `image.cpp:352-450` | `TransitIsNoop` (depth) | every draw, one `Transit` per target |
| The `RenderState`'s size/layers (`min` with `image->info.size >> mip`, the view's layers), `RenderAttachment` (view, layout, `clear_value`, `is_clear`), `usage.render_target` | `:4184-4196` | memo | every draw |
| `TakeHudless`: if `cb == 0 && image->usage.vo_surface` it sets `hudless_vo*` | `:4197-4202`, flag in `vk_presenter.h:92` | n/a | every draw (an effect outside the `RenderState`) |
| Depth: `FindDepthTarget` (stencil lookup by regions + `AssociateDepth`, `surface_metas.emplace` HTILE), `TestAndTouchMeta` HTILE, `Transit` | `:4209-4281`, `texture_cache.cpp:942-990` | `DepthFastBeginCheck` (`:3915-3950`) | every draw. In G-buffer it weighs more than in depth-only: `begin split ... depth=0.13` [M] |
| `scheduler.BeginRendering(state, token)` | `:1833`, `vk_scheduler.cpp:86-146` | the token skips the 296-byte `memcmp` | token always 0 -> `memcmp` (schBegin 0.029 µs [M]) |
| Dynamic state (viewport, blend, `write_masks`, ...) | `CommitDynamicState` `:4544-4591` | memo by `RelDynamic` | **covered** (`dyn` 0.088 -> 0.034 µs ON/OLD in G-buffer [M]); there is nothing more to take |
| Descriptors / bindings (`BindBuffers`, `BindTextures`, `Pipeline::BindResources`, `ResetBindings`) | `:3454-`, `:2833-2862` | unchanged | unchanged (see §7) |

A note on how `begin` is measured [C]: `BeginRendering` carries `DrawPhase::LapStart/Lap/Sub` (`vk_rasterizer.cpp:4114,4130,4143-4160,4183,4204,4214,4233,4287-4288`; `Now()` =
`__builtin_ia32_rdtsc()`, `vk_rasterizer.h:36`). Per target there are **5 laps** (4143, 4145, 4147, 4160, 4183): with 7 targets that is 35 reads, plus ~7 for the depth
and the ends: ~42 reads per draw. The `samples` lap (which only measures `SetBackingSamples`, an immediate return) shows **0.07-0.12 µs per draw** in both logs [M]: that is almost
only the clock's cost (~13 ns per read and target).

## 2. Invariants that make repeating the previous `RenderState` exact

`BeginRendering` (a consecutive G-buffer draw, without a clear) is a function of:

| Input | How it is guaranteed not to have changed | What breaks it |
|---|---|---|
| `key.mrt_mask`, `key.color_samples[cb]` (from the pipeline key: the pipeline changes in ~20% of the draws, `pipe=80-83` [M]) | compare `mrt_mask` and the 8 `u8` of `color_samples` with the memo's | a different mask between pipelines of the same stretch (MRT sets, ESCENA-TEMPLO §3: 4 sets of 7): a `mask` miss, full fallback |
| `regs.color_buffers[cb]`, `color_target_mask`, colour extensions (CmaskAddress, view, format) | the `RelColor` serial equal (it only goes up if a dword of the mask changes **value**, `liverpool.cpp:418-500`) | a change of MRT set (about 4 per frame) |
| Depth registers, `color_control` (`Disable` mode), `depth_render_control` (clear), `DB_DEPTH_CONTROL` bits 0-2, the depth extension | the `RelRender` serial equal (`DepthFastEnsureRelevance`, `:3844-3911`) | the 16 draws with `GREATER` writes at the start of the G-buffer, late PRE-Z |
| Which image each target is: `cb_descs[cb].first`, `db_desc.first` (and its `desc`) | `ImageSetGeneration` + `gpu_modified_epoch` (those of `RtMemo`) **and** comparing the ids with the memo's (another failed `PrepareRenderState` or a different `mrt_mask` rewrites `cb_descs`) | images added/removed (streaming, depth/colour twins: ~100 conversions/s in the open world, `texture_cache.cpp:350-413`); `needs_rebind` |
| The state of each image: `Registered`, `GpuModified` (`MarkWritten` has no effect), not `Dirty` and tracked whole (`UpdateIsNoop`, `texture_cache.h:590-595`: `UpdateImage` only touches the LRU), `num_samples <= 1`, without `needs_rebind` | reading the flags under `BatchLock` (the CP/fault handler change flags under the same mutex) | a CPU write over the target (`CpuDirty`), losing partial tracking, MSAA |
| `backing` (views, layout, `SetBackingSamples`) | the same `backing` pointer as when recorded (the `BackingImage`s live in a `std::deque`: stable addresses; the view lists only grow) | `SetBackingSamples` in another operation (copies, uploads, resolve) |
| The target's `Transit` without a barrier or state change | `Image::TransitIsNoop(ColorAttachmentOptimal, Write\|Read, ColorAttachmentOutput, range)` (`image.cpp:310-350`; stricter than `GetBarriers`: it also compares the stage) | the target was sampled/written by another operation between two draws (a real barrier); compute that writes the target |
| The CMASK/HTILE clear bit already consumed, and not set again | `MetaEpoch` equal (goes up in `ClearMeta`, `TouchMeta(.., true)`, entries added/removed: `texture_cache.h:538,550`, `.cpp:925,934,955,2241-2249,2307-2315`) | `ClearMeta` by a metadata dispatch/`FillBuffer` (`vk_rasterizer.cpp:2900,4347`): <= tens per frame |
| `RenderAttachment::is_clear` / `depth_clear` / `stencil_clear` = false when recorded | only a memo whose state does not clear is recorded (like `DepthFastRecord`, `:3967`); the state of the draw that clears is **not** the next one's (the bit is consumed) | the first draw after a clear: there is no memo -> full, and the next one records |
| `image->binding.is_bound` (sampling the target itself: a feedback loop) | read **in every draw** (set by `BindTextures`, which runs first, `:1805` against `:1813`); `false` is required for every target | a target sampled by the PS (SSR, reading the depth buffer as a texture if it is a colour twin): the full path handles it with `eAttachmentFeedbackLoopOptimalEXT` and `attachment_feedback_loop = true` |
| `usage.vo_surface` of target 0 (the `hudless_vo*` effect) | required false when recorded and read again on every hit (one bit) | the video out surface (the final composite draw): full |
| Side effects: `download_images.emplace` (not idempotent over time: `ProcessDownloadImages` empties the set), `image.usage.render_target` | do not record if `readback_linear_images && (!is_tiled \|\| width <= 8)`; the `usage` is an idempotent store that is repeated | linear targets with readback (not the G-buffer's) |

Effects that **do** have to be repeated on every hit (the others of `BeginRendering` are null under the conditions above): `attachment_feedback_loop = false`; the LRU touch of each image
(`GetImage` and `UpdateImage`'s coincide within the same `gc_tick`: `LeastRecentlyUsedCache::Touch` returns as soon as `item.tick >= tick`, `lru_cache.h:35-39`, ~3-5 ns); `usage.render_target = 1` and
`usage.depth_target = true`; the touch of the linked stencil image (`TouchLinked`, already exists). `NoteFound`/`bound_images`/`is_target` are done by `PrepareRenderState` before, not `BeginRendering`.

Cases that make the memo wrong if forgotten (all have a check above): the first draw after a clear; targets also sampled (feedback); CMASK/FMASK metadata that changes through a fast clear (`MetaEpoch`);
`SetBackingSamples` with a copy between MSAA backings (`backing` changes); an image recreated by a depth/colour conversion (`ImageSetGeneration`); `needs_rebind` (the full path reassigns `cb_descs[cb].first`);
a different `mrt_mask`/`color_samples` with the same registers (the pipeline key); target 0 = the video out surface (hudless).

## 3. What is and is not repeatable (decision)

Everything above can be checked with per-target reads, without touching hash tables: the repetition is exact when (Register, Image, State, Backing, Transit, Meta, Clear, is_bound, vo_surface) hold. What **cannot** be skipped without
changing behaviour: the LRU touches (an effect observable by the GC) and reading each image's flags (the CP and CPU faults change them between draws). That sets a hit's minimum cost at ~20-25 ns per target [E].

## 4. Implementation plan (phase 2, to be requested later)

### 4.1 Switch

`BbToggle::GBufferFastPath` (bit set = old path; **active by default**: it is not in the default mask of `src/runtime_memory.c:1402`). Bit 29: `bbport_toggles.h` says
"bits 20-29 are used as raw debug switches" (camera/motion/upscaler); `grep` in `gpu/` and `src/` finds no use of `1<<29`, but that `grep` has to be repeated when starting. If in doubt, **bit 31**
(`1u << 31`, free; `UpdateImageFastPath` is 30). It also requires `DepthFastActive()` (the draw thread + the relevance masks built): without transport by differences the serials always go up. Honoured live, read per draw, like bit 28.

### 4.2 Structures (`vk_rasterizer.h`)

```
struct GBufferFastMemo {            // one slot, separate from df_memo (they do not overwrite each other: DepthFastRecord invalidates its own with colour)
    bool valid{};
    u32 rel_render{}, rel_color{}, mrt_mask{};
    std::array<u8, 8> samples{};                 // key.color_samples when recorded
    u64 image_generation{}, gpu_epoch{}, meta_epoch{};
    struct Att { VideoCore::ImageId id{}; const void* backing{}; } color[8]; // null id = empty slot
    DepthFastMemo depth;                         // db_id, stencil_id, backing, layout/access/stage/range (reuses fields and the check)
    u64 token{};
    RenderState state{};
};
```

### 4.3 Functions

- `Rasterizer::BeginRenderingFast` (`:4002`): remove the early return for `mrt_mask != 0` **only** if `GBufferFastPath` is active; for `mrt_mask != 0` call `GBufferFastCheck` / `Apply` / `Record`. A single point, used by `Draw` and `DrawIndirect`.
- `u32 GBufferFastCheck(const GraphicsPipeline*)`: under `BatchLock`; causes (like `c.cause[]`): `nomemo`, `mask` (mrt_mask/samples), `regs` (RelRender/RelColor), `ids` (`cb_descs[cb].first`/`db_desc.first`), `gen`, `gpuepoch`, `meta`, `flags` (Registered/GpuModified/needs_rebind/`UpdateIsNoop`), `bound` (`is_bound`), `vo` (target 0's `usage.vo_surface`), `backing`, `transit` (colour), `transit_depth`. For the depth part, extract from `DepthFastBeginCheck` (`:3915-3950`) a function `DepthSideCheck(const DepthFastMemo&)` and call it from both (without changing its behaviour: the depth verify already has 0 mismatches in 24.8 M).
- `void GBufferFastApply()`: `attachment_feedback_loop = false`; per non-empty target `GetImage(id)` + `usage.render_target = 1`; depth like `DepthFastBeginApply` (`:3955-3960`).
- `void GBufferFastRecord(const RenderState&, const GraphicsPipeline*)`: after a full `BeginRendering`; record only if: no `is_clear`/`depth_clear`/`stencil_clear`; `attachment_feedback_loop == false`; for each non-empty image `!needs_rebind`, `Registered`, `GpuModified`, `UpdateIsNoop`, `num_samples <= 1`, no linear readback, `backing->num_samples == key.color_samples[cb]`; target 0 without `vo_surface`; the `cb_descs` ids equal to those used (the full path may have reassigned them); plus the current `TransitIsNoop` check (so as not to record a state that has just produced a barrier). Otherwise, `valid = false` and a `not-recorded` counter per cause.
- The colour `Transit` needs no fields of its own: they are constants (`ColorAttachmentOptimal`, `ColorAttachmentOutput`, `Write|Read`) and the range comes from `cb_descs[cb].second.view_info.range`, which does not change while `cb_descs` and the serials match (the same assumption as `RtMemo`).
- `Scheduler::BeginRendering(state, token)` already knows how to skip the `memcmp` with the token (`vk_scheduler.cpp:86-99`): `gb_memo.token` is passed (the shared counter `df_next_token`).
- Separate micro-adjustments (no risk, ~0.03-0.05 µs per G-buffer draw [E]): move `PrepareRenderState`'s `active_mask` loop to the miss path (`:906-908`); and make `PrepareRenderState`'s hit and `GBufferFastApply` not repeat `GetImage`+`NoteFound` over the same 8 images (today: `:975-988` and then `:4137`).

### 4.4 VERIFY (`SOTC_DEPTHFAST_VERIFY=1`, the same mechanism; or `SOTC_GBFAST_VERIFY=1`)

Like `:4034-4106`: on every hit, `GBufferFastApply`; snapshot; the **full** `BeginRendering` on top; snapshot; require (a) a `RenderState` byte for byte equal to the memo's, (b) an identical snapshot, (c) no
new barrier (`runtime.PendingImageBarriers()`), use the full path's result. The snapshot is widened per target (an array of 8 + depth): `flags`, `usage`, `binding`, `backing`, layout/access/stage, `subresource_states.size()`,
`track_addr/_end`, LRU tick, `tick_accessed_last`; the target's CMASK mask (`MetaClearMask(CmaskAddress)`) and HTILE; plus globals: `attachment_feedback_loop`, `needs_barrier`, `bound_images.size()`, the `cb_descs` ids, `hudless_vo` (the full path must not set it: that checks the `vo_surface` exclusion),
the images' `LruTickOf`. Any difference is counted and printed (the first 20); accumulated counters in the `SOTC DEPTHFAST` line (add `gb cand/hit/cause[]`).
Limits (as in DEPTH-FASTPATH §5): it does not verify the bytes of the recorder's thunks (they are a function of `RenderState`, descriptors, etc.); a `RenderState` field outside the `memcmp` would not be seen, but `RenderState` is compared whole and without padding (`static_assert has_unique_object_representations`).
VERIFY's acceptance criterion: a replay of the temple + Shrine with >= 20 M G-buffer hits checked and 0 mismatches.

### 4.5 Measurement and launches (suggested budget: 8)

1. **Calibration + "count only" mode** (1 launch): build with a diagnostic switch `SOTC_DRAW_LAPS=0` that removes `BeginRendering`'s laps (`Lap`/`LapStart`; the `Mark`s stay) and with `GBufferFastCheck` running without applying (cause statistics). It tells: the G-buffer's real `begin`, and the real hit rate by cause. **Criterion to continue: real `begin` >= 0.35 µs and hits >= 90%.**
2. VERIFY of the temple (+ the idle Shrine at the start): 1-2 launches.
3. A/B on the same binary with the bit alternating every 5 s, ABBA and BAAB, temple and Shrine (`out/depth_ab.sh`, `out/depth_ab_temple.sh`): 4 launches. 1 phases launch (`SOTC_DRAW_PHASES=1` with laps off) for the ON/OLD table by phase.
4. `tools/pgo_train.sh` before packaging (the new functions have no profile).

## 5. Expected hit rate and saving

**Hits [E]**: 93-98% of the G-buffer draws. Basis: `rstate=100%` against the previous draw; `PrepareRenderState` 99.3% [M]; the depth path sees `regs` 0.8-1.3%, `gen` 0.01%, `meta` 0%, `flags`/`backing` 0% and `transit` 6-8% (only from the DEPTH-RO draws). Expected misses in the G-buffer: the first draw of each stretch after a clear (~10-20 per frame), a change of MRT set/`mrt_mask` between pipelines (**unknown, it is the main risk to the hit rate**: today `RtMemo` has a single slot and misses with another `mrt_mask`), the depth of the draws that also sample it (a real barrier per draw, the same 6-8% as DEPTH-RO), `ClearMeta`s.

**Cost** [E, per G-buffer draw, 7 targets + depth]:

| | µs |
|---|---:|
| full `BeginRendering`, instrumented [M] | 0.59-0.70 |
| minus ~42 `rdtsc` reads (~8-14 ns each; the `samples` lap = clock only shows 0.07-0.12 µs [M]) | -0.15 to -0.40 |
| **full `BeginRendering`, real** | **0.30-0.55** |
| repetition per hit: `BatchLock` 0.009 + 7 x 20-25 ns + depth 0.04 + effects 0.01 (anchored on the depth-only hit: 0.079 µs instrumented, ~0.06 real, with 1 target) | 0.20-0.25 |
| `scheduler.BeginRendering` with a token (avoids the 296 B `memcmp`) | -0.01 |
| **net saving per hit** | **0.10-0.35, central ~0.2** |

Per frame (heavy temple, 2465 G-buffer draws, 95% hits): **0.25-0.8 ms, central ~0.5 ms/frame (~+1.2 FPS at 47 FPS, ~2.5% of the frame)**, plus 0.07-0.12 ms from §4.3's micro-adjustments. The 1.7 ms ceiling of
DEPTH-FASTPATH §8 is the instrumented figure with a free repetition: it cannot be reached. At the edge of the project's acceptance criterion (>= 0.5 ms/frame or >= 2% FPS); that is why §4.5's step 0 is mandatory.

## 6. Risks

1. **A smaller benefit than expected** (above). Mitigation: calibrate before writing the repetition.
2. **A forgotten effect** in the repetition: VERIFY covers it (the widened snapshot), but an effect outside the snapshot would not be seen: `download_images` (only with `readback_linear_images`, excluded when recording), `hudless_*` (excluded and checked), `bound_images`/`cb_descs` (in the snapshot).
3. **A single-slot memo with an alternating `mrt_mask`**: if a stretch's draws alternate 2-3 masks, both `RtMemo` and `gb_memo` always miss. The `mask` counter in step 0; if it happens, widen to 2-4 slots per `mrt_mask` (`RtMemo` too).
4. **A stage-only Transit**: `GetBarriers` does not update `pl_stage` when it emits no barrier (`image.cpp:429-431`) and `TransitIsNoop` compares it: an image with the right layout/access but another stage would always miss without a real barrier. Count `transit` separately for targets and review when looking at the causes.
5. **Unstable `Image*`s**: no `Image` pointers are kept (the `SlotVector` moves on insert); only ids and `backing` (stable). Do not introduce an `Image*` cache without validating against `ImageSetGeneration`.
6. **Concurrency**: the flags are changed by the CP/fault handler under the `TextureCache` mutex; the check's reads go under `BatchLock`, like the depth path. Do not read flags outside the lock.
7. **Contamination between memos**: `df_memo` and `gb_memo` separate; `RtMemo` is shared (it already was). Do not change `DepthFastRecord` (it invalidates with colour: it is only called with `mrt_mask == 0`).
8. **PGO**: the new functions have no profile (`tools/pgo_train.sh`). The shader cache does not change.
9. **Scope**: the same gate will accept draws of the "other" class (colour without MRT 4, ~200 per window); they will not hit (`begTrans` 1.6-1.9 µs: real barriers) and must not get worse: if the check misses, the extra cost is the check's (~0.03 µs).

## 7. Other per-G-buffer-draw costs, larger than `BeginRendering` (evidence)

All [M] in instrumented µs per G-buffer draw (`run-dftp.txt` / `run-depth-ph.txt`) with the cause [C]:

| Cost | µs | Code evidence | Verdict |
|---|---:|---|---|
| `BindTextures` (VS + PS; ~11 images + samplers, 22-24 descriptor writes per draw) | **0.94-1.16** | `ReplayTexBindMemo` (`:3387-3452`) hits 86%, but per image it still runs `BindResolvedImage` (`:3321-3366`): `FindTexture` -> `UpdateImage` (lock + `TrackImage` + `TouchImage` + `RefreshImage`) + `FindView` + `Transit` + `image_infos.emplace_back`; and per sampler `GetSampler` (`:3786-3829`). It is **the same per-image machinery** as `BeginRendering` per target, with more images (11 against 7) | **A larger candidate of the same kind**: `UpdateIsNoop && TransitIsNoop(ShaderReadOnlyOptimal, ShaderRead, AllCommands, range)` + a view memoised by `(backing, view_info)` in `TexBindMemoBinding`. [E] 0.2-0.4 µs per G-buffer draw (0.5-1.0 ms/frame). Exactness is more delicate: the descriptors carry the layout `Transit` leaves, and sampled images that are targets (`is_target`) use a feedback loop. Deserves its own document |
| `BindBuffers` (11 buffers) | **0.85-0.89** (`bbObt` 0.46-0.58, `bbClamp` 0.16-0.19, `bbDesc` 0.14-0.17, `bbFlat` 0.09-0.11) | `ObtainBuffer` x ~11, a range clamp and a descriptor per buffer | **No** (DEPTH-FASTPATH §3: new addresses in every draw; a memo by (address, size) already measured zero gain) |
| `Pipeline::BindResources` (`pipeDesc` 0.16-0.21, `pipePush` 0.05-0.06) | 0.25-0.29 | `pushDescriptorSetKHR` with 22-24 writes, equal descriptors 0% | Not without changing the recorded commands |
| `ResetBindings` + `FlushPeriodic` (`postReset` 0.165-0.20) | 0.19-0.23 | `:2833-2862`: `binding = {}` for each image in `bound_images` (~8 targets + ~11 sampled), `AccessBuffer` per buffer (~11, memoised by epoch `vk_runtime.cpp:731-751`) and per fixed read | Only the targets' `binding = {}` could be skipped, but a persistent `is_target` would change behaviour between draws (`ResolveOverlap` and copies read it, `texture_cache.cpp:660,2181`): **not** exact |
| `PrepareRenderState` hit | 0.11-0.14 | the loop over 8 images (`:975-988`) + `active_mask` (`:906-908`) | Partly: §4.3's micro-adjustments (~0.03-0.05) |

`BeginRendering` (0.59-0.70 instrumented, 0.30-0.55 estimated real) is at the level of `pipe` and below `bbuf`/`btex`; **`BindTextures` is the only cost larger than `BeginRendering` where the per-image work can be memoised with the same
tools** (`UpdateIsNoop`, `TransitIsNoop`, generation/epoch serials).

## 8. Recommended order

1. §4.5's step 0 (calibration + cause statistics, 1 launch, without changing behaviour).
2. If the real `begin` >= 0.35 µs and hits >= 90%: implement §4 (`GBufferFastPath`) with VERIFY; A/B.
3. With the same pieces (`UpdateIsNoop`, `TransitIsNoop`): evaluate `BindTextures` (§7) with the same method ("count only" mode first).

## 9. Measured results (2026-10-26, binary `out/bb-probe.gbfast.exe`, 6 launches of 10)

Note: §5's estimate was pessimistic. With the laps removed (`SOTC_DRAW_LAPS=0`), the G-buffer's `BeginRendering` costs **0.52 real µs** (not 0.30-0.45): most of the 0.60-0.70 instrumented was real work. Everything was implemented and measured (coordination later asked to stop at step 0 and port to the new branch; the code stays in the tree, builds, and is **active by default**).

**Step 0 (`gbs0`, ABBA, `SOTC_DRAW_PHASES=1 SOTC_DRAW_LAPS=0`, modes `SOTC_GBFAST_MODE=count` and `SOTC_BTFAST_MODE=count`, windows >= 5000 cmds/frame, G-buffer, µs/draw):**

| | bit 29 set (old path) | bit 29 clear (count: check + full) |
|---|---:|---:|
| `begin` | **0.521** | 0.600 (the check costs +0.079) |
| `btex` (BindTextures, ~11 images, 2 stages) | **1.147** | 1.196 |
| `btex` -> `s_btMemo` (hash + memo + `BindResolvedImage` per image) / `s_btImages` | 0.796 / 0.240 | 0.812 / 0.272 |
| total | 3.461 | 3.626 |

The G-buffer hit rate through the check: **97.6%** (`cand 124703 hit 121660`; misses: `mask` 1.2%, `nomemo` 0.4%, `regs` 0.6%, `dtransit` 0.15%, `gen` 0.03%; `ids/gpuepoch/meta/flags/bound/backing/transit/vo` 0). `state-differs 0`: on every hit the full `BeginRendering` gave the memo's `RenderState`. BindTextures: 99.9% of 3.5 M memoised bindings meet the conditions (all the misses are `transit`). Step 0's gate (real begin >= 0.35 µs, hits >= 90%): met; real `btex` 1.15 >= 0.6: met.

**Implemented** (bits: `GBufferFastPath` = 29, `TexBindFastPath` = 31; bit set = old path; the default mask in `src/runtime_memory.c` does not include them -> active). Bit 29 checked free: no use in `gpu/`, `src/`, `launcher/`, `sotc.py` nor scripts (the "debug bits 20-29" comment is historical, from bbport). Bit 31 too.
- `GBufferFast`/`Check`/`Record`/`Apply` (`vk_rasterizer.cpp`, before `BeginRenderingFast`) with its own `gb_memo`; the scheduler's token; counters and a `SOTC GBFAST` line.
- `TexBindFastCheck/Apply` inside `ReplayTexBindMemo`: it only replaces `BindResolvedImage` (UpdateImage + FindView + Transit) with the remembered view and layout when the image is not Dirty, has the same `backing`, `TransitIsNoop(ShaderReadOnly/DepthStencilReadOnly, ShaderRead, AllCommands)` and is not a target/General. `SotcLod::Mark` per T# is done in the loop before, which is not touched: the sequence of marks is identical to the slow one's.
- Diagnostics: `SOTC_DRAW_LAPS=0` (removes `BeginRendering`'s laps), the subphases `btMemo`/`btImages`, `SOTC_GBFAST_MODE=count`, `SOTC_BTFAST_MODE=count`.

**VERIFY** (`gbv1`, temple replay, `SOTC_DEPTHFAST_VERIFY=1`): the G-buffer's `BeginRendering` **13.04 M checks, 0 mismatches**; textures **134.5 M, 0**; depth (already existing) 25.0 M, 0; `PrepareRenderState` 40.3 M, 0; dynamic state 34.1 M, 0.

**A/B warm** (the same binary, `BB_TOGGLE_FILE` every 5 s, ABBA + BAAB grouped, neighbours of >= 5000 cmds/frame, from 70 s; `gba1/gba2` bit 29, `gbb1/gbb2` bit 31):

| Change | `draw busy` ON-OLD | per 1000 cmds | FPS ON-OLD | heavy stretch (>= 7000 cmds) |
|---|---|---|---|---|
| `GBufferFastPath` (29) | **-1.06 ± 0.41 ms/frame** (n=20) | -0.120 ± 0.047 ms | **+2.57 ± 0.83** | -0.72 ± 0.27 ms/frame, +1.42 FPS (n=5) |
| `TexBindFastPath` (31) | -0.70 ± 0.42 ms/frame (n=20) | -0.055 ± 0.068 ms | +1.48 ± 0.94 | -0.46 ± 0.18 ms/frame, +0.67 FPS (n=3) |

The criterion (>= 0.5 ms/frame in the temple's heavy stretch or >= 2% FPS at the Shrine) is met for bit 29 (-0.72 ± 0.27 ms) and is at the edge for 31 (-0.46 ± 0.18, n=3, high noise). The Shrine was not measured. Files touched: `gpu/shim/bbport_toggles.h`, `gpu/shadps4/video_core/texture_cache/texture_cache.h` (`RenderTargetReplayable`), `gpu/shadps4/video_core/renderer_vulkan/vk_rasterizer.h/.cpp`; scripts `out/gb_bench_temple.sh`, `out/gb_ab_temple.sh`, `out/_gb_chain.sh`.
