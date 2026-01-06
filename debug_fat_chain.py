#!/usr/bin/env python3
"""
DEBUG FAT CHAIN - Perché auxilary.bin mostra solo 1 cluster?
Il file è 4MB ma la chain dice 1 cluster... qualcosa non va!
"""

import struct

HDD_H1 = r"D:\xemu\bk\xbox_hddh1.qcow2"

# Offset per HDD xemu standard
FAT_OFFSET = 0x001A1000
DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

print("Caricamento H1...")
with open(HDD_H1, 'rb') as f:
    data = f.read()
print(f"Size: {len(data):,} bytes")

# auxilary.bin inizia al cluster 12, size 4,186,132 bytes
# 4,186,132 / 16384 = 255.5 -> servono 256 cluster!
first_cluster = 12
expected_clusters = (4186132 + CLUSTER_SIZE - 1) // CLUSTER_SIZE
print(f"\nauxilary.bin: first_cluster={first_cluster}, expected {expected_clusters} cluster")

# Leggiamo manualmente le FAT entries
print(f"\n--- FAT16 entries (cluster 12-20) ---")
for c in range(12, 21):
    fat_off = FAT_OFFSET + (c * 2)
    fat_val = struct.unpack('<H', data[fat_off:fat_off + 2])[0]
    print(f"  Cluster {c}: FAT16 = 0x{fat_val:04x} ({fat_val})")

print(f"\n--- Proviamo con FAT contigue (cluster allocati linearmente) ---")
# Forse i cluster sono allocati in modo contiguo senza catena?
# Leggiamo i primi byte di ogni cluster per vedere se contengono dati

print(f"\nLettura cluster 12-270 (primi 16 byte di ogni cluster):")
for c in range(12, 270):
    offset = DATA_START + ((c - 1) * CLUSTER_SIZE)
    if offset + 16 > len(data):
        print(f"  Cluster {c}: FUORI dal file!")
        break
    first_bytes = data[offset:offset + 16]
    # Mostra solo se non è tutto zero
    if first_bytes != b'\x00' * 16:
        hex_str = ' '.join(f'{b:02x}' for b in first_bytes[:16])
        print(f"  Cluster {c} @ 0x{offset:08x}: {hex_str}")

# Confronto diretto: quali cluster sono DIVERSI tra H1 e H2?
print(f"\n{'='*60}")
print("CONFRONTO DIRETTO H1 vs H2 nei cluster 10-300")
print(f"{'='*60}")

print("\nCaricamento H2...")
with open(r"D:\xemu\bk\xbox_hddh2.qcow2", 'rb') as f:
    data2 = f.read()
print(f"H2 Size: {len(data2):,} bytes")

different_clusters = []
for c in range(10, 300):
    offset = DATA_START + ((c - 1) * CLUSTER_SIZE)
    if offset + CLUSTER_SIZE > len(data) or offset + CLUSTER_SIZE > len(data2):
        break
    
    h1_chunk = data[offset:offset + CLUSTER_SIZE]
    h2_chunk = data2[offset:offset + CLUSTER_SIZE]
    
    if h1_chunk != h2_chunk:
        # Conta byte diversi
        diff_bytes = sum(1 for a, b in zip(h1_chunk, h2_chunk) if a != b)
        different_clusters.append((c, diff_bytes))

print(f"\nCluster con differenze: {len(different_clusters)}")
for c, diff in different_clusters[:30]:  # Primi 30
    offset = DATA_START + ((c - 1) * CLUSTER_SIZE)
    print(f"  Cluster {c} @ 0x{offset:08x}: {diff:,} byte diversi")

if len(different_clusters) > 30:
    print(f"  ... e altri {len(different_clusters) - 30} cluster")

# Riepilogo
total_diff_bytes = sum(diff for _, diff in different_clusters)
print(f"\nTOTALE: {len(different_clusters)} cluster diversi, {total_diff_bytes:,} byte diversi")
