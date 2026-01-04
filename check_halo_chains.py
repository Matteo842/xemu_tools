#!/usr/bin/env python3
"""Check FAT chains for Halo 2 save clusters"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd3.qcow2"
FAT = 0x00161000

with open(HDD, 'rb') as f:
    data = f.read()

def rf(c):
    return struct.unpack('<H', data[FAT + c*2:FAT + c*2 + 2])[0]

def chain(c):
    ch = [c]
    for _ in range(500):
        n = rf(c)
        if n >= 0xFFF8 or n == 0 or n in ch: break
        ch.append(n)
        c = n
    return ch

print("=== FAT CHAINS ===")

# Save slot Halo 2 a cluster 27127
print("\nSave slot Halo 2 (cluster 27127):")
ch27127 = chain(27127)
print(f"  Chain length: {len(ch27127)}")
print(f"  Chain: {ch27127[:20]}...")

# Cluster 27339 (dalla diff)
print("\nCluster 27339:")
ch27339 = chain(27339)
print(f"  Chain length: {len(ch27339)}")
print(f"  Chain: {ch27339[:20]}...")

# Cluster 20539 (dalla diff) 
print("\nCluster 20539:")
ch20539 = chain(20539)
print(f"  Chain length: {len(ch20539)}")
print(f"  Chain: {ch20539[:20]}...")

# Check cosa c'è a cluster 147+ (FAT32 diff area)
print("\n=== CLUSTER 147+ ===")
for c in range(147, 160):
    fat_val = rf(c)
    if fat_val != 0 and fat_val != 0xFFFF:
        print(f"  Cluster {c} -> {fat_val}")
