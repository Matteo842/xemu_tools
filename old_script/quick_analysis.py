#!/usr/bin/env python3
"""Quick analysis - senza emoji per evitare problemi encoding"""

import struct

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"
FAT_TABLE_OFFSET = 0x00161000
FAT32_TABLE_OFFSET = 0x00311000
CLUSTER_SIZE = 16384
DATA_START = 0x00443000

def read_fat16_entry(data, cluster):
    offset = FAT_TABLE_OFFSET + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_fat_chain(data, first_cluster, max_length=10000):
    if first_cluster == 0 or first_cluster >= 0xFFF0: return []
    chain = [first_cluster]
    current = first_cluster
    for _ in range(max_length):
        next_c = read_fat16_entry(data, current)
        if next_c >= 0xFFF8 or next_c == 0x0000: break
        if next_c in chain: break
        chain.append(next_c)
        current = next_c
    return chain

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)

def parse_entry(data, offset):
    e = data[offset:offset + 64]
    fn_len = e[0]
    if fn_len in [0xFF, 0x00, 0xE5] or fn_len > 42: return None
    attrs = e[1]
    fn = e[2:2+fn_len].decode('ascii', errors='replace')
    fc = struct.unpack('<I', e[44:48])[0]
    fs = struct.unpack('<I', e[48:52])[0]
    if fc > 100000: return None
    return {
        'filename': fn, 'attrs': attrs, 'first_cluster': fc, 
        'size': fs, 'offset': offset, 'is_dir': bool(attrs & 0x10),
        'raw': e
    }

def scan_dir(data, first_cluster):
    entries = []
    chain = get_fat_chain(data, first_cluster)
    for cluster in chain[:5]:
        co = cluster_to_offset(cluster)
        for i in range(CLUSTER_SIZE // 64):
            e = parse_entry(data, co + i*64)
            if e: entries.append(e)
    return entries

print("=" * 60)
print("ANALISI DINAMICA MERCENARIES")
print("=" * 60)

with open(HDD_SOURCE, 'rb') as f:
    data = f.read()

print(f"File caricato: {len(data):,} bytes")

# UDATA cluster 4
udata = scan_dir(data, 4)
print(f"\nUDATA entries: {len(udata)}")
for e in udata:
    print(f"  {e['filename']} -> cluster {e['first_cluster']}")

# Mercenaries
merc_entry = next((e for e in udata if e['filename'].lower() == '4c410015'), None)
if merc_entry:
    print()
    print("=" * 60)
    print("MERCENARIES (4c410015)")
    print("=" * 60)
    print(f"Entry offset: 0x{merc_entry['offset']:08x}")
    print(f"First cluster: {merc_entry['first_cluster']}")
    
    # Scan game folder
    game_content = scan_dir(data, merc_entry['first_cluster'])
    print(f"\nContent entries: {len(game_content)}")
    
    all_clusters = set()
    folder_chain = get_fat_chain(data, merc_entry['first_cluster'])
    all_clusters.update(folder_chain)
    
    for e in game_content:
        typ = 'DIR' if e['is_dir'] else 'FILE'
        print(f"  {typ:4} {e['filename']:<25} cluster={e['first_cluster']:>5}")
        
        if e['first_cluster'] > 0:
            ec = get_fat_chain(data, e['first_cluster'])
            all_clusters.update(ec)
            
            # Sub-scan if dir
            if e['is_dir']:
                subs = scan_dir(data, e['first_cluster'])
                for se in subs:
                    print(f"       -> {se['filename']:<20} cluster={se['first_cluster']:>5}")
                    if se['first_cluster'] > 0:
                        sec = get_fat_chain(data, se['first_cluster'])
                        all_clusters.update(sec)
    
    print()
    print("=" * 60)
    print("RISULTATI")
    print("=" * 60)
    print(f"Total clusters: {len(all_clusters)}")
    sorted_c = sorted(all_clusters)
    print(f"Cluster range: {sorted_c[0]} - {sorted_c[-1]}")
    
    # Mostra cluster bassi (quelli interessanti)
    low_clusters = [c for c in sorted_c if c < 50]
    print(f"Cluster bassi (<50): {low_clusters}")
    
    # Verifica cluster 11 (0x31102C in FAT32)
    print()
    print("=" * 60)
    print("VERIFICA VS OFFSET NOTI")
    print("=" * 60)
    
    # 0x31102C corrisponde a cluster 11 in FAT32
    # (0x31102C - 0x311000) / 4 = 0x2C / 4 = 11
    cluster_11 = 11 in all_clusters
    cluster_38 = 38 in all_clusters  # Fine range noto
    
    print(f"Cluster 11 (0x31102C): {'TROVATO' if cluster_11 else 'NON TROVATO'}")
    print(f"Cluster 38 (fine range): {'TROVATO' if cluster_38 else 'NON TROVATO'}")
    
    # 0x463040 - entry "Mercenaries Saves"
    # Controlliamo se abbiamo quell'offset nelle entries
    entry_463040 = any(e['offset'] == 0x463040 for e in game_content)
    print(f"Entry @ 0x463040: {'TROVATO' if entry_463040 else 'NON TROVATO'}")
    
    # Se non trovato, cerchiamo manualmente
    if not entry_463040:
        print("\nCerco entry 'Mercenaries Saves'...")
        for e in game_content:
            if 'mercenari' in e['filename'].lower() or 'saves' in e['filename'].lower():
                print(f"  Trovato: '{e['filename']}' @ 0x{e['offset']:08x} cluster={e['first_cluster']}")
