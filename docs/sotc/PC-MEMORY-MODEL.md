# PC memory model (option C) — a plan in steps

The user's request on 27 Oct 2026, after measuring the drops when arriving in new areas (DMA 83–127 ms,
uploads 70–106 ms, GPU readback waits 47–59 ms per 5 s window; VRAM 6.4–7.1 GB of 8 GB; draw thread
27–36 ms per frame at 30 FPS, Pro mode + Maximum + DLSS).

## The idea

Today the game's memory and the GPU's are separate: what the game writes is copied to VRAM (DMA
synchronisation, uploads), and what the GPU writes and the game reads comes back by copy (GPU
readbacks, with page protection and waiting). In the "PC memory model" the GPU uses the game's memory
**where it is** (RAM imported with `VK_EXT_external_memory_host`), and only what is always read is
mirrored in VRAM.

Reference: the Bloodborne port (deadinside28, 0.5–0.6, `docs/NVIDIA_MEMORY_MODEL.ru.md` in
`ref/deadinside28_bloodborne_pc`). There the model became the default on every card in 0.6 (19 Oct),
but they rewrote the whole GPU core. Ours uses shadPS4's core: the idea is ported, the code is not.
Their lessons that apply here:

- the VRAM copy **diverging** from the game's memory gave exploding vertices and textures with
  garbage; every CPU write that does not go through the port has to be seen (write traps);
- the GPU should only write to VRAM in blocks the CPU has not touched since the allocation;
- importing host memory pins pages in RAM: import in pieces, on demand, not 9 GB.

The prototype `tools/host_import_test.c` (8 Oct) showed on the RTX 2060 SUPER: importing 256 MiB to
5 GiB works, coherent in both directions, the GPU reads at 5.5 GB/s.

## Steps (each measured before the next; everything behind `SOTC_PC_MEMORY`, off by default)

| # | Step | Delivers | Measurement | Risk |
|---|---|---|---|---|
| 1 | Import the game's memory into the GPU | extension enabled; 64 MiB pieces of the `backing` view imported on demand as `VkBuffer`; a coherence test at start-up | log: imported, time, memory type; nothing changes in the game | low |
| 2 | GPU readbacks straight into the game's memory | `BeginAsyncReadback` copies from VRAM to the imported piece, without a staging area or `memcpy` | ms/s of readbacks, FPS in the demo and on the user's save | low |
| 3 | "Honest" end-of-work labels | the label (EOP) the game waits for is written when the GPU finishes, only for the measured cases | FPS, no hang | medium (already tried on 12 Oct as `SOTC_EOP_DEFER`: FPS halved; it has to be selective) |
| 4 | Regions read every frame written in place | visibility culling (the XPR bitmask, ~0x1078c10000) and other "hot readbacks" written by the GPU straight into the imported RAM: no protection, no read-back | readback waits → ~0; FPS on the bridge and at the end of the demo | medium/high |
| 5 | Data the CPU writes read in place | dynamic constants and vertices read from the imported RAM instead of synchronised by DMA; a VRAM mirror only of what is always read | DMA cost (today ~47 ms/s), drops at area changes | high |

**A constraint found in step 1 (27 Oct):** readbacks apply the data through `ApplyDownloads`, which
contains the guard of the game's heaps (`BpeHeapGuard`, #146, the ending's 0x49500 crash): old bytes
from the GPU must not land in blocks the game has already freed. A GPU copy straight into the game's
memory skips that guard. So step 2 writes directly **only outside the guarded heaps**; inside them
the current path stays. The same applies to steps 4 and 5.

Cut-off criteria: the same image in the demo's captures, no green blocks (the 6th colossus's
temple), the ending without a crash (POOL_FIX, the heap guards and the pool rule untouched).

## Status

- 27 Oct: plan written.
- 27 Oct: **step 1 done** (`SOTC_PC_MEMORY=1`, off by default). `VK_EXT_external_memory_host`
  requested only with the switch; `renderer_vulkan/sotc_guest_memory.*` imports the `backing` view
  (`runtime_memory_backing_view`) in 64 MiB pieces on demand. The view only exists after the game
  maps memory, so it is looked for at every submission (`Rasterizer::OnSubmit`) until found. On the
  RTX 2060 SUPER: `10176 MiB of game memory, 159 chunks ... chunk 0 in 24.2 ms` (memory type 3),
  demo at 60 FPS, no errors. The device's extension list grew from 32 to 48 places (33 requested).
- 27 Oct: **step 2 dropped** (the user's request: the safest option, protecting the ending). The
  heap guard decides at apply time which blocks the game has just freed (world heaps grow in 1 MiB
  pieces, the range rebuilt every 250 ms–2 s); a GPU copy straight into memory falls outside that
  control. The gain is small too (~3–5% of the draw thread; the wait stays).
- 27 Oct, measurement (`SOTC_RB_STATS=1`, the user's save, gameplay standing still, 60 FPS, Pro +
  DLSS): readbacks per game instruction over ~3 min: `eboot+0x1a6d60` (visibility culling) ~50
  thousand in `0x109f83…–0x109f8a…`; `eboot+0x101a98` ~22 thousand spread over `0x13…`;
  `eboot+0x937fd` ~2.6 thousand at `0x1245620000`. The culling buffer **is not fixed** (on 14 Oct it
  was at `0x1078c1…`): it is allocated in the **pool of 64 KiB pages** (`0x10…`–`0x123C…`, the one
  of `POOL_FIX`), not in a heap (the guarded heap starts at `0x123c000020`, 150 MB). The pool frees
  and reuses pages: a direct write is only safe with an honest end-of-work signal.
- **New order:** (a) an honest EOP only for the culling's work (risk: slowness, no data moves);
  (b) then, a direct write only to the pages the culling uses, checking every frame that they are
  still its own. Everything off by default; the ending tested by the user before it becomes the
  default.
