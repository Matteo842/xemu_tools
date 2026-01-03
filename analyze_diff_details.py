#!/usr/bin/env python3
"""Analisi dettagliata differenze tra SOURCE e TARGET"""

SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # Entrambi
TARGET = r"D:\xemu\xbox_hdd.qcow2"        # Solo Merc

print("ANALISI DETTAGLIATA DIFFERENZE")
print("=" * 70)

with open(SOURCE, 'rb') as s, open(TARGET, 'rb') as t:
    # Directory_Metadata - 29 bytes diversi
    print("\n📋 Directory_Metadata (0x300000):")
    s.seek(0x300000)
    t.seek(0x300000)
    src = s.read(0x20000)
    tgt = t.read(0x20000)
    
    for i, (a, b) in enumerate(zip(src, tgt)):
        if a != b:
            abs_pos = 0x300000 + i
            ctx = src[i:i+16]
            ascii_ctx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ctx)
            print(f"  0x{abs_pos:08x}: 0x{a:02x} -> 0x{b:02x}  '{ascii_ctx}'")

    # Save_Area_Complete - 4 bytes diversi
    print("\n📋 Save_Area_Complete (0x440000):")
    s.seek(0x440000)
    t.seek(0x440000)
    src = s.read(0x30000)
    tgt = t.read(0x30000)
    
    for i, (a, b) in enumerate(zip(src, tgt)):
        if a != b:
            abs_pos = 0x440000 + i
            ctx = src[i:i+16]
            ascii_ctx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ctx)
            print(f"  0x{abs_pos:08x}: 0x{a:02x} -> 0x{b:02x}  '{ascii_ctx}'")
