#!/usr/bin/env python3
"""
Analisi DETTAGLIATA delle differenze nella cache
Per capire esattamente cosa serve
"""

import struct

HDD_H1 = r"D:\xemu\bk\xbox_hddh1.qcow2"
HDD_H2 = r"D:\xemu\bk\xbox_hddh2.qcow2"

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

# Analisi per fasce di cluster
print("\n" + "="*70)
print("ANALISI DIFFERENZE PER FASCIA DI CLUSTER")
print("="*70)

# cache000.map: cluster 59-11578
# cache001.map: cluster 2939-36218

ranges = [
    ("Cluster 1-58 (pre-cache)", 1, 58),
    ("Cluster 59-267 (cache + auxilary)", 59, 267),
    ("Cluster 268-1000", 268, 1000),
    ("Cluster 1001-2938 (cache000)", 1001, 2938),
    ("Cluster 2939-10000 (cache overlap)", 2939, 10000),
    ("Cluster 10001-11578 (cache000 end)", 10001, 11578),
    ("Cluster 11579-36218 (cache001)", 11579, 36218),
    ("Cluster 36219+ (post-cache)", 36219, 50000),
]

total_diff_all = 0
for name, start_c, end_c in ranges:
    start_off = cluster_to_offset(start_c)
    end_off = cluster_to_offset(end_c + 1)
    
    if start_off >= min(len(h1), len(h2)):
        continue
    
    actual_end = min(end_off, len(h1), len(h2))
    diff = sum(1 for i in range(start_off, actual_end) if h1[i] != h2[i])
    total_diff_all += diff
    
    if diff > 0:
        print(f"{name}: {diff:,} byte diversi")

# Inoltre, analizziamo la FAT separatamente
print("\n" + "="*70)
print("ANALISI FAT")
print("="*70)

FAT_OFFSET = 0x001A1000
fat_diff = sum(1 for i in range(FAT_OFFSET, DATA_START) if i < len(h1) and i < len(h2) and h1[i] != h2[i])
print(f"FAT area (0x{FAT_OFFSET:x} - 0x{DATA_START:x}): {fat_diff:,} byte diversi")

# E l'area prima della FAT
pre_fat_diff = sum(1 for i in range(min(FAT_OFFSET, len(h1), len(h2))) if h1[i] != h2[i])
print(f"Pre-FAT (0 - 0x{FAT_OFFSET:x}): {pre_fat_diff:,} byte diversi")

# Riepilogo
print("\n" + "="*70)
print("RIEPILOGO")
print("="*70)
total_diff = sum(1 for i in range(min(len(h1), len(h2))) if h1[i] != h2[i])
print(f"Differenze totali: {total_diff:,} bytes")

# Quali sono le aree MINIME da copiare per il restore?
# Teoria: tutto tranne cache001.map (cluster 11579+)
print("\n" + "="*70)
print("TEST: QUANTO SERVE SE ESCLUDIAMO SOLO cache001.map?")
print("="*70)

# Cluster 1-11578 (include cache000.map completa)
limit_c = 11578
limit_off = cluster_to_offset(limit_c + 1)
limit_off = min(limit_off, len(h1), len(h2))

diff_minimal = sum(1 for i in range(limit_off) if h1[i] != h2[i])
print(f"Se copiamo fino a cluster {limit_c}: {diff_minimal:,} byte")
print(f"Risparmio: {total_diff - diff_minimal:,} byte ({100*(total_diff - diff_minimal)/total_diff:.1f}%)")
