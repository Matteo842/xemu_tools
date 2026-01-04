#!/usr/bin/env python3
"""Scan completo UDATA per trovare TUTTE le entries"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_TABLE = 0x00161000

def rf(d, c):
    return struct.unpack('<H', d[FAT_TABLE + c*2:FAT_TABLE + c*2 + 2])[0]

def chain(d, first):
    if first == 0 or first >= 0xFFF0: return []
    ch = [first]
    c = first
    for _ in range(500):
        n = rf(d, c)
        if n >= 0xFFF8 or n == 0 or n in ch: break
        ch.append(n)
        c = n
    return ch

def coff(c):
    return DATA_START + (c - 2) * CLUSTER_SIZE

with open(HDD, 'rb') as f:
    data = f.read()

print("=== SCAN COMPLETO UDATA ===\n")

# UDATA è a cluster 4 (dalla nostra analisi precedente)
# Ma facciamo un full scan di tutti i cluster nella chain

udata_chain = chain(data, 4)
print(f"UDATA chain: {udata_chain}")
print()

all_entries = []

for cluster in udata_chain:
    c_off = coff(cluster)
    print(f"Cluster {cluster} @ 0x{c_off:08x}:")
    
    for i in range(256):
        e_off = c_off + i * 64
        if e_off + 64 > len(data): break
        
        e = data[e_off:e_off + 64]
        fn_len = e[0]
        
        if fn_len == 0xFF: break  # End of directory
        if fn_len == 0x00: continue  # Empty
        if fn_len == 0xE5: continue  # Deleted
        if fn_len > 42: continue  # Invalid
        
        attrs = e[1]
        fn = e[2:2+fn_len].decode('ascii', errors='replace')
        fc = struct.unpack('<I', e[44:48])[0]
        
        if fc > 50000: continue  # Garbage
        
        is_dir = "DIR" if attrs & 0x10 else "FILE"
        
        all_entries.append({
            'name': fn,
            'cluster': fc,
            'is_dir': is_dir,
            'offset': e_off
        })
        
        print(f"  Entry {i}: {is_dir} '{fn}' -> cluster {fc}")

print(f"\n=== RIEPILOGO ===")
print(f"Entries totali in UDATA: {len(all_entries)}")

# Cerchiamo entries con cluster alti (>10000) che potrebbero essere save slot ToeJam
print("\nEntries con cluster > 10000:")
for e in all_entries:
    if e['cluster'] > 10000:
        print(f"  '{e['name']}' -> {e['cluster']}")

# Cerchiamo entries che potrebbero essere save slot (nomi hex)
print("\nPossibili save slot (nomi hex-like):")
for e in all_entries:
    name = e['name']
    # Nome hex-like: 8+ caratteri alfanumerici
    if len(name) >= 8 and all(c in '0123456789ABCDEFabcdef' for c in name):
        print(f"  '{name}' -> cluster {e['cluster']}")
