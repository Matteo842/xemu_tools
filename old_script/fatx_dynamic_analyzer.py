#!/usr/bin/env python3
"""
FATX ANALYZER FINALE - Solo Mercenaries per ora
Trova TUTTE le aree necessarie per backup/restore

SOLO LETTURA!
"""

import struct
from pathlib import Path
from typing import List, Set, Tuple

# =============================================================================
# CONFIGURAZIONE
# =============================================================================
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # SOLO LETTURA!

FAT_TABLE_OFFSET = 0x00161000   
FAT32_TABLE_OFFSET = 0x00311000 
CLUSTER_SIZE = 16384            
DATA_START = 0x00443000         
ENTRY_SIZE = 64                 

# =============================================================================
# FUNZIONI
# =============================================================================

def read_fat16(data: bytes, cluster: int) -> int:
    offset = FAT_TABLE_OFFSET + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_fat_chain(data: bytes, first: int) -> List[int]:
    if first == 0 or first >= 0xFFF0: return []
    chain = [first]
    current = first
    seen = set([first])
    for _ in range(50000):
        next_c = read_fat16(data, current)
        if next_c >= 0xFFF8 or next_c == 0: break
        if next_c in seen: break
        chain.append(next_c)
        seen.add(next_c)
        current = next_c
    return chain

def cluster_to_offset(cluster: int) -> int:
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)

def parse_entry(data: bytes, offset: int) -> dict:
    e = data[offset:offset + 64]
    if len(e) < 64:
        return None
    fn_len = e[0]
    if fn_len == 0xFF or fn_len == 0x00 or fn_len == 0xE5:
        return None
    if fn_len > 42:
        return None
    attrs = e[1]
    fn = e[2:2+fn_len].decode('ascii', errors='replace').rstrip('\x00\xff')
    fc = struct.unpack('<I', e[44:48])[0]
    fs = struct.unpack('<I', e[48:52])[0]
    # Skip garbage - cluster troppo alto per un gioco Xbox
    if fc > 20000:
        return None
    return {
        'offset': offset,
        'filename': fn,
        'attrs': attrs,
        'is_dir': bool(attrs & 0x10),
        'first_cluster': fc,
        'size': fs,
        'raw': e
    }

def scan_dir(data: bytes, first_cluster: int, max_clusters: int = 2) -> List[dict]:
    """Scansiona directory - limita clusters per evitare di leggere dati file."""
    entries = []
    chain = get_fat_chain(data, first_cluster)
    
    for cluster in chain[:max_clusters]:  # Solo primi N cluster
        cluster_offset = cluster_to_offset(cluster)
        for i in range(CLUSTER_SIZE // 64):
            offset = cluster_offset + i * 64
            if offset + 64 > len(data):
                break
            e = parse_entry(data, offset)
            if e:
                entries.append(e)
    return entries

def analyze_mercenaries(data: bytes) -> dict:
    """Analizza Mercenaries e calcola tutte le aree."""
    print("=" * 60)
    print("ANALISI MERCENARIES (4c410015)")
    print("=" * 60)
    
    result = {
        'all_clusters': set(),
        'directory_entries': [],
        'fat16_ranges': [],
        'fat32_ranges': [],
    }
    
    # 1. UDATA (cluster 4) - trova entry 4c410015
    print("\n[1] Scan UDATA (cluster 4)")
    udata_entries = scan_dir(data, 4)
    merc_entry = None
    for e in udata_entries:
        if e['filename'].lower() == '4c410015':
            merc_entry = e
            print(f"    Trovato: '{e['filename']}' @ 0x{e['offset']:08x} -> cluster {e['first_cluster']}")
            break
    
    if not merc_entry:
        print("    ERRORE: Mercenaries non trovato!")
        return result
    
    # Aggiungi entry UDATA del gioco
    result['directory_entries'].append((merc_entry['offset'], 64))
    
    # 2. Cartella gioco (cluster 5)
    print(f"\n[2] Scan cartella gioco (cluster {merc_entry['first_cluster']})")
    game_folder_chain = get_fat_chain(data, merc_entry['first_cluster'])
    result['all_clusters'].update(game_folder_chain)
    print(f"    Folder chain: {game_folder_chain[:5]}... ({len(game_folder_chain)} clusters)")
    
    game_contents = scan_dir(data, merc_entry['first_cluster'])
    print(f"    Entries: {len(game_contents)}")
    
    for e in game_contents:
        t = 'DIR' if e['is_dir'] else 'FILE'
        print(f"    {t:4} {e['filename']:<25} cluster={e['first_cluster']:>5} @ 0x{e['offset']:08x}")
        
        result['directory_entries'].append((e['offset'], 64))
        
        if e['first_cluster'] > 0:
            chain = get_fat_chain(data, e['first_cluster'])
            result['all_clusters'].update(chain)
        
        # Subdirectory (es: 9AA9F19E10C6)
        if e['is_dir'] and e['first_cluster'] > 0:
            print(f"         [sub-scan cluster {e['first_cluster']}]")
            sub_entries = scan_dir(data, e['first_cluster'])
            for se in sub_entries:
                st = 'DIR' if se['is_dir'] else 'FILE'
                print(f"         {st:4} {se['filename']:<20} cluster={se['first_cluster']:>5} @ 0x{se['offset']:08x}")
                
                result['directory_entries'].append((se['offset'], 64))
                
                if se['first_cluster'] > 0:
                    sub_chain = get_fat_chain(data, se['first_cluster'])
                    result['all_clusters'].update(sub_chain)
    
    # 3. Calcola ranges
    sorted_clusters = sorted(result['all_clusters'])
    print(f"\n[3] Cluster totali: {len(sorted_clusters)}")
    print(f"    Range: {sorted_clusters[0]} - {sorted_clusters[-1]}")
    print(f"    Cluster <50: {[c for c in sorted_clusters if c < 50]}")
    
    # FAT16 ranges
    fat16_ranges = []
    start = sorted_clusters[0]
    end = start
    for c in sorted_clusters[1:]:
        if c == end + 1:
            end = c
        else:
            fat16_ranges.append((FAT_TABLE_OFFSET + start * 2, (end - start + 1) * 2))
            start = c
            end = c
    fat16_ranges.append((FAT_TABLE_OFFSET + start * 2, (end - start + 1) * 2))
    result['fat16_ranges'] = fat16_ranges
    
    # FAT32 ranges
    fat32_ranges = []
    start = sorted_clusters[0]
    end = start
    for c in sorted_clusters[1:]:
        if c == end + 1:
            end = c
        else:
            fat32_ranges.append((FAT32_TABLE_OFFSET + start * 4, (end - start + 1) * 4))
            start = c
            end = c
    fat32_ranges.append((FAT32_TABLE_OFFSET + start * 4, (end - start + 1) * 4))
    result['fat32_ranges'] = fat32_ranges
    
    # 4. Output
    print(f"\n[4] Aree calcolate:")
    print(f"    Directory entries: {len(result['directory_entries'])}")
    for o, s in result['directory_entries']:
        print(f"        0x{o:08x}")
    
    print(f"\n    FAT16 ranges: {len(result['fat16_ranges'])}")
    for o, s in result['fat16_ranges'][:5]:
        c1 = (o - FAT_TABLE_OFFSET) // 2
        c2 = c1 + s // 2 - 1
        print(f"        0x{o:08x} ({s} bytes, cluster {c1}-{c2})")
    
    print(f"\n    FAT32 ranges: {len(result['fat32_ranges'])}")
    for o, s in result['fat32_ranges'][:5]:
        c1 = (o - FAT32_TABLE_OFFSET) // 4
        c2 = c1 + s // 4 - 1
        print(f"        0x{o:08x} ({s} bytes, cluster {c1}-{c2})")
    
    # 5. VERIFICA
    print("\n" + "=" * 60)
    print("VERIFICA VS OFFSET NOTI FUNZIONANTI")
    print("=" * 60)
    
    # 0x31102C = FAT32 entry per cluster 11
    cluster_11 = 11 in result['all_clusters']
    fat32_covers = any(o <= 0x31102C < o + s for o, s in result['fat32_ranges'])
    print(f"\n0x31102C (FAT32 cluster 11-38):")
    print(f"    Cluster 11 nei nostri: {'SI' if cluster_11 else 'NO'}")
    print(f"    Coperto da FAT32 ranges: {'SI' if fat32_covers else 'NO'}")
    
    # 0x463040 = entry "Mercenaries Saves"
    entry_covers = any(o == 0x463040 for o, s in result['directory_entries'])
    print(f"\n0x463040 (Mercenaries Saves entry):")
    print(f"    Nelle nostre entries: {'SI' if entry_covers else 'NO'}")
    
    # Se non coperto, vediamo perche
    if not entry_covers:
        # 0x463040 e' in cluster 10, offset 0x40
        c10_offset = cluster_to_offset(10)
        print(f"    Cluster 10 offset: 0x{c10_offset:08x}")
        print(f"    0x463040 - 0x{c10_offset:08x} = 0x{0x463040 - c10_offset:04x}")
        # Check if cluster 10 in our set
        print(f"    Cluster 10 nei nostri: {'SI' if 10 in result['all_clusters'] else 'NO'}")
    
    return result

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("FATX ANALYZER - SOLO LETTURA")
    print("=" * 60)
    
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    print(f"File: {len(data):,} bytes\n")
    
    result = analyze_mercenaries(data)
    
    print("\n" + "=" * 60)
    print("RIEPILOGO FINALE")
    print("=" * 60)
    print(f"Cluster: {len(result['all_clusters'])}")
    print(f"Directory entries: {len(result['directory_entries'])}")
    print(f"FAT16 ranges: {len(result['fat16_ranges'])}")
    print(f"FAT32 ranges: {len(result['fat32_ranges'])}")

if __name__ == "__main__":
    main()
