# Path B: bbport's GPU optimizations in shadPS4 SotC

The original request: bring bbport's GPU optimizations, such as the two-thread drawing pipeline and
FSR, to our shadPS4.

## What the tests showed (7–8 Oct 2026)

The native port first ran with bbport's video core, which brings ~40 optimizations that can be turned
off through `BB_TOGGLE_FILE`, listed in bbport's `gpu/shim/bbport_toggles.h`.

| bbport optimization | Effect on Shadow of the Colossus |
|---|---|
| `PendingFenceWaits` (bit 39) | intermittent black screen at boot (50–75% of runs) |
| `DrawPipeline`, `DrawPreparation` and the like (preparation ahead and deferred) | old or garbage GPU state during the streaming when loading the save: invalid shader programs, `Unpack10_11_11`, device lost |
| relaxed GPU readbacks (bbport's default) | the game hangs; SotC needs precise readbacks (`BB_READBACKS=2`) |

With the fork's video core in place of bbport's (keeping bbport's loader and runtime), the game was
correct: menus, save and open world, 10 min without a crash. Those optimizations assume the game does
not read, on the CPU, what the GPU has just written. That holds for Bloodborne, but not for SotC.

## Current measurement (native port, i9-13900K + RTX 2060 SUPER, 1080p)

- Default: locked at 30 FPS, as on the PS4; 22–25 during loads and in the temple.
- `fps60` mode (120 Hz vblank): 38 FPS in the open world, ~25 in the temple.
- Bottleneck: the `GpuCommandProcessor` thread is 72% busy. The time goes to the Vulkan driver and to
  fence waits of the precise readbacks. The game's job workers stay at 36–43%.
- The fork in shadPS4 ran at 17–18 FPS (consolidated document), so the native port already has ~1.7x
  the performance.

## Conclusion

Copying bbport's two-thread pipeline to the fork as it is would break SotC for the reasons in the
table. FSR brings no gain because the game already renders at native 1080p.

The native port and the fork now use **the same video core** (the files of `gpu/shadps4/video_core`
are the fork's). So any optimization made here applies to both. The viable path is to optimize that
common core, one piece at a time, with an A/B test: `tools/sotc_hangtest.py` and the route that loads
the save in `tools/sotc_play.py`. Candidates, in order of risk:

1. bbport's pure caches, without deferral: `RegionCache`, `FetchShaderCache`, `ImageDescCache`,
   `FindImageCache`, `TextureBindingMemo`, `RenderStateMemo`. They attack the command thread's cost.
2. `ThreadedRecording` (Vulkan recording on another thread), keeping strict order with respect to the
   precise readbacks.
3. Cheaper precise readbacks: copy only the pages read and wait for the right fence instead of waiting
   for the GPU to go idle.

Each item is a manual merge between cores that diverged by ~17 thousand lines. The expected gain is
in the 60 FPS mode: the default mode already reaches the PS4's 30.

## The game's memory in place: prototype (8 Oct 2026)

The original bbport (deadinside28, version 0.3) has a "PC memory model" (`BB_GUEST_IN_PLACE`): the GPU
uses the game's memory where it is and the EOP labels are written when the GPU has really finished.
That removes the copies to VRAM, the page protection and the readbacks. Measured on Bloodborne:
95 → 115–124 FPS in heavy scenes. There it uses dma-buf, which exists only on Linux and only works on
AMD.

On Windows the path is `VK_EXT_external_memory_host`. The test `tools/host_import_test.c` maps a page
file section the same way `src/runtime_memory.c` does (a "backing" view and the game's view over a
placeholder) and imports the "backing" view. Result on the RTX 2060 SUPER:

| Size | Imports | GPU writes → CPU sees | CPU writes → GPU reads | GPU reads the imported memory |
|---|---|---|---|---|
| 256 MiB | yes (50 ms) | yes | yes | 5.4 GB/s |
| 2 GiB | yes (460 ms) | yes | yes | 5.7 GB/s |
| 5 GiB | yes (1.5 s) | yes | yes | 5.5 GB/s |

The memory type is host-coherent, uncached on the CPU, and the minimum alignment is 4 KiB. The
VRAM→VRAM copy ran at 65–184 GB/s. So textures and geometry stay in VRAM; the gain is in the data the
GPU writes and the CPU reads (what needs precise readbacks today) and in the labels.

**Proposed integration, in measurable steps:**

1. Import the whole "backing" view at start-up, as a `VkDeviceMemory`.
2. Make the readbacks copy from VRAM straight into the game's memory, without staging and without a
   memcpy. The risk is low and the gain small, but it validates the piece.
3. Move to the imported memory the regions that become "hot readbacks" (the ones the game rereads
   every frame). The GPU then writes to them directly, without page protection or readback.
4. "Honest" EOP labels (written after completion on the GPU) for those regions. With that the game's
   own synchronisation is enough.
