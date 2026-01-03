#!/usr/bin/env python3
"""
EXPLORE GAME STRUCTURE - Analizza la struttura interna di un gioco Xbox

Obiettivo: Capire quali cluster sono usati dai file INTERNI alla cartella del gioco
per poter calcolare dinamicamente le metadata_areas.

QUESTO SCRIPT È SOLO LETTURA - Non modifica nulla!
"""

import struct
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

# =============================================================================
# CONFIGURAZIONE - SOLO LETTURA!
# =============================================================================
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # ⚠️ SOLO LETTURA!

# Struttura FATX (da analisi precedenti)
FAT_TABLE_OFFSET = 0x00161000   # FAT16 Table
FAT32_TABLE_OFFSET = 0x00311000 # FAT32 Table
CLUSTER_SIZE = 16384            # 16KB
DATA_START = 0x00443000         # Inizio area dati

# Directory entries
GAME_DIR_OFFSET = 0x00447000    # Directory UDATA (giochi)
ENTRY_SIZE = 64                 # Ogni entry è 64 bytes

# Giochi conosciuti
GAMES = {
    "4c410015": {"name": "Mercenaries", "dir_entry_offset": 0x00447000, "first_cluster": 4},
    "5345000f": {"name": "ToeJam & Earl III", "dir_entry_offset": 0x00447040, "first_cluster": 39},
}

# =============================================================================
# STRUTTURE DATI
# =============================================================================

@dataclass
class DirectoryEntry:
    """Entry di directory FATX (64 bytes)."""
    offset: int              # Offset assoluto nell'HDD
    filename: str            # Nome file/directory
    filename_len: int        # Lunghezza nome
    attributes: int          # Attributi (0x10 = directory)
    is_directory: bool
    first_cluster: int       # Primo cluster dei dati
    file_size: int           # Dimensione file
    is_deleted: bool         # Entry eliminata?
    raw_data: bytes          # Dati grezzi per debug

@dataclass
class ClusterInfo:
    """Informazioni su un cluster."""
    cluster_num: int
    fat16_offset: int        # Offset nella FAT16
    fat32_offset: int        # Offset nella FAT32
    data_offset: int         # Offset dei dati
    fat16_value: int         # Valore nella FAT16
    fat32_value: int         # Valore nella FAT32

# =============================================================================
# FUNZIONI DI PARSING
# =============================================================================

def read_fat16_entry(data: bytes, cluster: int) -> int:
    """Legge una entry FAT16 (2 bytes)."""
    offset = FAT_TABLE_OFFSET + (cluster * 2)
    if offset + 2 > len(data):
        return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def read_fat32_entry(data: bytes, cluster: int) -> int:
    """Legge una entry FAT32 (4 bytes)."""
    offset = FAT32_TABLE_OFFSET + (cluster * 4)
    if offset + 4 > len(data):
        return 0xFFFFFFFF
    return struct.unpack('<I', data[offset:offset + 4])[0]

def get_fat_chain(data: bytes, first_cluster: int, max_length: int = 10000) -> List[int]:
    """Costruisce la catena FAT partendo dal primo cluster."""
    chain = [first_cluster]
    current = first_cluster
    
    for _ in range(max_length):
        next_cluster = read_fat16_entry(data, current)
        
        # End of chain (FAT16)
        if next_cluster >= 0xFFF8:
            break
        if next_cluster == 0x0000:
            break
        
        chain.append(next_cluster)
        current = next_cluster
    
    return chain

def cluster_to_offset(cluster: int) -> int:
    """Converte numero cluster in offset fisico nei dati."""
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)

def parse_directory_entry(data: bytes, offset: int) -> Optional[DirectoryEntry]:
    """Parsa una directory entry da 64 bytes."""
    entry_data = data[offset:offset + ENTRY_SIZE]
    
    if len(entry_data) < ENTRY_SIZE:
        return None
    
    filename_len = entry_data[0]
    
    # Entry vuote o fine directory
    if filename_len == 0xFF or filename_len == 0x00:
        return None
    
    # Entry eliminata
    is_deleted = (filename_len == 0xE5)
    if is_deleted:
        # Per entry eliminate, il secondo byte ha la lunghezza originale
        filename_len = entry_data[1] if entry_data[1] <= 42 else 0
    
    if filename_len > 42:
        filename_len = 42
    
    # Offset del filename dipende se è deleted o no
    if is_deleted:
        filename_raw = entry_data[2:2 + filename_len]
    else:
        filename_raw = entry_data[2:2 + filename_len]
    
    try:
        filename = filename_raw.decode('ascii', errors='replace').rstrip('\x00\xff')
    except:
        filename = "<invalid>"
    
    # Attributi e altri campi
    # Offset 0x2B = attributes (secondo la documentazione free60)
    # Ma dalle nostre analisi sembra essere a offset diversi
    # Proviamo con offset 0x2B (43 decimale)
    attributes = entry_data[43] if len(entry_data) > 43 else 0
    
    # First cluster: offset 0x2C (44 decimale), 4 bytes
    first_cluster = struct.unpack('<I', entry_data[44:48])[0] if len(entry_data) >= 48 else 0
    
    # File size: offset 0x30 (48 decimale), 4 bytes
    file_size = struct.unpack('<I', entry_data[48:52])[0] if len(entry_data) >= 52 else 0
    
    return DirectoryEntry(
        offset=offset,
        filename=filename,
        filename_len=filename_len,
        attributes=attributes,
        is_directory=bool(attributes & 0x10),
        first_cluster=first_cluster,
        file_size=file_size,
        is_deleted=is_deleted,
        raw_data=entry_data
    )

def scan_directory_cluster(data: bytes, cluster: int) -> List[DirectoryEntry]:
    """Scansiona un cluster di directory per trovare tutte le entry."""
    entries = []
    cluster_offset = cluster_to_offset(cluster)
    
    # Un cluster può contenere 16KB / 64 bytes = 256 entry
    max_entries = CLUSTER_SIZE // ENTRY_SIZE
    
    for i in range(max_entries):
        entry_offset = cluster_offset + (i * ENTRY_SIZE)
        entry = parse_directory_entry(data, entry_offset)
        
        if entry is None:
            continue
        
        entries.append(entry)
    
    return entries

def scan_directory(data: bytes, first_cluster: int) -> List[DirectoryEntry]:
    """Scansiona l'intera directory seguendo la catena FAT."""
    all_entries = []
    
    # Ottieni la catena di cluster per questa directory
    cluster_chain = get_fat_chain(data, first_cluster)
    
    for cluster in cluster_chain:
        entries = scan_directory_cluster(data, cluster)
        all_entries.extend(entries)
    
    return all_entries

def get_cluster_info(data: bytes, cluster: int) -> ClusterInfo:
    """Ottiene informazioni complete su un cluster."""
    fat16_offset = FAT_TABLE_OFFSET + (cluster * 2)
    fat32_offset = FAT32_TABLE_OFFSET + (cluster * 4)
    data_offset = cluster_to_offset(cluster)
    
    fat16_value = read_fat16_entry(data, cluster)
    fat32_value = read_fat32_entry(data, cluster)
    
    return ClusterInfo(
        cluster_num=cluster,
        fat16_offset=fat16_offset,
        fat32_offset=fat32_offset,
        data_offset=data_offset,
        fat16_value=fat16_value,
        fat32_value=fat32_value
    )

# =============================================================================
# FUNZIONI DI ANALISI
# =============================================================================

def explore_game(data: bytes, game_id: str) -> Dict:
    """Esplora completamente un gioco e restituisce tutte le informazioni."""
    if game_id not in GAMES:
        print(f"❌ Gioco sconosciuto: {game_id}")
        return {}
    
    game = GAMES[game_id]
    print(f"\n{'='*70}")
    print(f"🎮 ESPLORAZIONE: {game['name']} ({game_id})")
    print(f"{'='*70}")
    
    result = {
        "game_id": game_id,
        "game_name": game["name"],
        "dir_entry_offset": game["dir_entry_offset"],
        "first_cluster": game["first_cluster"],
        "folder_clusters": [],
        "internal_entries": [],
        "all_clusters": set(),
        "fat16_areas": [],
        "fat32_areas": [],
    }
    
    # 1. Catena FAT della cartella principale del gioco
    print(f"\n📁 1. CARTELLA PRINCIPALE")
    folder_chain = get_fat_chain(data, game["first_cluster"])
    result["folder_clusters"] = folder_chain
    result["all_clusters"].update(folder_chain)
    
    print(f"   First cluster: {game['first_cluster']}")
    print(f"   Cluster chain: {folder_chain[:10]}{'...' if len(folder_chain) > 10 else ''}")
    print(f"   Total clusters: {len(folder_chain)}")
    
    # 2. Contenuto della directory (file e subdirectory interni)
    print(f"\n📂 2. CONTENUTO DIRECTORY")
    internal_entries = scan_directory(data, game["first_cluster"])
    
    for entry in internal_entries:
        status = "🗑️" if entry.is_deleted else "✅"
        type_str = "📁" if entry.is_directory else "📄"
        
        print(f"   {status} {type_str} {entry.filename:<30} "
              f"cluster:{entry.first_cluster:>5} size:{entry.file_size:>10,}")
        
        if not entry.is_deleted:
            result["internal_entries"].append({
                "filename": entry.filename,
                "is_directory": entry.is_directory,
                "first_cluster": entry.first_cluster,
                "file_size": entry.file_size,
                "entry_offset": entry.offset,
            })
            
            # Aggiungi i cluster di questo file/subdir
            if entry.first_cluster > 0:
                entry_chain = get_fat_chain(data, entry.first_cluster)
                result["all_clusters"].update(entry_chain)
                
                print(f"      └─ Cluster chain: {entry_chain[:5]}{'...' if len(entry_chain) > 5 else ''} "
                      f"({len(entry_chain)} clusters)")
    
    # 3. Esplora ricorsivamente le subdirectory
    print(f"\n📂 3. SUBDIRECTORY (ricorsivo)")
    for entry in internal_entries:
        if entry.is_directory and not entry.is_deleted and entry.first_cluster > 0:
            print(f"\n   📁 Subdirectory: {entry.filename}")
            sub_entries = scan_directory(data, entry.first_cluster)
            
            for sub_entry in sub_entries:
                if not sub_entry.is_deleted:
                    status = "🗑️" if sub_entry.is_deleted else "✅"
                    type_str = "📁" if sub_entry.is_directory else "📄"
                    
                    print(f"      {status} {type_str} {sub_entry.filename:<25} "
                          f"cluster:{sub_entry.first_cluster:>5} size:{sub_entry.file_size:>10,}")
                    
                    if sub_entry.first_cluster > 0:
                        sub_chain = get_fat_chain(data, sub_entry.first_cluster)
                        result["all_clusters"].update(sub_chain)
                        print(f"         └─ Cluster chain: {sub_chain[:5]}{'...' if len(sub_chain) > 5 else ''}")
    
    # 4. Calcola offset FAT16 e FAT32 per tutti i cluster
    print(f"\n📊 4. OFFSET FAT CALCOLATI")
    all_clusters_sorted = sorted(result["all_clusters"])
    
    print(f"   Totale cluster unici: {len(all_clusters_sorted)}")
    print(f"   Range cluster: {min(all_clusters_sorted)} - {max(all_clusters_sorted)}")
    
    for cluster in all_clusters_sorted:
        info = get_cluster_info(data, cluster)
        result["fat16_areas"].append((info.fat16_offset, 2))
        result["fat32_areas"].append((info.fat32_offset, 4))
    
    # Raggruppa aree contigue per FAT32
    fat32_ranges = []
    if result["fat32_areas"]:
        sorted_fat32 = sorted(result["fat32_areas"], key=lambda x: x[0])
        current_start = sorted_fat32[0][0]
        current_end = current_start + 4
        
        for offset, size in sorted_fat32[1:]:
            if offset == current_end:
                current_end = offset + size
            else:
                fat32_ranges.append((current_start, current_end - current_start))
                current_start = offset
                current_end = offset + size
        
        fat32_ranges.append((current_start, current_end - current_start))
    
    print(f"\n   FAT32 Ranges (contigue):")
    for start, size in fat32_ranges:
        print(f"      0x{start:08x} - 0x{start + size:08x} ({size} bytes, {size // 4} entries)")
    
    # 5. Confronta con le metadata_areas hardcoded (se esistono)
    print(f"\n📋 5. CONFRONTO CON METADATA_AREAS CONOSCIUTE")
    
    # Valori che sappiamo funzionano per Mercenaries
    known_metadata = {
        "4c410015": [
            (0x0031102C, 112, "Directory_Metadata_Mercenaries"),
            (0x00463040, 64, "SaveEntry_Mercenaries"),
        ]
    }
    
    if game_id in known_metadata:
        for offset, size, desc in known_metadata[game_id]:
            # Verifica se questo offset è coperto dai nostri calcoli
            covered = any(start <= offset < start + sz for start, sz in fat32_ranges)
            status = "✅" if covered else "❌"
            
            # Calcola a quale cluster corrisponde questo offset
            if offset >= FAT32_TABLE_OFFSET:
                cluster = (offset - FAT32_TABLE_OFFSET) // 4
                in_our_clusters = cluster in result["all_clusters"]
                cluster_status = "✅" if in_our_clusters else "❌"
            else:
                cluster = "N/A"
                cluster_status = "❓"
            
            print(f"   {status} 0x{offset:08x} ({size} bytes): {desc}")
            print(f"      └─ Cluster: {cluster} - In nostri cluster: {cluster_status}")
    
    return result

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("🔍 EXPLORE GAME STRUCTURE - Analisi struttura interna Xbox saves")
    print("=" * 70)
    print(f"\n⚠️  QUESTO SCRIPT È SOLO LETTURA!")
    print(f"📂 Sorgente: {Path(HDD_SOURCE).name}")
    
    # Carica HDD
    print(f"\n⏳ Caricamento HDD...")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    print(f"   Dimensione: {len(data):,} bytes")
    
    # Analizza ogni gioco
    results = {}
    for game_id in GAMES:
        results[game_id] = explore_game(data, game_id)
    
    # Riepilogo finale
    print("\n" + "=" * 70)
    print("📊 RIEPILOGO FINALE")
    print("=" * 70)
    
    for game_id, result in results.items():
        if result:
            print(f"\n🎮 {result['game_name']} ({game_id}):")
            print(f"   Cluster totali: {len(result['all_clusters'])}")
            print(f"   File/Directory interni: {len(result['internal_entries'])}")
            
            # Controlla se 0x31102C è nei nostri range
            test_offset = 0x0031102C
            test_cluster = (test_offset - FAT32_TABLE_OFFSET) // 4
            in_clusters = test_cluster in result['all_clusters']
            print(f"   Cluster 11 (0x31102C) nei nostri?: {in_clusters}")
    
    print("\n" + "=" * 70)
    print("✅ ANALISI COMPLETATA")
    print("=" * 70)

if __name__ == "__main__":
    main()
