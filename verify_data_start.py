#!/usr/bin/env python3
"""
VERIFICA DATA START - Trova l'offset corretto per i cluster dati
"""

import struct

HDD_PATH = r"D:\xemu\bk\xbox_hdd2.qcow2"
FAT_TABLE_OFFSET = 0x00161000
CLUSTER_SIZE = 16384  # 16KB

print("=" * 70)
print("🔍 VERIFICA DATA START CORRETTO")
print("=" * 70)

with open(HDD_PATH, 'rb') as f:
    data = f.read()

# Mercenaries è nel cluster 4
# ToeJam è nel cluster 39

# Sappiamo che:
# - 4c410015 appare a 0x0044b002
# - 5345000f appare a 0x0044b042

# Se cluster 4 contiene 4c410015, allora:
# data_start + (4 - 2) * 16384 = 0x0044b000 (circa, allineato)
# data_start + 2 * 16384 = 0x0044b000
# data_start + 32768 = 0x0044b000
# data_start = 0x0044b000 - 0x8000 = 0x00443000

# Verifichiamo
test_starts = [
    0x00443000,  # Calcolato sopra
    0x00440000,  # Root directory
    0x00450000,  # Stima precedente
    0x00460000,  # Stima precedente
    0x00447000,  # Directory giochi
]

print("\nTest diversi DATA_START:\n")
for data_start in test_starts:
    # Cluster 4 (Mercenaries)
    cluster_4_offset = data_start + ((4 - 2) * CLUSTER_SIZE)
    
    if cluster_4_offset < len(data):
        sample = data[cluster_4_offset:cluster_4_offset + 32]
        ascii_sample = ''.join(chr(c) if 32 <= c < 127 else '.' for c in sample)
        has_merc = b'4c410015' in sample
        print(f"DATA_START=0x{data_start:08x}:")
        print(f"  Cluster 4 @ 0x{cluster_4_offset:08x}: \"{ascii_sample}\" {'<-- MERCENARIES!' if has_merc else ''}")
    
    # Cluster 39 (ToeJam)
    cluster_39_offset = data_start + ((39 - 2) * CLUSTER_SIZE)
    
    if cluster_39_offset < len(data):
        sample = data[cluster_39_offset:cluster_39_offset + 32]
        ascii_sample = ''.join(chr(c) if 32 <= c < 127 else '.' for c in sample)
        has_toejam = b'5345000f' in sample
        print(f"  Cluster 39 @ 0x{cluster_39_offset:08x}: \"{ascii_sample}\" {'<-- TOEJAM!' if has_toejam else ''}")
    print()

# Cerchiamo direttamente dove sono i game ID
print("\n" + "=" * 70)
print("RICERCA DIRETTA POSIZIONE GAME ID")
print("=" * 70)

for pattern, name in [(b'4c410015', 'Mercenaries'), (b'5345000f', 'ToeJam')]:
    pos = 0
    print(f"\n{name}:")
    found = 0
    while found < 5:
        pos = data.find(pattern, pos)
        if pos == -1:
            break
        
        # Prova a calcolare da quale DATA_START verrebbe
        # Se questo è cluster N, allora:
        # pos = data_start + (N - 2) * 16384
        # data_start = pos - (N - 2) * 16384
        
        # Per cluster 4: data_start = pos - 2 * 16384 = pos - 32768
        # Per cluster 39: data_start = pos - 37 * 16384 = pos - 606208
        
        if name == 'Mercenaries':
            implied_data_start = pos - (2 * CLUSTER_SIZE)
        else:
            implied_data_start = pos - (37 * CLUSTER_SIZE)
        
        print(f"  0x{pos:08x} → implied DATA_START: 0x{implied_data_start:08x}")
        pos += 1
        found += 1

# Test: qual è il vero data start basandosi sul cluster 2?
# Il cluster 2 è il primo cluster usabile (TDATA)
# TDATA dir entry è a 0x00443000, first_cluster = 2
# Quindi il contenuto di TDATA (il suo sub-directory) è nel cluster 2

print("\n" + "=" * 70)
print("VERIFICA CLUSTER 2 (TDATA)")
print("=" * 70)

# TDATA è una directory, il suo contenuto dovrebbe contenere le subdirectory
# Cerchiamo 4c410015 e 5345000f come subdirectory

# Il pattern directory entry per 4c410015:
# filename_size (1 byte) + filename (8 bytes) = "4c410015"

for data_start in [0x00443000, 0x00444000, 0x00445000, 0x00446000, 0x00447000]:
    cluster_2_offset = data_start + ((2 - 2) * CLUSTER_SIZE)  # = data_start
    
    sample = data[cluster_2_offset:cluster_2_offset + 256]
    
    # Cerca pattern di directory entry
    if b'TDATA' in sample or b'UDATA' in sample or b'4c410015' in sample:
        print(f"DATA_START=0x{data_start:08x} (cluster 2 @ 0x{cluster_2_offset:08x}):")
        ascii_sample = ''.join(chr(c) if 32 <= c < 127 else '.' for c in sample[:64])
        print(f"  Content: \"{ascii_sample}\"")
