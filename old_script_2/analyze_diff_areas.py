#!/usr/bin/env python3
"""
Confronto dettagliato auxilary.bin e cache tra H1 e H2
"""

import struct

HDD_H1 = r"D:\xemu\bk\xbox_hddt1.qcow2"
HDD_H2 = r"D:\xemu\bk\xbox_hddt2.qcow2"

DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 1) * CLUSTER_SIZE)

print("Caricamento HDD...")
with open(HDD_H1, 'rb') as f:
    h1 = f.read()
with open(HDD_H2, 'rb') as f:
    h2 = f.read()

print(f"H1: {len(h1):,} bytes")
print(f"H2: {len(h2):,} bytes")

# ============================================
# CONFRONTO auxilary.bin (cluster 12-267)
# ============================================
print("\n" + "="*60)
print("CONFRONTO auxilary.bin (cluster 12-267)")
print("="*60)

diff_count = 0
diff_clusters = []
for c in range(12, 268):
    off = cluster_to_offset(c)
    if off + CLUSTER_SIZE > len(h1) or off + CLUSTER_SIZE > len(h2):
        print(f"Cluster {c}: fuori range")
        continue
    
    chunk1 = h1[off:off + CLUSTER_SIZE]
    chunk2 = h2[off:off + CLUSTER_SIZE]
    
    if chunk1 != chunk2:
        diff = sum(1 for a, b in zip(chunk1, chunk2) if a != b)
        diff_count += diff
        diff_clusters.append((c, diff))

print(f"Cluster con differenze: {len(diff_clusters)}")
print(f"Byte diversi totali in auxilary.bin: {diff_count:,}")
for c, diff in diff_clusters[:20]:
    print(f"  Cluster {c}: {diff:,} byte diversi")

# ============================================
# CERCA FILE CACHE
# ============================================
print("\n" + "="*60)
print("CERCA cache000.map e cache001.map")
print("="*60)

for cache_name in [b'cache000.map', b'cache001.map']:
    print(f"\n--- {cache_name.decode()} ---")
    pos = h1.find(cache_name)
    if pos != -1:
        entry_start = pos - 2
        fn_len = h1[entry_start]
        first_cluster = struct.unpack('<I', h1[entry_start + 44:entry_start + 48])[0]
        file_size = struct.unpack('<I', h1[entry_start + 48:entry_start + 52])[0]
        print(f"H1: first_cluster={first_cluster}, size={file_size:,} bytes ({file_size//1024//1024} MB)")
        
        # Quanti cluster occupa?
        num_clusters = (file_size + CLUSTER_SIZE - 1) // CLUSTER_SIZE
        print(f"    Cluster range: {first_cluster} - {first_cluster + num_clusters - 1} ({num_clusters} cluster)")
    else:
        print(f"H1: NON TROVATO")

# ============================================
# ANALISI DISTRIBUZIONE DIFFERENZE
# ============================================
print("\n" + "="*60)
print("DISTRIBUZIONE DIFFERENZE PER AREA")
print("="*60)

# Dividiamo le differenze per area
areas = {
    'FAT (prima di DATA_START)': (0, DATA_START),
    'Cluster 1-11 (root/UDATA)': (DATA_START, cluster_to_offset(12)),
    'Cluster 12-267 (auxilary.bin)': (cluster_to_offset(12), cluster_to_offset(268)),
    'Cluster 268-1000': (cluster_to_offset(268), cluster_to_offset(1001)),
    'Cluster 1000-10000': (cluster_to_offset(1000), cluster_to_offset(10001)),
    'Cluster 10000+ (cache?)': (cluster_to_offset(10000), min(len(h1), len(h2))),
}

for area_name, (start, end) in areas.items():
    if start >= min(len(h1), len(h2)):
        continue
    
    actual_end = min(end, len(h1), len(h2))
    diff = sum(1 for i in range(start, actual_end) if h1[i] != h2[i])
    
    if diff > 0:
        print(f"{area_name}: {diff:,} byte diversi")

# ============================================
# RIEPILOGO
# ============================================
print("\n" + "="*60)
print("RIEPILOGO")
print("="*60)

total_diff = sum(1 for i in range(min(len(h1), len(h2))) if h1[i] != h2[i])
print(f"Differenze totali H1 vs H2: {total_diff:,} bytes")
print(f"Di cui in auxilary.bin: {diff_count:,} bytes ({100*diff_count/total_diff:.2f}%)")
