#!/usr/bin/env python3
"""Trova chi punta a cluster 17710"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"

with open(HDD, 'rb') as f:
    data = f.read()

# Cerca first_cluster = 17710 (come valore a 4 byte)
target = struct.pack('<I', 17710)
print(f"Cerco first_cluster=17710 (0x{17710:08x})...")
print()

pos = 0
count = 0
while count < 30:
    pos = data.find(target, pos)
    if pos == -1: 
        break
    
    # Verifica se potrebbe essere a offset +44 di una directory entry
    entry_start = pos - 44
    if entry_start >= 0:
        fn_len = data[entry_start]
        if 1 <= fn_len <= 42:
            fn = data[entry_start+2:entry_start+2+fn_len].decode('ascii', errors='replace')
            attrs = data[entry_start + 1]
            is_dir = "DIR" if attrs & 0x10 else "FILE"
            print(f"0x{entry_start:08x}: {is_dir} '{fn}' -> 17710")
    
    pos += 1
    count += 1

print()
print(f"Trovati {count} riferimenti")
