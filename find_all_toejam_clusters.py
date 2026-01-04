#!/usr/bin/env python3
"""
Trova TUTTI i cluster usati da ToeJam, inclusi quelli alti
"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_TABLE = 0x00161000

def read_fat16(data, cluster):
    offset = FAT_TABLE + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_chain(data, first, max_len=500):
    if first == 0 or first >= 0xFFF0: return []
    chain = [first]
    current = first
    for _ in range(max_len):
        n = read_fat16(data, current)
        if n >= 0xFFF8 or n == 0 or n in chain: break
        chain.append(n)
        current = n
    return chain

def cluster_to_offset(c):
    return DATA_START + (c - 2) * CLUSTER_SIZE

with open(HDD, 'rb') as f:
    data = f.read()

print("=== TROVA TUTTI I CLUSTER DI TOEJAM ===\n")

# Le aree diverse trovate:
# 0x00160000 - FAT
# 0x00170000 - TEMP_SAVE  
# 0x0f730000 - cluster ~15553
# 0x118f0000 - cluster 17710 (SaveMeta)
# 0x14520000 - cluster ~21300

# Calcoliamo quali cluster corrispondono
areas = [
    (0x0f73f000, "Area 0x0f730000"),
    (0x118f3000, "Area 0x118f0000 (SaveMeta)"),
    (0x14523000, "Area 0x14520000"),
]

print("Cluster corrispondenti alle aree diverse:")
for offset, name in areas:
    if offset >= DATA_START:
        cluster = (offset - DATA_START) // CLUSTER_SIZE + 2
        print(f"  {name}: cluster {cluster}")

# Verifica chi usa questi cluster
print("\n=== FAT CHAIN DI QUESTI CLUSTER ===")

interesting_clusters = [15553, 17710, 21315]  # Calcolati dalle aree

for c in interesting_clusters:
    chain = get_chain(data, c)
    if len(chain) > 0:
        fat_val = read_fat16(data, c)
        next_str = f"-> {fat_val}" if fat_val < 0xFFF8 else "END"
        print(f"Cluster {c}: {next_str} (chain len: {len(chain)})")
        if len(chain) > 1:
            print(f"  Chain: {chain[:10]}...")

# Cerca reverse: chi punta a questi cluster?
print("\n=== CHI PUNTA A QUESTI CLUSTER? (reverse FAT) ===")

for target in interesting_clusters:
    for c in range(2, 25000):
        next_c = read_fat16(data, c)
        if next_c == target:
            print(f"  Cluster {c} -> {target}")

# Cerca directory entries che referenziano questi cluster
print("\n=== DIRECTORY ENTRIES CHE REFERENZIANO QUESTI CLUSTER ===")

# Scan un range ampio per entries
for target_cluster in interesting_clusters:
    target_bytes = struct.pack('<I', target_cluster)
    
    pos = 0
    while True:
        pos = data.find(target_bytes, pos)
        if pos == -1:
            break
        
        # Check se questo potrebbe essere first_cluster in una dir entry
        # first_cluster è a offset +44 dalla entry start
        entry_start = pos - 44
        if entry_start >= 0:
            fn_len = data[entry_start]
            if 1 <= fn_len <= 42:
                fn = data[entry_start+2:entry_start+2+fn_len].decode('ascii', errors='replace')
                # Verifica che il nome sia ragionevole (solo caratteri printable)
                if all(c.isprintable() or c == '\x00' for c in fn):
                    attrs = data[entry_start + 1]
                    is_dir = "DIR" if attrs & 0x10 else "FILE"
                    cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2 if entry_start >= DATA_START else "pre-data"
                    print(f"  '{fn}' -> {target_cluster} @ 0x{entry_start:08x} (cluster {cluster})")
        
        pos += 1

# Analizziamo il contenuto di cluster 17710 (SaveMeta area)
print("\n=== DETTAGLIO CLUSTER 17710 ===")
c_off = cluster_to_offset(17710)
print(f"Offset: 0x{c_off:08x}")

# Dump entries
for i in range(10):
    e_off = c_off + i * 64
    e = data[e_off:e_off + 64]
    fn_len = e[0]
    
    if fn_len == 0xFF or fn_len == 0x00:
        continue
    if fn_len == 0xE5:
        print(f"  Entry {i}: DELETED")
        continue
    if fn_len > 42:
        continue
    
    fn = e[2:2+fn_len].decode('ascii', errors='replace')
    fc = struct.unpack('<I', e[44:48])[0]
    attrs = e[1]
    is_dir = "DIR" if attrs & 0x10 else "FILE"
    
    print(f"  Entry {i}: {is_dir} '{fn}' -> cluster {fc}")
    
    # Segui la chain
    if fc > 0 and fc < 50000:
        chain = get_chain(data, fc)
        print(f"    Chain: {chain[:5]}... ({len(chain)} clusters)")
