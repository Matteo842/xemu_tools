#!/usr/bin/env python3
"""Analizza TDATA vs UDATA per ToeJam"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_TABLE = 0x00161000

def read_fat16(data, cluster):
    offset = FAT_TABLE + (cluster * 2)
    return struct.unpack('<H', data[offset:offset + 2])[0]

def cluster_to_offset(c):
    return DATA_START + (c - 2) * CLUSTER_SIZE

def get_chain(data, first, max_len=200):
    if first == 0 or first >= 0xFFF0: return []
    chain = [first]
    current = first
    for _ in range(max_len):
        n = read_fat16(data, current)
        if n >= 0xFFF8 or n == 0 or n in chain: break
        chain.append(n)
        current = n
    return chain

def scan_dir(data, first_cluster, max_entries=50):
    entries = []
    chain = get_chain(data, first_cluster)
    for c in chain[:3]:
        c_off = cluster_to_offset(c)
        for i in range(256):
            e_off = c_off + i * 64
            if e_off + 64 > len(data): break
            e = data[e_off:e_off + 64]
            fn_len = e[0]
            if fn_len == 0xFF or fn_len == 0x00: continue
            if fn_len == 0xE5: continue  # deleted
            if fn_len > 42: continue
            fc = struct.unpack('<I', e[44:48])[0]
            if fc > 50000: continue
            fn = e[2:2+fn_len].decode('ascii', errors='replace')
            attrs = e[1]
            entries.append({'fn': fn, 'fc': fc, 'off': e_off, 'dir': bool(attrs & 0x10)})
            if len(entries) >= max_entries:
                return entries
    return entries

with open(HDD, 'rb') as f:
    data = f.read()

print("=== STRUTTURA XBOX TDATA vs UDATA ===\n")

# Cluster 2 contiene la root con TDATA e UDATA
print("CLUSTER 2 (root):")
root = scan_dir(data, 2)
for e in root:
    t = "DIR" if e['dir'] else "FILE"
    print(f"  {t} '{e['fn']}' -> cluster {e['fc']}")

# TDATA (cluster 3)
print("\nCLUSTER 3 (TDATA):")
tdata = scan_dir(data, 3)
for e in tdata:
    t = "DIR" if e['dir'] else "FILE"
    print(f"  {t} '{e['fn']}' -> cluster {e['fc']}")

# UDATA (cluster 4)
print("\nCLUSTER 4 (UDATA):")
udata = scan_dir(data, 4)
for e in udata:
    t = "DIR" if e['dir'] else "FILE"
    print(f"  {t} '{e['fn']}' -> cluster {e['fc']}")

# Cerca il ToeJam save slot
print("\n=== CERCA TOEJAM SAVE SLOT ===")

# Cluster 40 = ToeJam in UDATA, ma contiene dati
# Proviamo cluster 39 = ToeJam in TDATA?
print("\nToeJam TDATA (cluster 39):")
chain39 = get_chain(data, 39)
print(f"  Chain: {chain39[:10]}... ({len(chain39)} clusters)")

# Vediamo se c'è un save slot directory da qualche parte
# Cerchiamo entries con nomi tipo "XXXXXXXX" (hex save slot ID)
print("\n=== CERCA SAVE SLOT DIRECTORIES ===")

for base_name, base_cluster in [("TDATA/5345000f", 39), ("UDATA/5345000f", 40)]:
    print(f"\n{base_name} (cluster {base_cluster}):")
    chain = get_chain(data, base_cluster)
    
    # Scan tutti i cluster della chain per directory entries
    for c in chain[:5]:  # Solo primi 5 cluster
        c_off = cluster_to_offset(c)
        
        # Verifica se questo cluster contiene directory entries
        first_byte = data[c_off]
        if 1 <= first_byte <= 42:  # Sembra un filename length
            entries = scan_dir(data, c, max_entries=10)
            if entries:
                print(f"  Cluster {c}: {len(entries)} entries")
                for e in entries[:5]:
                    t = "DIR" if e['dir'] else "FILE"
                    print(f"    {t} '{e['fn']}' -> {e['fc']}")

# Controlla direttamente cluster 17710
print("\n=== CLUSTER 17710 (dove abbiamo trovato SaveMeta) ===")
entries_17710 = scan_dir(data, 17710, max_entries=10)
print(f"Entries trovate: {len(entries_17710)}")
for e in entries_17710:
    t = "DIR" if e['dir'] else "FILE"
    print(f"  {t} '{e['fn']}' -> cluster {e['fc']}")

# Chi punta a 17710?
print("\n=== CHI PUNTA A CLUSTER 17710? ===")
# Cerca nel FAT
for c in range(2, 20000):
    next_c = read_fat16(data, c)
    if next_c == 17710:
        print(f"FAT: cluster {c} -> 17710")

# Cerca nelle directory entries
print("Cerco entries con first_cluster=17710...")
for base in [2, 3, 4, 5, 6, 39, 40]:
    chain = get_chain(data, base)
    for c in chain[:3]:
        c_off = cluster_to_offset(c)
        for i in range(256):
            e_off = c_off + i * 64
            if e_off + 64 > len(data): break
            e = data[e_off:e_off + 64]
            fn_len = e[0]
            if fn_len == 0xFF or fn_len == 0x00 or fn_len > 42: continue
            fc = struct.unpack('<I', e[44:48])[0]
            if fc == 17710:
                fn = e[2:2+fn_len].decode('ascii', errors='replace')
                print(f"  Cluster {c}: '{fn}' -> 17710 @ 0x{e_off:08x}")
