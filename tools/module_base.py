"""sotc: the address llvm-symbolizer expects for module offset 0 of an ELF file (its first PT_LOAD
page: 0 for the shared GPU library, 0x400000 for the non-PIE bb-probe). SOTC_PROFILE writes
<module>+0x<offset> from dladdr's load base, which is that page."""
import struct


def module_base(path):
    with open(path, 'rb') as f:
        head = f.read(64)
        phoff, = struct.unpack_from('<Q', head, 32)
        phentsize, phnum = struct.unpack_from('<HH', head, 54)
        f.seek(phoff)
        table = f.read(phentsize * phnum)
    loads = [struct.unpack_from('<Q', table, i * phentsize + 16)[0] for i in range(phnum)
             if struct.unpack_from('<I', table, i * phentsize)[0] == 1]
    return min(loads) & ~0xfff if loads else 0
