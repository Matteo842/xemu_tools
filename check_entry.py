#!/usr/bin/env python3
"""Cerca 589BCCD01326 nell'HDD"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd3.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384

with open(HDD, 'rb') as f:
    data = f.read()

pattern = b"589BCCD01326"
print(f"Cerca '{pattern.decode()}'...")

pos = 0
while True:
    pos = data.find(pattern, pos)
    if pos == -1:
        break
    
    entry_start = pos - 2
    if entry_start >= 0:
        fn_len = data[entry_start]
        if fn_len == 12:
            attrs = data[entry_start + 1]
            fc = struct.unpack('<I', data[entry_start + 44:entry_start + 48])[0]
            cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2 if entry_start >= DATA_START else "pre"
            
            t = "DIR" if attrs & 0x10 else "FILE"
            print(f"  @ 0x{entry_start:08x} (cluster {cluster}): {t} -> fc={fc}")
    
    pos += 1

print("\nDone")
