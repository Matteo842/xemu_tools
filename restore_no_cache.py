#!/usr/bin/env python3
"""
RESTORE CHECKPOINT SENZA CACHE
Copia SOLO le aree necessarie, escludendo la cache (cluster 10000+)
"""

import struct
import os

HDD_SOURCE = r"D:\xemu\bk\xbox_hddh1.qcow2"  # Checkpoint 1 (backup)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"        # HDD attivo (copia di h2)

DATA_START = 0x001B3000
FAT_OFFSET = 0x001A1000
CLUSTER_SIZE = 16384

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 1) * CLUSTER_SIZE)

print("="*70)
print("RESTORE CHECKPOINT SENZA CACHE")
print("="*70)

# Carica entrambi
print("\nCaricamento source (H1)...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
print(f"H1 Size: {len(source):,} bytes")

print("Caricamento target...")
with open(HDD_TARGET, 'rb') as f:
    target = f.read()
print(f"Target Size: {len(target):,} bytes")

# Definiamo le aree da copiare (escludendo cluster 10000+)
# Basato sull'analisi:
# - FAT (0 - DATA_START): 10,943 byte diversi
# - Cluster 12-267 (auxilary.bin): 31,047 byte diversi
# - Cluster 268-1000: 38,381 byte diversi

# Trova ESATTAMENTE i byte diversi in queste aree
print("\nTrovando byte diversi (escludendo cache > cluster 10000)...")

# Limite: cluster 10000 = offset circa 0x09E33000
CACHE_START = cluster_to_offset(10000)
print(f"Cache inizia a: 0x{CACHE_START:08x}")

diff_positions = []
min_len = min(len(source), len(target))
limit = min(CACHE_START, min_len)  # Non andiamo oltre la cache

for i in range(limit):
    if source[i] != target[i]:
        diff_positions.append(i)

print(f"\nByte diversi (escludendo cache): {len(diff_positions):,}")

if len(diff_positions) == 0:
    print("Nessuna differenza nelle aree non-cache!")
    exit(0)

# Raggruppa in blocchi contigui
blocks = []
current_start = diff_positions[0]
current_end = diff_positions[0]

for pos in diff_positions[1:]:
    if pos == current_end + 1:
        current_end = pos
    else:
        blocks.append((current_start, current_end))
        current_start = pos
        current_end = pos
blocks.append((current_start, current_end))

print(f"Blocchi contigui: {len(blocks)}")

# Mostra distribuzione
fat_bytes = sum(end - start + 1 for start, end in blocks if end < DATA_START)
data_bytes = sum(end - start + 1 for start, end in blocks if start >= DATA_START)
print(f"  Byte nella FAT: {fat_bytes:,}")
print(f"  Byte nei dati: {data_bytes:,}")

total_bytes = sum(end - start + 1 for start, end in blocks)
print(f"\nByte totali da scrivere: {total_bytes:,}")

# Conferma
confirm = input("\nProcedere? (y/n): ").strip().lower()
if confirm != 'y':
    print("Annullato.")
    exit(0)

# Copia!
print("\nScrittura su target...")
with open(HDD_TARGET, 'r+b') as f:
    for start, end in blocks:
        f.seek(start)
        f.write(source[start:end + 1])
    
    f.flush()
    os.fsync(f.fileno())

print("\n" + "="*70)
print("RESTORE COMPLETATO (senza cache)!")
print("="*70)
print(f"Scritti {total_bytes:,} bytes in {len(blocks)} blocchi")
print(f"Cache (cluster 10000+) NON toccata")
print("Ora testa con xemu!")
