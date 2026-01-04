#!/usr/bin/env python3
"""
Trova save slot cercando SaveMeta.xbx per ogni gioco
"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_TABLE = 0x00161000

def cluster_to_offset(c):
    return DATA_START + (c - 2) * CLUSTER_SIZE

with open(HDD, 'rb') as f:
    data = f.read()

print("=== TROVA TUTTI I SAVE SLOT (cercando SaveMeta.xbx) ===\n")

# Cerca tutte le occorrenze di "SaveMeta.xbx" come filename in directory entries
# Il pattern è: fn_len (0x0C = 12) + attrs + "SaveMeta.xbx"
pattern = b"SaveMeta.xbx"

pos = 0
save_slots = []

while True:
    pos = data.find(pattern, pos)
    if pos == -1:
        break
    
    # Verifica che sia una directory entry valida
    # Il filename inizia a offset +2 dalla entry start
    entry_start = pos - 2
    
    if entry_start >= 0:
        fn_len = data[entry_start]
        attrs = data[entry_start + 1]
        
        if fn_len == 12:  # "SaveMeta.xbx" ha 12 caratteri
            # Questo è probabilmente un save slot valido
            fc = struct.unpack('<I', data[entry_start + 44:entry_start + 48])[0]
            
            # Calcola il cluster dove si trova questa entry
            if entry_start >= DATA_START:
                entry_cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2
            else:
                entry_cluster = "pre-data"
            
            save_slots.append({
                'entry_offset': entry_start,
                'entry_cluster': entry_cluster,
                'data_cluster': fc,
            })
            
            print(f"SaveMeta.xbx @ 0x{entry_start:08x}")
            print(f"  Entry in cluster: {entry_cluster}")
            print(f"  Data in cluster: {fc}")
    
    pos += 1

print(f"\n=== RIEPILOGO ===")
print(f"Trovati {len(save_slots)} save slot")

# Per ogni save slot, verifica se il cluster dell'entry è nella chain di un gioco
print("\n=== CORRELAZIONE CON GIOCHI ===")

# Giochi conosciuti e le loro chain
games = {
    "Mercenaries (4c410015)": 5,  # primo cluster
    "ToeJam (5345000f)": 40,       # primo cluster
}

def read_fat16(data, cluster):
    offset = FAT_TABLE + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_chain(data, first, max_len=500):
    if first == 0 or first >= 0xFFF0: return []
    chain = set([first])
    current = first
    for _ in range(max_len):
        n = read_fat16(data, current)
        if n >= 0xFFF8 or n == 0 or n in chain: break
        chain.add(n)
        current = n
    return chain

for slot in save_slots:
    entry_cluster = slot['entry_cluster']
    if entry_cluster == "pre-data":
        continue
    
    print(f"\nSave slot @ cluster {entry_cluster}:")
    
    # Controlla se entry_cluster è nelle chain dei giochi
    for game_name, game_first in games.items():
        chain = get_chain(data, game_first)
        if entry_cluster in chain:
            print(f"  -> Appartiene a {game_name}")
            break
    else:
        # Non appartiene a nessun gioco - è standalone!
        print(f"  -> STANDALONE (non in nessuna chain di gioco!)")
        print(f"     Questo cluster deve essere incluso separatamente!")
