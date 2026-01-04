#!/usr/bin/env python3
"""Analisi completa file nel save slot - cerca cluster frammentati"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd3.qcow2"
FAT = 0x00161000
DATA_START = 0x00443000
CLUSTER_SIZE = 16384

with open(HDD, 'rb') as f:
    data = f.read()

def rf(c):
    return struct.unpack('<H', data[FAT + c*2:FAT + c*2 + 2])[0]

def full_chain(first, max_len=10000):
    """Segui la chain completa"""
    ch = [first]
    c = first
    for _ in range(max_len):
        n = rf(c)
        if n >= 0xFFF8 or n == 0:
            break
        if n in ch:  # Loop detection
            print(f"  WARNING: Loop detected at cluster {n}")
            break
        ch.append(n)
        c = n
    return ch

# Halo 2 game folder chain
print("=== HALO 2 GAME FOLDER ===")
halo_chain = full_chain(54)
print(f"Chain 54: {len(halo_chain)} clusters")
print(f"  Range: {min(halo_chain)} - {max(halo_chain)}")

# Save slot 27127
print("\n=== SAVE SLOT 27127 ===")
c_off = DATA_START + (27127 - 2) * CLUSTER_SIZE

files_found = []
for i in range(20):
    e_off = c_off + i * 64
    e = data[e_off:e_off + 64]
    fn_len = e[0]
    if fn_len == 0xFF or fn_len == 0x00:
        continue
    if fn_len > 42:
        continue
    fn = e[2:2+fn_len].decode('ascii', errors='replace')
    fc = struct.unpack('<I', e[44:48])[0]
    fs = struct.unpack('<I', e[48:52])[0]
    
    ch = full_chain(fc)
    chain_size = len(ch) * CLUSTER_SIZE
    
    print(f"\n'{fn}':")
    print(f"  first_cluster: {fc}")
    print(f"  file_size: {fs:,} bytes")
    print(f"  chain: {len(ch)} clusters = {chain_size:,} bytes")
    print(f"  chain range: {min(ch)} - {max(ch)}")
    
    # Ci sono cluster fuori dal range di Halo 2?
    halo_set = set(halo_chain)
    outside = [c for c in ch if c not in halo_set]
    if outside:
        print(f"  *** CLUSTER FUORI HALO 2: {outside} ***")
    
    files_found.append({'name': fn, 'chain': ch, 'size': fs})

# Save slot 20539 (589BCCD01326)
print("\n=== SAVE SLOT 20539 (589BCCD01326) ===")
c_off = DATA_START + (20539 - 2) * CLUSTER_SIZE

for i in range(20):
    e_off = c_off + i * 64
    e = data[e_off:e_off + 64]
    fn_len = e[0]
    if fn_len == 0xFF or fn_len == 0x00:
        continue
    if fn_len > 42:
        continue
    fn = e[2:2+fn_len].decode('ascii', errors='replace')
    fc = struct.unpack('<I', e[44:48])[0]
    fs = struct.unpack('<I', e[48:52])[0]
    
    if fc == 0 or fc > 50000:
        continue
    
    ch = full_chain(fc)
    chain_size = len(ch) * CLUSTER_SIZE
    
    print(f"\n'{fn}':")
    print(f"  first_cluster: {fc}")
    print(f"  file_size: {fs:,} bytes")
    print(f"  chain: {len(ch)} clusters = {chain_size:,} bytes")
    
    outside = [c for c in ch if c not in halo_set]
    if outside:
        print(f"  *** CLUSTER FUORI HALO 2: {outside} ***")
