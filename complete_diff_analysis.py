#!/usr/bin/env python3
"""
ANALISI COMPLETA - Trova TUTTE le differenze tra HDD con saves e senza.
"""

import os

HDD_WITH = r"D:\xemu\bk\xbox_hdd_working_20251227.qcow2"  # Con saves
HDD_WITHOUT = r"D:\xemu\xbox_hdd.qcow2"  # Senza saves

print("=" * 70)
print("ANALISI COMPLETA DIFFERENZE")
print("=" * 70)

print(f"\n📂 Con saves: {os.path.basename(HDD_WITH)}")
print(f"📂 Senza saves: {os.path.basename(HDD_WITHOUT)}")

print("\n⏳ Caricamento file...")
with open(HDD_WITH, 'rb') as f:
    data_with = f.read()
with open(HDD_WITHOUT, 'rb') as f:
    data_without = f.read()

print(f"   Size con: {len(data_with):,} bytes")
print(f"   Size senza: {len(data_without):,} bytes")

# Trova TUTTE le differenze
print("\n⏳ Analisi differenze...")
all_diffs = []
for i in range(min(len(data_with), len(data_without))):
    if data_with[i] != data_without[i]:
        all_diffs.append(i)

print(f"\n📊 TOTALE DIFFERENZE: {len(all_diffs):,} bytes")

# Raggruppa per area (blocchi da 64KB = 0x10000)
areas = {}
for pos in all_diffs:
    area = (pos // 0x10000) * 0x10000
    if area not in areas:
        areas[area] = []
    areas[area].append(pos)

print(f"📊 AREE DIVERSE: {len(areas)}")

# Mostra tutte le aree
print("\n" + "=" * 70)
print("DETTAGLIO PER AREA (64KB blocks)")
print("=" * 70)

for area in sorted(areas.keys()):
    diffs = areas[area]
    first_diff = min(diffs)
    last_diff = max(diffs)
    
    # Mostra contesto del primo byte diverso
    ctx_start = max(0, first_diff - 8)
    context = data_with[ctx_start:ctx_start + 32]
    ascii_ctx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in context)
    
    print(f"\n0x{area:08x}: {len(diffs):>5} bytes diversi")
    print(f"   Range: 0x{first_diff:08x} - 0x{last_diff:08x}")
    print(f"   Contesto: \"{ascii_ctx}\"")
    
    # Primi 3 byte diversi
    for pos in diffs[:3]:
        a = data_with[pos]
        b = data_without[pos]
        print(f"   0x{pos:08x}: 0x{a:02x} (con) -> 0x{b:02x} (senza)")

# Confronta con le aree di restore_filesystem_areas.py
print("\n" + "=" * 70)
print("CONFRONTO CON AREE DI restore_filesystem_areas.py")
print("=" * 70)

restore_areas = [
    (0x00440000, 0x00030000, "Save_Area_Complete"),
    (0x00080000, 0x00010000, "Partition_Table"),
    (0x00160000, 0x00010000, "FATX_Partition_1"),
    (0x001f0000, 0x00010000, "FATX_Partition_2"),
    (0x00280000, 0x00010000, "FATX_Partition_3"),
    (0x00300000, 0x00020000, "Directory_Metadata"),
    (0x00320000, 0x00020000, "File_Allocation_Tables"),
    (0x00070000, 0x00010000, "Pre_Partition_Area"),
    (0x00340000, 0x00020000, "Extended_Metadata"),
]

covered = 0
not_covered = 0

for pos in all_diffs:
    is_covered = False
    for start, size, name in restore_areas:
        if start <= pos < start + size:
            is_covered = True
            break
    if is_covered:
        covered += 1
    else:
        not_covered += 1

print(f"\n   Bytes coperti dallo script: {covered:,}")
print(f"   Bytes NON coperti: {not_covered:,}")

if not_covered > 0:
    print("\n⚠️  AREE NON COPERTE:")
    uncovered_areas = set()
    for pos in all_diffs:
        is_covered = False
        for start, size, name in restore_areas:
            if start <= pos < start + size:
                is_covered = True
                break
        if not is_covered:
            area = (pos // 0x10000) * 0x10000
            uncovered_areas.add(area)
    
    for area in sorted(uncovered_areas):
        count = sum(1 for p in all_diffs if (p // 0x10000) * 0x10000 == area)
        print(f"   0x{area:08x}: {count} bytes")
