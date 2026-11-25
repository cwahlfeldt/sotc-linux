# SotC's water in the port: what was wrong and how it was found

A record of the water fixes (October 2026), so the investigation is not repeated.

## Symptoms

- The water was flat, like a mirror, without waves. It only rippled very close to Wander.
- The lake near the waterfall reflected only nearby objects. Further away, the surface was dark and
  flat.
- The open world's lakes and rivers, below the waterfalls, were completely still.

## Two kinds of water

1. **Simulated water** (the lake near the waterfall, shader `fs 8356` in the lake capture). The CPU
   updates a 512×512 simulation texture around Wander, and the vertex shader takes the normal from
   it. Outside that square, the waves come from normal maps.
2. **Flow-map water** (the open world's lakes and rivers, `fs 0xc65f86f1`). It has no simulation:
   the waves are BC5 normal maps shifted by a flow map and a clock (`srt[69]`, time × speed
   `srt[184]`, with two `fract` phases).

## Fix 1: DMA on by default (`294b68e`)

The screen-space reflection shader (compute) reads, for each ray, a 224-byte *probe* record with an
index computed at run time. The pass that "flattens" the shader's memory reads cannot resolve that
index. Without DMA the read fell on `srt_flatbuf.data[0]`, so every pixel used the same record.

Pink-shadPS4 turns on `direct_memory_access_enabled` in `CUSA08809.json`. With DMA those reads become
direct accesses to the game's memory (a BDA page table). It is now the port's default
(`BB_DIRECT_MEMORY_ACCESS`, in `gpu/shim/core/emulator_settings.h`). Only about 4 shaders start
using DMA, and the measured cost is negligible.

## Fix 2: `S_WQM_B64` (`debb0c4`)

At the start of the open world's water shader:

```
s_mov_b32  vcc_hi, 0x384        ; the game uses vcc_hi as an ordinary register
...
s_wqm_b64  vcc, exec            ; VCC = mask of active threads ("whole quad" mode)
...
v_cmp_nle_f32 s[12:13], v9, s87 ; s87 = 0.05
s_and_saveexec_b64 s[88:89], vcc
```

The recompiler treated `S_WQM_B64` as "do nothing", which is only safe for `s_wqm_b64 exec, exec`.
Here the destination is VCC: the lower half of VCC was undefined and the upper half held 0x384
(900). On an NVIDIA GPU (subgroups of 32) only the undefined half counts, so the branch that applies
the flow map never ran. The shader always wrote the same normal, straight up (`0x16ffb801` in the
G-buffer).

Fix in `shader_recompiler/frontend/translate/scalar_alu.cpp`: when the destination is not EXEC,
`S_WQM_B64` writes the mask expanded to whole quads (a 2×2 quad with any bit set gets all four) and
sets SCC. Pink has the same problem.

- The first version only copied the mask. The water came out right, but the distant tree crowns got
  "coloured garbage". The foliage uses `s_wqm_b64` in the alpha test to keep the quad's neighbours
  alive, which the GPU needs to compute the texture's level of detail. Without the expansion it read
  mips with garbage.
- The expansion is done per thread (each pixel gathers the 4 bits of its quad with `QuadBroadcast`
  and then `Ballot`), not with shifts on the 64-bit mask. The `InverseBallot` elimination pass
  treats masks as a boolean per thread and aborts on a constant such as `0x1111111111111111`.
- Only 9 of the game's pixel shaders use this form (`s_wqm_b64 vcc, exec` or `vcc, vcc`).
  `SOTC_WQM_COPY=0` returns to the old behaviour, for comparison.

## Method (scripts in `tools/rdoc`; run with `qrenderdoc.exe --python <script>` and the `RD_*` variables)

1. **Capture in RenderDoc:** `SOTC_WRAP` (JSON with `renderdoccmd capture`) +
   `SOTC_RDOC_SUBMITS=8` + `SOTC_RECORD_THREAD=0`, and F12 in the game. Opening the capture needs the
   game closed, because there is no VRAM left. The first frame has indirect arguments with garbage;
   use the following frames.
2. **Find the draw:** list the draws by shader and textures (`rd_findps.py`). The G-buffer's pixel
   history (`rd_hist.py`) shows which draw wrote each pixel.
3. **Check the inputs:** views and mips (`rd_views.py`, `rd_mipsminmax.py`), constants
   (`rd_flatdump.py`), vertex buffers (`rd_vsbufs.py`) and outputs (`rd_raw.py`, which saves the
   G-buffer's bytes to decode in Python).
4. **Instrument the shader:** extract the SPIR-V (`rd_spv.py`), disassemble with `spirv-dis`, replace
   what goes to `frag_color0` with intermediate values (`spv_probe.py`), assemble with `spirv-as`,
   replace it in the capture (`BuildTargetShader` + `ReplaceResource`) and read the pixel
   (`rd_probe.py`). That is how the straight normal and the branch with `InverseBallot` over
   `(Undef, 900)` showed up.
5. **See the GCN code:** `BB_DUMP_SHADERS=1` writes the IR and the binary of each compiled shader to
   `user/shader/dumps`. `tools/rdoc/gcnscan.py` is a minimal GCN decoder that marks the instructions
   that touch VCC.
