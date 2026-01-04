#!/usr/bin/env python3
"""
DIFF TOEJAM - Confronta HDD sorgente (ToeJam funziona) vs target (dopo restore)
Per capire cosa manca nel nostro restore.
"""

import struct

# HDD sorgente con ToeJam funzionante
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"
# HDD target dopo il nostro restore
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"

# Costanti
DATA_START = 0x00443000
CLUSTER_SIZE = 16384

def cluster_to_offset(c):
    return DATA_START + ((c - 2) * CLUSTER_SIZE)

print("=" * 70)
print("DIFF TOEJAM - Cosa manca nel restore?")
print("=" * 70)

print(f"\nSorgente (funziona): {HDD_SOURCE.split(chr(92))[-1]}")
print(f"Target (non funziona): {HDD_TARGET.split(chr(92))[-1]}")

print("\nCaricamento...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
with open(HDD_TARGET, 'rb') as f:
    target = f.read()

print(f"  Source: {len(source):,} bytes")
print(f"  Target: {len(target):,} bytes")

# Focus sull'area ToeJam (cluster 39-146 + aree FAT/directory)
# Cluster 39-146 = offset 0x4D7000 - 0x6B7000
TOEJAM_DATA_START = cluster_to_offset(39)  # 0x4D7000
TOEJAM_DATA_END = cluster_to_offset(147)   # 0x6B7000

# Area FAT per cluster 39-146
FAT_TABLE = 0x00161000
FAT32_TABLE = 0x00311000
TOEJAM_FAT16_START = FAT_TABLE + 39 * 2
TOEJAM_FAT16_END = FAT_TABLE + 147 * 2
TOEJAM_FAT32_START = FAT32_TABLE + 39 * 4
TOEJAM_FAT32_END = FAT32_TABLE + 147 * 4

# Area directory UDATA (cluster 3-4)
UDATA_START = cluster_to_offset(3)  # 0x447000
UDATA_END = cluster_to_offset(5)    # 0x44F000

areas_to_check = [
    ("UDATA Directory (cluster 3-4)", UDATA_START, UDATA_END),
    ("ToeJam FAT16 entries", TOEJAM_FAT16_START, TOEJAM_FAT16_END),
    ("ToeJam FAT32 entries", TOEJAM_FAT32_START, TOEJAM_FAT32_END),
    ("ToeJam Data (cluster 39-146)", TOEJAM_DATA_START, TOEJAM_DATA_END),
]

print("\n" + "=" * 70)
print("ANALISI AREE TOEJAM")
print("=" * 70)

total_diff = 0
for name, start, end in areas_to_check:
    src_area = source[start:end]
    tgt_area = target[start:end]
    
    diff_count = sum(1 for a, b in zip(src_area, tgt_area) if a != b)
    pct = (diff_count / len(src_area)) * 100 if len(src_area) > 0 else 0
    
    status = "IDENTICHE" if diff_count == 0 else f"{diff_count:,} bytes ({pct:.1f}%)"
    
    print(f"\n{name}:")
    print(f"  Range: 0x{start:08x} - 0x{end:08x} ({end-start:,} bytes)")
    print(f"  Differenze: {status}")
    
    if diff_count > 0 and diff_count < 1000:
        # Mostra prime differenze
        first_diffs = []
        for i in range(min(len(src_area), len(tgt_area))):
            if src_area[i] != tgt_area[i]:
                first_diffs.append(start + i)
                if len(first_diffs) >= 5:
                    break
        
        print(f"  Prime differenze:")
        for pos in first_diffs:
            s = source[pos]
            t = target[pos]
            print(f"    0x{pos:08x}: src=0x{s:02x} tgt=0x{t:02x}")
    
    total_diff += diff_count

# Check specifico: entry ToeJam in UDATA
print("\n" + "=" * 70)
print("CHECK ENTRY TOEJAM IN UDATA")
print("=" * 70)

# Entry ToeJam dovrebbe essere a 0x447040 (cluster 3) o 0x44b040 (cluster 4)
for entry_offset in [0x447040, 0x44b040]:
    print(f"\nEntry @ 0x{entry_offset:08x}:")
    
    src_entry = source[entry_offset:entry_offset + 64]
    tgt_entry = target[entry_offset:entry_offset + 64]
    
    # Parse
    src_fn_len = src_entry[0]
    tgt_fn_len = tgt_entry[0]
    
    if 1 <= src_fn_len <= 42:
        src_fn = src_entry[2:2+src_fn_len].decode('ascii', errors='replace')
        src_fc = struct.unpack('<I', src_entry[44:48])[0]
        print(f"  Source: '{src_fn}' -> cluster {src_fc}")
    else:
        print(f"  Source: invalid (fn_len=0x{src_fn_len:02x})")
    
    if 1 <= tgt_fn_len <= 42:
        tgt_fn = tgt_entry[2:2+tgt_fn_len].decode('ascii', errors='replace')
        tgt_fc = struct.unpack('<I', tgt_entry[44:48])[0]
        print(f"  Target: '{tgt_fn}' -> cluster {tgt_fc}")
    else:
        print(f"  Target: invalid (fn_len=0x{tgt_fn_len:02x})")
    
    if src_entry == tgt_entry:
        print(f"  Status: IDENTICHE")
    else:
        diff = sum(1 for a, b in zip(src_entry, tgt_entry) if a != b)
        print(f"  Status: DIVERSE ({diff} bytes)")

# Check FAT chain
print("\n" + "=" * 70)
print("CHECK FAT CHAIN TOEJAM (cluster 39-50)")
print("=" * 70)

for c in range(39, 51):
    fat16_off = FAT_TABLE + c * 2
    src_fat = struct.unpack('<H', source[fat16_off:fat16_off+2])[0]
    tgt_fat = struct.unpack('<H', target[fat16_off:fat16_off+2])[0]
    
    src_next = "END" if src_fat >= 0xFFF8 else (f"-> {src_fat}" if src_fat > 0 else "FREE")
    tgt_next = "END" if tgt_fat >= 0xFFF8 else (f"-> {tgt_fat}" if tgt_fat > 0 else "FREE")
    
    status = "OK" if src_fat == tgt_fat else "DIFF!"
    print(f"  Cluster {c}: src={src_next}, tgt={tgt_next} [{status}]")

print("\n" + "=" * 70)
print("RIEPILOGO")
print("=" * 70)
print(f"Totale differenze aree ToeJam: {total_diff:,} bytes")
