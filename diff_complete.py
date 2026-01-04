#!/usr/bin/env python3
"""
DIFF COMPLETA - Trova TUTTE le differenze tra source e target
"""

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd4.qcow2"
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"

print("=" * 70)
print("DIFF COMPLETA HDD")
print("=" * 70)

print("\nCaricamento...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
with open(HDD_TARGET, 'rb') as f:
    target = f.read()

print(f"Source: {len(source):,} bytes")
print(f"Target: {len(target):,} bytes")

# Trova TUTTE le differenze
print("\nAnalisi differenze (potrebbe richiedere tempo)...")
all_diffs = []
for i in range(min(len(source), len(target))):
    if source[i] != target[i]:
        all_diffs.append(i)

print(f"\nTOTALE BYTES DIVERSI: {len(all_diffs):,}")

if len(all_diffs) == 0:
    print("\nI file sono IDENTICI!")
else:
    # Raggruppa per aree da 64KB
    areas = {}
    for pos in all_diffs:
        area = (pos // 0x10000) * 0x10000
        if area not in areas:
            areas[area] = []
        areas[area].append(pos)
    
    print(f"AREE DIVERSE: {len(areas)}")
    
    print("\n" + "=" * 70)
    print("DETTAGLIO AREE")
    print("=" * 70)
    
    for area in sorted(areas.keys()):
        diffs = areas[area]
        first = min(diffs)
        last = max(diffs)
        
        # Contesto
        ctx = source[first:first+32]
        ascii_ctx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ctx)
        
        print(f"\n0x{area:08x}: {len(diffs):,} bytes diversi")
        print(f"  Range: 0x{first:08x} - 0x{last:08x}")
        print(f"  Contesto source: \"{ascii_ctx[:40]}\"")
        
        # Prime 3 differenze
        for pos in diffs[:3]:
            s = source[pos]
            t = target[pos]
            print(f"  0x{pos:08x}: src=0x{s:02x} tgt=0x{t:02x}")
