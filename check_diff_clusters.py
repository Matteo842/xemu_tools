#!/usr/bin/env python3
"""Check cosa contengono i cluster dalle differenze"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd3.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384

with open(HDD, 'rb') as f:
    data = f.read()

def coff(c):
    return DATA_START + (c - 2) * CLUSTER_SIZE

# Cluster dalle differenze (calcolati dalle aree diverse)
# 0x05410000 -> circa cluster 5099
# 0x0a410000 -> circa cluster 10227  
# 0x1af60000 -> circa cluster 27365

# Ricalcolo preciso
offsets = [0x054170cc, 0x0a417000, 0x1af67000]

print("=== ANALISI CLUSTER DALLE DIFFERENZE ===\n")

for off in offsets:
    c = (off - DATA_START) // CLUSTER_SIZE + 2
    c_start = coff(c)
    
    chunk = data[c_start:c_start + 64]
    
    # Check se sembra directory entry
    fn_len = chunk[0]
    is_entry = 1 <= fn_len <= 42
    
    print(f"Offset 0x{off:08x} -> Cluster {c}")
    
    if is_entry:
        fn = chunk[2:2+fn_len].decode('ascii', errors='replace')
        fc = struct.unpack('<I', chunk[44:48])[0]
        print(f"  Entry: '{fn}' -> cluster {fc}")
    else:
        hex_short = ' '.join(f'{b:02x}' for b in chunk[:32])
        print(f"  Data: {hex_short}")
    print()
