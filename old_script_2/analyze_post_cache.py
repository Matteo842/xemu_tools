#!/usr/bin/env python3
"""
Analizza cosa c'è nell'area cluster 36219+ (post-cache)
"""

import struct

HDD_H1 = r"D:\xemu\bk\xbox_hddh1.qcow2"
HDD_H2 = r"D:\xemu\bk\xbox_hddh2.qcow2"

DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 1) * CLUSTER_SIZE)

print("Caricamento H1...")
with open(HDD_H1, 'rb') as f:
    h1 = f.read()

# Calcola quanti cluster ha H1
h1_data_size = len(h1) - DATA_START
h1_clusters = h1_data_size // CLUSTER_SIZE
print(f"H1: {len(h1):,} bytes = {h1_clusters} cluster")

# Cerca file nell'area 36219+
print(f"\n{'='*60}")
print("CERCA FILE NELL'AREA CLUSTER 36219+")
print(f"{'='*60}")

# Cerca pattern di directory entries (filename validi)
start_offset = cluster_to_offset(36219)
print(f"Offset inizio: 0x{start_offset:08x}")

# Cerca nomi di file comuni
patterns = [
    b'cache',
    b'.map',
    b'.bin',
    b'.xbx',
    b'auxilary',
    b'profile',
    b'Save',
]

for pattern in patterns:
    pos = start_offset
    count = 0
    while pos < len(h1):
        pos = h1.find(pattern, pos)
        if pos == -1 or pos >= len(h1):
            break
        count += 1
        if count <= 3:
            cluster = (pos - DATA_START) // CLUSTER_SIZE + 1 if pos >= DATA_START else 'pre'
            print(f"'{pattern.decode()}' @ 0x{pos:08x} (cluster ~{cluster})")
        pos += 1
    if count > 3:
        print(f"  ... e altre {count - 3} occorrenze")

# Analizza i primi cluster dell'area 36219+
print(f"\n{'='*60}")
print("PRIMI BYTE DEI CLUSTER 36219-36230")
print(f"{'='*60}")

for c in range(36219, 36231):
    offset = cluster_to_offset(c)
    if offset + 16 > len(h1):
        print(f"Cluster {c}: FUORI RANGE (H1 finisce prima)")
        break
    
    first_bytes = h1[offset:offset + 32]
    
    # Prova a interpretare come directory entry
    fn_len = first_bytes[0]
    attrs = first_bytes[1]
    
    if 1 <= fn_len <= 42 and attrs <= 0x3F:
        try:
            name = first_bytes[2:2+fn_len].decode('ascii', errors='replace')
            if name.isprintable():
                print(f"Cluster {c}: Possibile entry: '{name}' attrs=0x{attrs:02x}")
                continue
        except:
            pass
    
    # Mostra hex
    hex_str = ' '.join(f'{b:02x}' for b in first_bytes[:16])
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in first_bytes[:16])
    print(f"Cluster {c}: {hex_str} | {ascii_str}")

# Verifica se H1 ha meno cluster di 36219
h1_max_cluster = (len(h1) - DATA_START) // CLUSTER_SIZE
h2_max_cluster = (1188298752 - DATA_START) // CLUSTER_SIZE  # H2 size
print(f"\n{'='*60}")
print("RIEPILOGO DIMENSIONI")
print(f"{'='*60}")
print(f"H1 max cluster: ~{h1_max_cluster}")
print(f"H2 max cluster: ~{h2_max_cluster}")
print(f"Cluster 36219 offset: 0x{cluster_to_offset(36219):08x} = {cluster_to_offset(36219):,} bytes")
print(f"H1 termina a offset: 0x{len(h1):08x} = {len(h1):,} bytes")
