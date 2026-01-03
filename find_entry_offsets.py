#!/usr/bin/env python3
"""Trova offset esatti delle directory entries"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384

def cluster_to_offset(c):
    return DATA_START + ((c - 2) * CLUSTER_SIZE)

with open(HDD, 'rb') as f:
    data = f.read()

# Cluster 9 contiene la directory 9AA9F19E10C6
# Che contiene 'Mercenaries Saves' al cluster 11
c9_offset = cluster_to_offset(9)
print(f"Cluster 9 offset: 0x{c9_offset:08x}")

# Scan entries in cluster 9
print()
print("Entries nel cluster 9 (save slot dir):")
for i in range(10):
    offset = c9_offset + (i * 64)
    entry = data[offset:offset + 64]
    fn_len = entry[0]
    if fn_len in [0xFF, 0x00]: 
        continue
    attrs = entry[1]
    fn = entry[2:2+min(fn_len,42)].decode('ascii', errors='replace')
    fc = struct.unpack('<I', entry[44:48])[0]
    print(f"  Entry {i}: offset=0x{offset:08x} name='{fn}' cluster={fc}")

# Verifica 0x463040
print()
print("=" * 60)
print("VERIFICA OFFSET 0x463040")
print("=" * 60)

# L'offset 0x463040 dovrebbe essere in un cluster
target_offset = 0x463040
target_cluster = (target_offset - DATA_START) // CLUSTER_SIZE + 2
offset_in_cluster = (target_offset - DATA_START) % CLUSTER_SIZE
entry_index = offset_in_cluster // 64

print(f"0x463040 e nel cluster {target_cluster}")
print(f"Offset dentro cluster: 0x{offset_in_cluster:04x}")
print(f"Sarebbe entry index: {entry_index}")

# Leggi cosa c'e a 0x463040
entry_at_target = data[target_offset:target_offset + 64]
fn_len = entry_at_target[0]
if fn_len > 0 and fn_len < 0xE5:
    fn = entry_at_target[2:2+min(fn_len,42)].decode('ascii', errors='replace')
    fc = struct.unpack('<I', entry_at_target[44:48])[0]
    print(f"Entry @ 0x463040: name='{fn}' cluster={fc}")
else:
    print(f"Entry @ 0x463040: non valida (fn_len=0x{fn_len:02x})")

# Confronta con cluster 9
print()
print("=" * 60)
print("CONFRONTO OFFSET")
print("=" * 60)
print(f"Cluster 9 offset:  0x{c9_offset:08x}")
print(f"Target offset:     0x{target_offset:08x}")
print(f"Differenza:        0x{target_offset - c9_offset:08x} = {target_offset - c9_offset} bytes")
