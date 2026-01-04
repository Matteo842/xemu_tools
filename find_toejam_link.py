#!/usr/bin/env python3
"""Trova come cluster 17710 è collegato a ToeJam"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_TABLE = 0x00161000

def read_fat16(data, cluster):
    offset = FAT_TABLE + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def cluster_to_offset(c):
    return DATA_START + (c - 2) * CLUSTER_SIZE

with open(HDD, 'rb') as f:
    data = f.read()

print("=== COME CLUSTER 17710 È COLLEGATO A TOEJAM ===")
print()

# Cluster 17710 contiene SaveMeta.xbx
# Ma come ci arriviamo da 5345000f?

# L'entry 5345000f in UDATA cluster 4 punta a cluster 40
# Ma 40 contiene dati, non directory entries

# Forse ToeJam usa una struttura diversa?
# Cerchiamo chi punta a cluster 17710

print("Cerco chi punta a cluster 17710 nella FAT...")
for c in range(2, 20000):
    next_c = read_fat16(data, c)
    if next_c == 17710:
        print(f"  Cluster {c} -> 17710")

# Cerchiamo quale directory entry ha first_cluster vicino a 17710
print("\nCerco directory entries con first_cluster = 17708-17712...")

# Scan aree directory note
for base_cluster in [2, 3, 4, 5, 6, 9, 10, 39, 40]:
    c_off = cluster_to_offset(base_cluster)
    
    for i in range(256):  # Tutte le possibili entries nel cluster
        e_off = c_off + i * 64
        if e_off + 64 > len(data):
            break
            
        e = data[e_off:e_off + 64]
        fn_len = e[0]
        
        if fn_len == 0xFF or fn_len == 0x00 or fn_len > 42:
            continue
        
        fc = struct.unpack('<I', e[44:48])[0]
        
        # Cluster vicino a 17710?
        if 17700 <= fc <= 17720:
            fn = e[2:2+fn_len].decode('ascii', errors='replace')
            print(f"  Cluster {base_cluster}, entry {i}: '{fn}' -> {fc}")

# Forse l'entry è in un cluster che non abbiamo cercato
# Cerchiamo in tutto l'HDD per "5345000f" come nome file
print("\nCerco '5345000f' come filename in tutto l'HDD...")
pattern = b'5345000f'
pos = 0
count = 0
while count < 10:
    pos = data.find(pattern, pos)
    if pos == -1:
        break
    
    # Verifica se è una directory entry (il nome inizia a offset +2)
    entry_start = pos - 2
    if entry_start >= 0:
        fn_len = data[entry_start]
        if fn_len == 8:  # "5345000f" ha 8 caratteri
            fc = struct.unpack('<I', data[entry_start + 44:entry_start + 48])[0]
            cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2 if entry_start >= DATA_START else "pre-data"
            print(f"  0x{entry_start:08x} (cluster {cluster}): '5345000f' -> cluster {fc}")
    
    pos += 1
    count += 1

# Guarda la FAT chain del cluster 40 (cartella ToeJam)
print("\nFAT chain dal cluster 40:")
chain = [40]
current = 40
for _ in range(200):
    next_c = read_fat16(data, current)
    if next_c >= 0xFFF8 or next_c == 0:
        break
    chain.append(next_c)
    current = next_c

print(f"  Lunghezza: {len(chain)}")
print(f"  Primi 20: {chain[:20]}")
print(f"  Ultimi 20: {chain[-20:]}")

# Forse il cluster 17710 è nella chain?
if 17710 in chain:
    print(f"  17710 È nella chain! Posizione: {chain.index(17710)}")
else:
    print(f"  17710 NON è nella chain del cluster 40")
