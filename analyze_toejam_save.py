#!/usr/bin/env python3
"""Analizza l'area SaveMeta di ToeJam"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384

with open(HDD, 'rb') as f:
    data = f.read()

# Area 0x118f3000 - SaveMeta.xbx di ToeJam
print("=== AREA SAVEMETA TOEJAM (0x118f3000) ===")
offset = 0x118f3000
cluster = (offset - DATA_START) // CLUSTER_SIZE + 2
print(f"Offset: 0x{offset:08x}")
print(f"Cluster: {cluster}")

# Leggi questa area
area = data[offset:offset + 256]
print("\nHex dump:")
for i in range(0, 128, 16):
    hex_p = ' '.join(f"{a:02x}" for a in area[i:i+16])
    asc = ''.join(chr(a) if 32 <= a < 127 else '.' for a in area[i:i+16])
    print(f"  0x{offset+i:08x}: {hex_p}  {asc}")

# Parse come directory entry
fn_len = area[0]
if 1 <= fn_len <= 42:
    fn = area[2:2+fn_len].decode('ascii', errors='replace')
    fc = struct.unpack('<I', area[44:48])[0]
    print(f"\nParsed entry 1: filename='{fn}' first_cluster={fc}")

# Seconda entry a +64
fn_len2 = area[64]
if 1 <= fn_len2 <= 42:
    fn2 = area[66:66+fn_len2].decode('ascii', errors='replace')
    fc2 = struct.unpack('<I', area[64+44:64+48])[0]
    print(f"Parsed entry 2: filename='{fn2}' first_cluster={fc2}")

# Cerca la struttura di ToeJam 
print("\n=== STRUTTURA TOEJAM SAVE ===")

# L'entry 5345000f in cluster 3 dice first_cluster=39
# Ma i save sono a cluster 17710+
# Cerchiamo come sono collegati

# Cerca entry che puntano a cluster 17710
print("\nCerco entries che puntano a cluster 17710...")
for search_cluster in [3, 4, 39, 40]:
    c_off = DATA_START + (search_cluster - 2) * CLUSTER_SIZE
    print(f"\nCluster {search_cluster} @ 0x{c_off:08x}:")
    
    for i in range(20):  # Prime 20 entries
        e_off = c_off + i * 64
        e = data[e_off:e_off + 64]
        fn_len = e[0]
        
        if fn_len == 0xFF or fn_len == 0x00:
            continue
        if fn_len > 42:
            continue
        
        attrs = e[1]
        fn = e[2:2+fn_len].decode('ascii', errors='replace')
        fc = struct.unpack('<I', e[44:48])[0]
        
        if fc > 10000:  # Cluster alti - interessanti!
            print(f"  Entry {i}: '{fn}' -> cluster {fc} (ALTO!)")
        elif '5345' in fn.lower() or 'save' in fn.lower() or 'toejam' in fn.lower():
            print(f"  Entry {i}: '{fn}' -> cluster {fc}")
