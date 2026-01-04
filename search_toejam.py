#!/usr/bin/env python3
"""Cerca i veri save data di ToeJam"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_TABLE = 0x00161000

def cluster_to_offset(c):
    return DATA_START + ((c - 2) * CLUSTER_SIZE)

def read_fat16(data, cluster):
    offset = FAT_TABLE + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_chain(data, first, max_len=500):
    if first == 0 or first >= 0xFFF0: return []
    chain = [first]
    current = first
    for _ in range(max_len):
        n = read_fat16(data, current)
        if n >= 0xFFF8 or n == 0 or n in chain: break
        chain.append(n)
        current = n
    return chain

print("=" * 70)
print("RICERCA SAVE DATA TOEJAM")
print("=" * 70)

with open(HDD, 'rb') as f:
    data = f.read()

# Cerca pattern specifici di ToeJam
patterns = [
    b"ToeJam",
    b"Earl",
    b"Zona Verde",  # Dal screenshot "La Zona Verde"
    b"5345000f",
    b"TDATA",
    b"UDATA",
]

print("\nRicerca pattern nell'intero HDD...")
for pattern in patterns:
    pos = 0
    found = []
    while True:
        pos = data.find(pattern, pos)
        if pos == -1: break
        found.append(pos)
        pos += 1
        if len(found) >= 20: break
    
    if found:
        print(f"\nPattern '{pattern.decode('ascii', errors='replace')}':")
        for offset in found[:10]:
            if offset >= DATA_START:
                cluster = (offset - DATA_START) // CLUSTER_SIZE + 2
                off_in_c = (offset - DATA_START) % CLUSTER_SIZE
                print(f"  0x{offset:08x} (cluster {cluster}, +0x{off_in_c:04x})")
            else:
                section = "Header/FAT" if offset < DATA_START else "Data"
                print(f"  0x{offset:08x} ({section})")

# Analizza la struttura UDATA più in dettaglio
print("\n" + "=" * 70)
print("ANALISI UDATA DETTAGLIATA (cluster 3, 4)")
print("=" * 70)

for c in [3, 4, 5]:
    c_off = cluster_to_offset(c)
    print(f"\nCluster {c} @ 0x{c_off:08x}:")
    
    # Scan directory entries
    entries_found = 0
    for i in range(256):  # Max 256 entries per cluster
        e_off = c_off + i * 64
        e = data[e_off:e_off + 64]
        fn_len = e[0]
        
        if fn_len == 0xFF or fn_len == 0x00:
            continue
        if fn_len == 0xE5:  # Deleted
            continue
        if fn_len > 42:
            continue
        
        attrs = e[1]
        fn = e[2:2+fn_len].decode('ascii', errors='replace')
        fc = struct.unpack('<I', e[44:48])[0]
        
        # Filtro garbage
        if fc > 50000:
            continue
        
        is_dir = "DIR" if attrs & 0x10 else "FILE"
        print(f"  {is_dir:4} '{fn}' -> cluster {fc} @ 0x{e_off:08x}")
        entries_found += 1
        
        if entries_found > 20:
            break

# Verifica cosa c'e' veramente nei cluster 39-50 (area ToeJam)
print("\n" + "=" * 70)
print("CONTENUTO CLUSTER 39-50 (area ToeJam)")
print("=" * 70)

for c in range(39, 51):
    c_off = cluster_to_offset(c)
    chunk = data[c_off:c_off + 64]
    
    # Check se sembra una directory entry
    fn_len = chunk[0]
    is_dir_entry = 1 <= fn_len <= 42
    
    # Check se contiene pattern riconoscibili
    has_save = b"Save" in chunk or b"Meta" in chunk
    has_title = b"Title" in chunk
    
    if is_dir_entry or has_save or has_title:
        attrs = chunk[1]
        fn = chunk[2:2+min(fn_len, 42)].decode('ascii', errors='replace') if is_dir_entry else ""
        fc = struct.unpack('<I', chunk[44:48])[0] if is_dir_entry else 0
        
        print(f"Cluster {c}: fn='{fn}' cluster={fc} (entry?={is_dir_entry})")
    else:
        # Mostra primi bytes
        hex_short = ' '.join(f'{b:02x}' for b in chunk[:16])
        print(f"Cluster {c}: {hex_short}... (DATA)")

# Check FAT per capire la struttura
print("\n" + "=" * 70)
print("FAT ENTRIES per cluster 39-50")
print("=" * 70)
for c in range(39, 51):
    fat_val = read_fat16(data, c)
    next_c = "END" if fat_val >= 0xFFF8 else (f"-> {fat_val}" if fat_val > 0 else "FREE")
    print(f"  Cluster {c}: {next_c}")
