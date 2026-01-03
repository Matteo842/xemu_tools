#!/usr/bin/env python3
"""
FATX CHAIN RESTORE - Ripristino singolo gioco seguendo la catena FAT

Questo script:
1. Parsa le directory entries per trovare il cluster iniziale del gioco
2. Segue la catena FAT per trovare TUTTI i cluster del gioco
3. Estrae: directory entry + FAT entries + dati cluster
4. Al restore, ripristina SOLO quelle parti specifiche
"""

import os
import struct
import json
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

# Config
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"
BACKUP_DIR = r"d:\GitHub\xemu_tools\chain_backups"

# Struttura Xbox HDD (dalle nostre analisi)
# La partizione E (saves) inizia a circa 0x120000
FATX_HEADER_OFFSET = 0x00120000  # Header FATX partizione E
CLUSTER_SIZE = 16384  # 16KB (dalle analisi)

# Offset delle aree chiave
FAT_START = 0x00130000  # File Allocation Table (stima)
ROOT_DIR_START = 0x00440000  # Root directory (TDATA, UDATA)
GAME_DIR_START = 0x00447000  # Directory giochi (4c410015, 5345000f)
DATA_START = 0x0044b000  # Inizio dati

# Game database
GAMES = {
    "4c410015": "Mercenaries",
    "5345000f": "ToeJam & Earl III",
}


@dataclass
class DirectoryEntry:
    offset: int
    raw_data: bytes
    filename: str
    first_cluster: int
    file_size: int
    is_directory: bool
    is_deleted: bool


@dataclass
class GameBackup:
    game_id: str
    game_name: str
    directory_entries: List[Tuple[int, bytes]]  # (offset, data)
    fat_entries: List[Tuple[int, int]]  # (cluster_num, next_cluster)
    data_clusters: List[Tuple[int, bytes]]  # (offset, data)
    metadata_areas: List[Tuple[int, bytes]]  # Aree metadata critiche


def parse_directory_entry(data: bytes, offset: int) -> Optional[DirectoryEntry]:
    """Parsa una directory entry da 64 bytes."""
    entry = data[offset:offset + 64]
    if len(entry) < 64:
        return None
    
    filename_size = entry[0]
    is_deleted = (filename_size == 0xE5)
    
    if filename_size == 0xFF or filename_size == 0x00:
        return None
    
    if is_deleted:
        filename_size = entry[1] if entry[1] < 42 else 8
        try:
            filename = entry[2:2 + filename_size].decode('ascii', errors='replace')
        except:
            filename = ""
    else:
        if filename_size > 42:
            filename_size = 42
        try:
            filename = entry[1:1 + filename_size].decode('ascii', errors='replace')
        except:
            filename = ""
    
    attributes = entry[43]
    first_cluster = struct.unpack('<I', entry[44:48])[0]
    file_size = struct.unpack('<I', entry[48:52])[0]
    
    return DirectoryEntry(
        offset=offset,
        raw_data=entry,
        filename=filename,
        first_cluster=first_cluster,
        file_size=file_size,
        is_directory=bool(attributes & 0x10),
        is_deleted=is_deleted,
    )


def follow_fat_chain(data: bytes, first_cluster: int, fat_start: int) -> List[int]:
    """Segue la catena FAT a partire dal cluster iniziale."""
    chain = [first_cluster]
    current = first_cluster
    max_iterations = 10000  # Sicurezza
    
    for _ in range(max_iterations):
        # FAT16: 2 bytes per entry
        fat_offset = fat_start + (current * 2)
        
        if fat_offset + 2 > len(data):
            break
        
        next_cluster = struct.unpack('<H', data[fat_offset:fat_offset + 2])[0]
        
        # End of chain markers
        if next_cluster >= 0xFFF8:
            break
        if next_cluster == 0x0000:
            break
        
        chain.append(next_cluster)
        current = next_cluster
    
    return chain


def cluster_to_offset(cluster: int, data_start: int = DATA_START) -> int:
    """Converte numero cluster in offset fisico."""
    # I primi 2 cluster sono riservati
    return data_start + ((cluster - 2) * CLUSTER_SIZE)


def find_all_game_entries(data: bytes, game_id: str) -> List[DirectoryEntry]:
    """Trova tutte le directory entries relative a un gioco."""
    entries = []
    game_id_bytes = game_id.encode('ascii')
    
    # Cerca in tutta l'area directory
    for offset in range(ROOT_DIR_START, DATA_START, 64):
        entry = parse_directory_entry(data, offset)
        if entry and game_id.lower() in entry.filename.lower():
            entries.append(entry)
            print(f"   Found entry: {entry.filename} @ 0x{offset:08x} cluster:{entry.first_cluster}")
    
    # Cerca anche nelle sottodirectory (area 0x460000+)
    for offset in range(0x460000, 0x480000, 64):
        entry = parse_directory_entry(data, offset)
        if entry and entry.filename and len(entry.filename) > 2:
            # Potrebbe essere un save file
            if not entry.is_deleted:
                entries.append(entry)
    
    return entries


def backup_game_with_chain(game_id: str) -> Tuple[str, str]:
    """Crea backup completo di un gioco seguendo la catena FAT."""
    print("=" * 70)
    print(f"📦 BACKUP CON CATENA FAT: {GAMES.get(game_id, game_id)}")
    print("=" * 70)
    
    # Carica HDD
    print(f"\n📂 Caricamento: {Path(HDD_SOURCE).name}")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    
    backup = GameBackup(
        game_id=game_id,
        game_name=GAMES.get(game_id, "Unknown"),
        directory_entries=[],
        fat_entries=[],
        data_clusters=[],
        metadata_areas=[],
    )
    
    # 1. Trova directory entry principale del gioco
    print(f"\n🔍 Ricerca directory entries...")
    game_id_bytes = game_id.encode('ascii')
    
    # Cerca la entry del gioco nell'area directory
    for offset in range(GAME_DIR_START, DATA_START, 64):
        if data[offset + 1:offset + 9] == game_id_bytes or data[offset + 2:offset + 10] == game_id_bytes:
            entry = parse_directory_entry(data, offset)
            if entry:
                print(f"   📁 Main entry: {entry.filename} @ 0x{offset:08x} cluster:{entry.first_cluster}")
                backup.directory_entries.append((offset, data[offset:offset + 64]))
                
                # 2. Segui catena FAT
                if entry.first_cluster > 0 and entry.first_cluster < 0xFFF0:
                    print(f"\n🔗 Seguendo catena FAT da cluster {entry.first_cluster}...")
                    
                    # Prova diversi offset FAT possibili
                    for fat_test in [0x130000, 0x150000, 0x160000, 0x1e0000]:
                        chain = follow_fat_chain(data, entry.first_cluster, fat_test)
                        if len(chain) > 1:
                            print(f"   FAT @ 0x{fat_test:08x}: catena = {chain[:10]}{'...' if len(chain) > 10 else ''}")
                            
                            # Salva FAT entries
                            for cluster in chain:
                                fat_offset = fat_test + (cluster * 2)
                                next_val = struct.unpack('<H', data[fat_offset:fat_offset + 2])[0]
                                backup.fat_entries.append((cluster, next_val))
                            break
    
    # 3. Estrai aree dati dove troviamo il game ID
    print(f"\n📊 Ricerca aree dati...")
    pos = 0
    areas_found = set()
    while True:
        pos = data.find(game_id_bytes, pos)
        if pos == -1:
            break
        
        area_start = (pos // 0x1000) * 0x1000
        if area_start not in areas_found:
            areas_found.add(area_start)
            area_size = 0x10000  # 64KB
            print(f"   📦 Data area: 0x{area_start:08x} - 0x{area_start + area_size:08x}")
            backup.data_clusters.append((area_start, data[area_start:area_start + area_size]))
        pos += 1
    
    # 4. Includi anche l'area save (0x460000) che contiene SaveMeta
    save_area_start = 0x460000
    save_area_size = 0x20000
    if (save_area_start, ) not in [(x[0],) for x in backup.data_clusters]:
        print(f"   📦 Save area: 0x{save_area_start:08x} - 0x{save_area_start + save_area_size:08x}")
        backup.data_clusters.append((save_area_start, data[save_area_start:save_area_start + save_area_size]))
    
    # 5. CRUCIALE: Includi le aree metadata/FAT
    print(f"\n📋 Aree metadata critiche...")
    critical_areas = [
        (0x00070000, 0x00010000, "Pre_Partition"),
        (0x00150000, 0x00010000, "FAT_Area_1"),
        (0x00170000, 0x00010000, "Dir_Metadata"),
        (0x001e0000, 0x00010000, "FAT_Area_2"),
        (0x00310000, 0x00010000, "Extended_Meta"),
    ]
    
    for start, size, name in critical_areas:
        print(f"   📋 {name}: 0x{start:08x}")
        backup.metadata_areas.append((start, data[start:start + size]))
    
    # Salva backup
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bin_file = backup_dir / f"{game_id}_chain_{timestamp}.bin"
    json_file = backup_dir / f"{game_id}_chain_{timestamp}.json"
    
    # Serializza dati binari
    all_data = b""
    areas_map = []
    
    for offset, raw in backup.directory_entries:
        areas_map.append({"type": "dir_entry", "offset": offset, "size": len(raw), "data_pos": len(all_data)})
        all_data += raw
    
    for offset, raw in backup.data_clusters:
        areas_map.append({"type": "data_cluster", "offset": offset, "size": len(raw), "data_pos": len(all_data)})
        all_data += raw
    
    for offset, raw in backup.metadata_areas:
        areas_map.append({"type": "metadata", "offset": offset, "size": len(raw), "data_pos": len(all_data)})
        all_data += raw
    
    with open(bin_file, 'wb') as f:
        f.write(all_data)
    
    metadata = {
        "game_id": game_id,
        "game_name": backup.game_name,
        "backup_date": datetime.now().isoformat(),
        "source": str(HDD_SOURCE),
        "total_size": len(all_data),
        "hash": hashlib.md5(all_data).hexdigest(),
        "fat_chain": backup.fat_entries,
        "areas": areas_map,
    }
    
    with open(json_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✅ Backup completato:")
    print(f"   File: {bin_file.name}")
    print(f"   Size: {len(all_data):,} bytes ({len(all_data) // 1024} KB)")
    print(f"   Dir entries: {len(backup.directory_entries)}")
    print(f"   Data areas: {len(backup.data_clusters)}")
    print(f"   Metadata areas: {len(backup.metadata_areas)}")
    
    return str(bin_file), str(json_file)


def restore_game_with_chain(bin_file: str, json_file: str) -> bool:
    """Ripristina un gioco dal backup con catena FAT."""
    print("=" * 70)
    print("💉 RIPRISTINO CON CATENA FAT")
    print("=" * 70)
    
    with open(json_file, 'r') as f:
        metadata = json.load(f)
    
    with open(bin_file, 'rb') as f:
        backup_data = f.read()
    
    print(f"\n🎮 Gioco: {metadata['game_name']} ({metadata['game_id']})")
    print(f"📅 Backup: {metadata['backup_date']}")
    
    # Verifica hash
    if hashlib.md5(backup_data).hexdigest() != metadata['hash']:
        print("❌ Hash non corrisponde!")
        return False
    print("✅ Hash verificato")
    
    # Ripristina
    print(f"\n📝 Scrittura in: {Path(HDD_TARGET).name}")
    
    with open(HDD_TARGET, 'r+b') as f:
        for area in metadata['areas']:
            offset = area['offset']
            size = area['size']
            data_pos = area['data_pos']
            area_type = area['type']
            
            area_data = backup_data[data_pos:data_pos + size]
            
            f.seek(offset)
            f.write(area_data)
            
            print(f"   {area_type}: 0x{offset:08x} ({size:,} bytes)")
        
        f.flush()
        os.fsync(f.fileno())
    
    print("\n✅ Ripristino completato!")
    return True


if __name__ == "__main__":
    import sys
    
    print("🎮 FATX CHAIN BACKUP/RESTORE")
    print("=" * 70)
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "backup" and len(sys.argv) > 2:
            backup_game_with_chain(sys.argv[2])
        elif cmd == "restore" and len(sys.argv) > 2:
            # Trova ultimo backup per quel game
            game_id = sys.argv[2]
            backup_dir = Path(BACKUP_DIR)
            backups = list(backup_dir.glob(f"{game_id}_chain_*.json"))
            if backups:
                latest = sorted(backups)[-1]
                restore_game_with_chain(str(latest.with_suffix('.bin')), str(latest))
    else:
        print("\nUso:")
        print("  python fatx_chain_restore.py backup <game_id>")
        print("  python fatx_chain_restore.py restore <game_id>")
        print("\nGame IDs:")
        for gid, name in GAMES.items():
            print(f"  {gid}: {name}")
