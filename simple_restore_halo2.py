#!/usr/bin/env python3
"""
SIMPLE HALO 2 CHECKPOINT RESTORE
Basato sull'analisi: i cluster 10-272 contengono tutto il save.
Più la directory entry al cluster 11473.
"""

import struct
import os

HDD_SOURCE = r"D:\xemu\bk\xbox_hddh1.qcow2"  # Checkpoint 1 (backup)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"        # HDD attivo (copia di h2)

# Offset per HDD xemu standard
FAT_OFFSET = 0x001A1000
DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 1) * CLUSTER_SIZE)

print("="*70)
print("SIMPLE HALO 2 CHECKPOINT RESTORE")
print("="*70)

# Carica source
print(f"\nCaricamento source: {HDD_SOURCE}")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
print(f"Size: {len(source):,} bytes")

# I cluster che contengono il save di Halo 2 (basato sull'analisi)
# - Directory entries del save slot: cluster 11473
# - Dati del save (auxilary.bin etc): cluster 10-280 (per sicurezza)
# - FAT entries per questi cluster

SAVE_CLUSTERS = list(range(10, 280))  # Cluster dati
ENTRY_CLUSTERS = [11473]  # Cluster con directory entries

print(f"\nCluster da copiare: {SAVE_CLUSTERS[0]}-{SAVE_CLUSTERS[-1]} ({len(SAVE_CLUSTERS)} cluster)")
print(f"Directory entries: cluster {ENTRY_CLUSTERS}")

# Prepara i dati da scrivere
data_to_write = []

# 1. FAT entries (sia FAT16)
print("\n[1] Preparazione FAT16 entries...")
for cluster in SAVE_CLUSTERS:
    fat_off = FAT_OFFSET + (cluster * 2)
    fat_data = source[fat_off:fat_off + 2]
    data_to_write.append(('fat16', fat_off, fat_data))

# 2. Cluster dati
print("[2] Preparazione data clusters...")
for cluster in SAVE_CLUSTERS + ENTRY_CLUSTERS:
    offset = cluster_to_offset(cluster)
    if offset + CLUSTER_SIZE <= len(source):
        chunk = source[offset:offset + CLUSTER_SIZE]
        data_to_write.append(('data', offset, chunk))
    else:
        print(f"  SKIP cluster {cluster} (fuori dal file)")

print(f"\nTotale operazioni: {len(data_to_write)}")

# Conferma
print("\n" + "="*70)
print("CONFERMA RESTORE")
print("="*70)
print(f"Source: {HDD_SOURCE}")
print(f"Target: {HDD_TARGET}")
print(f"Cluster dati: {len(SAVE_CLUSTERS)}")
print(f"Cluster entries: {len(ENTRY_CLUSTERS)}")
total_bytes = sum(len(d[2]) for d in data_to_write)
print(f"Bytes totali da scrivere: {total_bytes:,}")

confirm = input("\nProcedere? (y/n): ").strip().lower()
if confirm != 'y':
    print("Annullato.")
    exit(0)

# Esegui il restore
print("\n[3] Scrittura su target...")
with open(HDD_TARGET, 'r+b') as f:
    for dtype, offset, data in data_to_write:
        f.seek(offset)
        f.write(data)
    
    f.flush()
    os.fsync(f.fileno())

print("\n" + "="*70)
print("RESTORE COMPLETATO!")
print("="*70)
print(f"Scritti {total_bytes:,} bytes")
print("Ora testa con xemu!")
