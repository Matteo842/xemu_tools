#!/usr/bin/env python3
"""
ANALISI CACHE HALO 2 v2 - Verifica struttura contigua
"""

import struct

HDD_FILE = r"D:\xemu\bk\xbox_hddh1.qcow2"

FAT_OFFSET = 0x001A1000
DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

def read_fat16_entry(data, cluster):
    offset = FAT_OFFSET + (cluster * 2)
    if offset + 2 > len(data):
        return 0xFFFF
    return struct.unpack('<H', data[offset:offset+2])[0]

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 1) * CLUSTER_SIZE)

print("=" * 70)
print("ANALISI CACHE HALO 2 v2 - Struttura Contigua")
print("=" * 70)

with open(HDD_FILE, 'rb') as f:
    data = f.read()

print(f"HDD: {len(data):,} bytes")

# I file cache con le loro dimensioni note
cache_files = [
    ("cache000.map", 59, 188_743_680),   # 180 MB
    ("cache001.map", 2939, 545_259_520),  # 520 MB
]

print("\n1. ANALISI STRUTTURA CACHE:")
print("-" * 50)

for name, start_cluster, expected_size in cache_files:
    print(f"\n{name}:")
    print(f"  Start cluster: {start_cluster}")
    print(f"  Expected size: {expected_size:,} bytes ({expected_size / (1024*1024):.1f} MB)")
    
    # Calcola quanti cluster servono
    clusters_needed = (expected_size + CLUSTER_SIZE - 1) // CLUSTER_SIZE
    print(f"  Clusters needed: {clusters_needed:,}")
    
    end_cluster = start_cluster + clusters_needed - 1
    print(f"  End cluster: {end_cluster}")
    
    # Verifica FAT entries per questi cluster
    fat_values = {}
    for c in range(start_cluster, min(start_cluster + 10, end_cluster + 1)):
        fat_val = read_fat16_entry(data, c)
        fat_values[c] = fat_val
    
    print(f"  FAT entries (primi 10):")
    for c, fv in fat_values.items():
        status = "END" if fv >= 0xFFF8 else "FREE" if fv == 0 else f"next={fv}"
        print(f"    Cluster {c}: 0x{fv:04x} ({status})")

print("\n\n2. IL PROBLEMA:")
print("-" * 50)
print("""
I file cache di Halo 2:
- cache000.map: cluster 59-11578 (11520 cluster = 180MB)
- cache001.map: cluster 2939-36218 (33280 cluster = 520MB)

Ma la FAT NON registra questi cluster!
Il primo cluster ha FAT=0xFFFF (end), tutti gli altri hanno FAT=0x0000 (free)

Halo 2 scrive DIRETTAMENTE nei cluster contigui dopo il primo,
senza aggiornare la FAT!
""")

print("\n3. POSSIBILE SOLUZIONE:")
print("-" * 50)

# Calcola il range totale
total_start = 59
total_end = 36218  # Fine di cache001.map

print(f"""
Se includiamo TUTTI i cluster dal {total_start} al {total_end}:
- Totale cluster: {total_end - total_start + 1:,}
- Totale size: {(total_end - total_start + 1) * CLUSTER_SIZE / (1024*1024):.1f} MB

Questo è CHIRURGICO perché:
- Cattura TUTTI i dati di Halo 2
- I cluster sono CONTIGUI (59-36218)
- Non tocca cluster di altri giochi (se presenti sarebbero dopo 36218)

IL TRUCCO: Usare la SIZE del file dalla directory entry!
Poi calcolare quanti cluster CONTIGUI servono.
""")

print("\n4. VERIFICA FILE SIZE DALLE DIRECTORY ENTRIES:")
print("-" * 50)

# Scansiona per trovare cache000.map e cache001.map
# Le entries sono nel save slot (cluster 10)
slot_offset = cluster_to_offset(10)
slot_data = data[slot_offset:slot_offset + CLUSTER_SIZE]

for i in range(0, CLUSTER_SIZE, 64):
    entry = slot_data[i:i+64]
    if len(entry) < 64:
        break
    
    fn_len = entry[0]
    if fn_len == 0 or fn_len == 0xFF or fn_len > 42:
        continue
    
    try:
        name = entry[2:2+fn_len].decode('ascii')
        first_cluster = struct.unpack('<I', entry[44:48])[0]
        file_size = struct.unpack('<I', entry[48:52])[0]
        
        if 'cache' in name.lower():
            clusters_for_file = (file_size + CLUSTER_SIZE - 1) // CLUSTER_SIZE
            end_cluster = first_cluster + clusters_for_file - 1
            
            print(f"\n  {name}:")
            print(f"    first_cluster: {first_cluster}")
            print(f"    file_size: {file_size:,} bytes ({file_size / (1024*1024):.1f} MB)")
            print(f"    clusters needed: {clusters_for_file:,}")
            print(f"    cluster range: {first_cluster} - {end_cluster}")
    except:
        pass

print("\n" + "=" * 70)
print("CONCLUSIONE")
print("=" * 70)
print("""
POSSIAMO FARLO!

Il trucco è:
1. Quando troviamo un file come cache000.map con file_size grande
2. Calcolare: clusters_needed = ceil(file_size / CLUSTER_SIZE)
3. Includere TUTTI i cluster contigui: first_cluster to first_cluster + clusters_needed

Questo cattura i file cache ANCHE SE la FAT non li registra!
""")
