#!/usr/bin/env python3
"""
ANALISI FAT CHAIN - Trova le catene FAT per ogni gioco
"""

import os
import struct

# File da analizzare
HDD_PATH = r"D:\xemu\bk\xbox_hdd2.qcow2"

print("=" * 70)
print("🔗 ANALISI FAT CHAIN PER GIOCHI")
print("=" * 70)

with open(HDD_PATH, 'rb') as f:
    data = f.read()

# Dati dai risultati precedenti
GAMES = {
    "4c410015": {"name": "Mercenaries", "dir_offset": 0x00447000, "first_cluster": 4},
    "5345000f": {"name": "ToeJam & Earl III", "dir_offset": 0x00447040, "first_cluster": 39},
}

# FAT table start (primo header FATX + 0x1000)
FATX_HEADERS = [0x000d0000, 0x00160000, 0x001f0000, 0x00280000, 0x00310000]

def follow_fat_chain(data, fat_start, first_cluster, max_clusters=1000):
    """Segue la catena FAT e ritorna lista di cluster."""
    chain = [first_cluster]
    current = first_cluster
    
    for _ in range(max_clusters):
        # FAT16: 2 bytes per entry
        fat_offset = fat_start + (current * 2)
        
        if fat_offset + 2 > len(data):
            print(f"   ⚠️ FAT offset fuori range: 0x{fat_offset:08x}")
            break
        
        next_cluster = struct.unpack('<H', data[fat_offset:fat_offset + 2])[0]
        
        # End of chain markers (FAT16)
        if next_cluster >= 0xFFF8:
            break
        if next_cluster == 0x0000:
            break
        
        chain.append(next_cluster)
        current = next_cluster
    
    return chain

def cluster_to_offset(cluster, data_start, cluster_size=16384):
    """Converte numero cluster in offset fisico."""
    # I cluster 0 e 1 sono riservati
    return data_start + ((cluster - 2) * cluster_size)

# Prova diversi offset FAT per trovare quello giusto
print("\n📋 RICERCA FAT TABLE CORRETTA\n")

for fatx_offset in FATX_HEADERS:
    fat_start = fatx_offset + 0x1000
    
    # Leggi primo entry FAT
    first_entries = []
    for i in range(10):
        if fat_start + i*2 + 2 <= len(data):
            entry = struct.unpack('<H', data[fat_start + i*2:fat_start + i*2 + 2])[0]
            first_entries.append(entry)
    
    # La FAT valida dovrebbe avere: entry[0]=0xFFF8 (riservato), entry[1]=0xFFFF (riservato)
    if first_entries and first_entries[0] == 0xFFF8:
        print(f"✅ FAT potenzialmente valida a 0x{fat_start:08x}")
        print(f"   Primi entries: {[f'0x{e:04x}' for e in first_entries[:10]]}")
        
        # Prova a seguire le catene per i giochi
        for game_id, game_info in GAMES.items():
            print(f"\n   🎮 {game_info['name']} (cluster {game_info['first_cluster']}):")
            
            chain = follow_fat_chain(data, fat_start, game_info['first_cluster'])
            print(f"      Chain length: {len(chain)}")
            print(f"      Clusters: {chain[:10]}{'...' if len(chain) > 10 else ''}")
            
            # Calcola offset dati (stima)
            # Per la partizione E, i dati dovrebbero essere dopo root directory
            # Root dir è a ~0x440000, quindi dati a ~0x450000 o ~0x460000
            data_start_candidates = [0x00450000, 0x00460000, 0x00470000]
            
            for data_start in data_start_candidates:
                first_data_offset = cluster_to_offset(game_info['first_cluster'], data_start)
                if first_data_offset < len(data):
                    sample = data[first_data_offset:first_data_offset + 16]
                    ascii_sample = ''.join(chr(c) if 32 <= c < 127 else '.' for c in sample)
                    print(f"      Data@0x{data_start:08x} → 0x{first_data_offset:08x}: \"{ascii_sample}\"")
    else:
        print(f"❌ FAT non valida a 0x{fat_start:08x} (first entry: 0x{first_entries[0]:04x} se presente)")

# =============================================================================
# ANALISI SPECIFICA AREE GIOCHI
# =============================================================================
print("\n" + "=" * 70)
print("📋 ANALISI AREE SPECIFICHE DEI GIOCHI")
print("=" * 70)

# Aree dove abbiamo trovato i game ID
game_id_locations = {
    "4c410015": [0x00447002, 0x0044b002],
    "5345000f": [0x00447042, 0x0044b042],
}

for game_id, locations in game_id_locations.items():
    print(f"\n🎮 {game_id}:")
    for loc in locations:
        # Leggi contesto ampio
        ctx_start = (loc // 0x1000) * 0x1000  # Allinea a 4KB
        ctx_size = 0x100
        context = data[ctx_start:ctx_start + ctx_size]
        
        # Cerca pattern rilevanti
        patterns = [b'SaveMeta', b'SaveImage', b'JAC01', game_id.encode()]
        for p in patterns:
            pos = context.find(p)
            if pos != -1:
                abs_pos = ctx_start + pos
                print(f"   {p.decode('ascii', errors='ignore')}: 0x{abs_pos:08x}")

# =============================================================================
# MAPPA DELLE AREE PER GIOCO
# =============================================================================
print("\n" + "=" * 70)
print("📋 MAPPA AREE DA COPIARE PER SINGOLO GIOCO")
print("=" * 70)

print("""
Basandomi sull'analisi, per BACKUP/RESTORE di Mercenaries (4c410015):

1. DIRECTORY ENTRY
   - Offset: 0x00447000 (64 bytes)
   
2. DATI GIOCO (dove appare il game ID)
   - 0x0044b000 (area intorno a 0x0044b002)
   
3. SAVE FILES
   - 0x00463000 (area SaveMeta.xbx)
   - 0x0046b000 (area JAC01)
   
4. FAT ENTRIES
   - La catena FAT che parte dal cluster 4
   - PROBLEMA: Come fare merge senza rompere cluster 39 (ToeJam)?
   
Per ToeJam (5345000f):
   - Dir entry: 0x00447040
   - First cluster: 39
   - SaveMeta: 0x118f3000

CONCLUSIONE:
Se Mercenaries usa cluster 4, 5, 6... 
e ToeJam usa cluster 39, 40, 41...
Non si sovrappongono! Possiamo copiarli separatamente!

MA dobbiamo stare attenti alla Directory UDATA/TDATA che li contiene entrambi.
""")

print("=" * 70)
print("✅ ANALISI COMPLETATA")
print("=" * 70)
