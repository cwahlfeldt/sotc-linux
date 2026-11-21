#!/usr/bin/env python3
"""sotc: symbolize a SOTC_PROFILE report from a log: profile_sym.py log [module]
module: the library or program whose offsets are named (default out/gpu/libbbgpu.so: the report's
libbbgpu.so+0x... lines; out/bb-probe for the loader's)."""
import re, subprocess, sys
from module_base import module_base
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
start = text.find('SOTC profile of')
lines = text[start:].splitlines()[:150]
exe = sys.argv[2] if len(sys.argv) > 2 else 'out/gpu/libbbgpu.so'
pattern = re.escape(exe.rsplit('/', 1)[-1]) + r'\+(0x[0-9a-f]+)'
base = module_base(exe)
offs = sorted({m for l in lines for m in re.findall(pattern, l)})
out = subprocess.run(['llvm-symbolizer', f'--obj={exe}', '--no-inlines', '--functions=short',
                      *[hex(base + int(o, 16)) for o in offs]], capture_output=True, text=True).stdout.split('\n\n')
sym = {o: r.strip().split('\n')[0][:100] for o, r in zip(offs, out)}
for l in lines:
    m = re.search(pattern, l)
    print(l.rstrip() + ('   ' + sym.get(m.group(1), '') if m else ''))
