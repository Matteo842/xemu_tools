#!/usr/bin/env python3
"""
SINGLE GAME MERGER - Ripristina UN SOLO gioco Xbox con merge chirurgico della FAT

Questo script:
1. Legge le catene FAT dal backup funzionante
2. Identifica quali cluster appartengono al gioco da ripristinare
3. Copia SOLO quei cluster e le relative entry FAT
4. NON tocca gli altri giochi

IMPORTANTE: Usa merge chirurgico, non sovrascrittura!
"""

import os
import struct
import json
import hashlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple, Set

# =============================================================================
# CONFIGURAZIONE
# =============================================================================

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # Backup funzionante (SOLO LETTURA)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"       # HDD da modificare
BACKUP_DIR = r"d:\GitHub\xemu_tools\surgical_backups"

# Struttura Xbox FATX (da analisi precedente)
FAT_TABLE_OFFSET = 0x00161000  # FAT16 Table della partizione E
FAT32_TABLE_OFFSET = 0x00311000  # FAT32 Table (seconda copia/altra partizione)
CLUSTER_SIZE = 16384           # 16KB
DATA_START = 0x00443000        # Inizio area dati (VERIFICATO!)

# Directory entries
GAME_DIR_OFFSET = 0x00447000   # Directory che contiene i game ID
ENTRY_SIZE = 64                # Ogni directory entry è 64 bytes

# Giochi conosciuti - ora senza metadata_areas hardcoded!
# Gli offset FAT32 vengono calcolati dinamicamente dalla FAT chain
GAMES = {
    "4c410015": {
        "name": "Mercenaries",
        "dir_entry_offset": 0x00447000,
        "first_cluster": 4,
    },
    "5345000f": {
        "name": "ToeJam & Earl III", 
        "dir_entry_offset": 0x00447040,
        "first_cluster": 39,
    },
}

def calculate_fat32_offsets(fat_chain: list) -> list:
    """
    Calcola gli offset FAT32 per ogni cluster nella catena.
    Formula: FAT32_TABLE_OFFSET + (cluster * 4)
    """
    offsets = []
    for cluster in fat_chain:
        offset = FAT32_TABLE_OFFSET + (cluster * 4)
        offsets.append((offset, 4))  # (offset, size)
    return offsets

# =============================================================================
# FUNZIONI FAT
# =============================================================================

def read_fat_entry(data: bytes, fat_start: int, cluster: int) -> int:
    """Legge una entry FAT16 (2 bytes)."""
    offset = fat_start + (cluster * 2)
    if offset + 2 > len(data):
        return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_fat_chain(data: bytes, fat_start: int, first_cluster: int, max_length: int = 10000) -> List[int]:
    """Costruisce la catena FAT partendo dal primo cluster."""
    chain = [first_cluster]
    current = first_cluster
    
    for _ in range(max_length):
        next_cluster = read_fat_entry(data, fat_start, current)
        
        # End of chain (FAT16)
        if next_cluster >= 0xFFF8:
            break
        if next_cluster == 0x0000:
            break
        
        chain.append(next_cluster)
        current = next_cluster
    
    return chain

def cluster_to_offset(cluster: int, data_start: int = DATA_START) -> int:
    """Converte numero cluster in offset fisico."""
    # Cluster 0 e 1 sono riservati
    return data_start + ((cluster - 2) * CLUSTER_SIZE)

# =============================================================================
# BACKUP SINGOLO GIOCO
# =============================================================================

def backup_single_game(game_id: str) -> Tuple[str, str]:
    """
    Crea un backup chirurgico di un singolo gioco.
    Salva: directory entry, FAT entries, cluster dati.
    """
    print("=" * 70)
    print(f"📦 BACKUP CHIRURGICO: {GAMES[game_id]['name']}")
    print("=" * 70)
    
    if game_id not in GAMES:
        print(f"❌ Gioco non conosciuto: {game_id}")
        return None, None
    
    game = GAMES[game_id]
    
    # Leggi HDD sorgente
    print(f"\n📂 Lettura: {Path(HDD_SOURCE).name}")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    
    # --- 1. DIRECTORY ENTRY ---
    print(f"\n📋 1. Directory Entry")
    dir_entry = data[game['dir_entry_offset']:game['dir_entry_offset'] + ENTRY_SIZE]
    print(f"   Offset: 0x{game['dir_entry_offset']:08x}")
    print(f"   Size: {len(dir_entry)} bytes")
    
    # --- 2. FAT CHAIN ---
    print(f"\n📋 2. FAT Chain")
    fat_chain = get_fat_chain(data, FAT_TABLE_OFFSET, game['first_cluster'])
    print(f"   First cluster: {game['first_cluster']}")
    print(f"   Chain length: {len(fat_chain)}")
    print(f"   Clusters: {fat_chain[:10]}{'...' if len(fat_chain) > 10 else ''}")
    
    # Estrai FAT entries (cluster_num, fat_value)
    fat_entries = []
    for cluster in fat_chain:
        fat_value = read_fat_entry(data, FAT_TABLE_OFFSET, cluster)
        fat_entries.append((cluster, fat_value))
    print(f"   FAT entries salvate: {len(fat_entries)}")
    
    # --- 3. DATA CLUSTERS ---
    print(f"\n📋 3. Data Clusters")
    data_chunks = []
    for cluster in fat_chain:
        offset = cluster_to_offset(cluster)
        if offset + CLUSTER_SIZE <= len(data):
            chunk = data[offset:offset + CLUSTER_SIZE]
            data_chunks.append((cluster, offset, chunk))
    print(f"   Cluster estratti: {len(data_chunks)}")
    total_data_size = sum(len(c[2]) for c in data_chunks)
    print(f"   Dimensione totale: {total_data_size:,} bytes ({total_data_size // 1024} KB)")
    
    # --- 4. AREE EXTRA (directory UDATA entry, SaveMeta, etc) ---
    print(f"\n📋 4. Aree Extra")
    extra_areas = []
    
    # Cerca il game ID in altre aree
    game_id_bytes = game_id.encode('ascii')
    pos = 0
    found_areas = set()
    while True:
        pos = data.find(game_id_bytes, pos)
        if pos == -1:
            break
        area_start = (pos // 0x1000) * 0x1000  # Allinea a 4KB
        if area_start not in found_areas and area_start not in [c[1] for c in data_chunks]:
            # Non è già un cluster dati
            found_areas.add(area_start)
            area_data = data[area_start:area_start + 0x1000]
            extra_areas.append((area_start, area_data))
            print(f"   Extra area: 0x{area_start:08x} (4KB)")
        pos += 1
    
    # --- 5. FAT32 ENTRIES (calcolate dinamicamente!) ---
    print(f"\n📋 5. FAT32 Entries (calcolo dinamico)")
    
    # Calcola offset FAT32 per ogni cluster nella catena
    fat32_entries = []
    for cluster in fat_chain:
        offset = FAT32_TABLE_OFFSET + (cluster * 4)
        if offset + 4 <= len(data):
            entry_data = data[offset:offset + 4]
            fat32_entries.append((cluster, offset, entry_data))
    
    print(f"   Calcolati {len(fat32_entries)} offset FAT32 dalla catena")
    if fat32_entries:
        first_offset = fat32_entries[0][1]
        last_offset = fat32_entries[-1][1]
        print(f"   Range: 0x{first_offset:08x} - 0x{last_offset:08x}")
    
    # --- SALVA BACKUP ---
    print(f"\n💾 Salvataggio backup...")
    
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{game_id}_surgical_{timestamp}.bin"
    metadata_file = backup_dir / f"{game_id}_surgical_{timestamp}.json"
    
    # Serializza dati binari
    all_data = b""
    
    # Header custom (magic + versione)
    all_data += b"XBSV"  # Xbox Save Version
    all_data += struct.pack('<I', 3)  # Versione 3 (con FAT32 dinamico)
    
    # Directory entry
    all_data += struct.pack('<I', len(dir_entry))
    all_data += dir_entry
    
    # FAT entries
    all_data += struct.pack('<I', len(fat_entries))
    for cluster, fat_val in fat_entries:
        all_data += struct.pack('<HH', cluster, fat_val)
    
    # Data chunks
    all_data += struct.pack('<I', len(data_chunks))
    for cluster, offset, chunk_data in data_chunks:
        all_data += struct.pack('<II', cluster, offset)
        all_data += struct.pack('<I', len(chunk_data))
        all_data += chunk_data
    
    # Extra areas
    all_data += struct.pack('<I', len(extra_areas))
    for offset, area_data in extra_areas:
        all_data += struct.pack('<I', offset)
        all_data += struct.pack('<I', len(area_data))
        all_data += area_data
    
    # FAT32 entries (NUOVO in v3 - calcolato dinamicamente!)
    all_data += struct.pack('<I', len(fat32_entries))
    for cluster, offset, entry_data in fat32_entries:
        all_data += struct.pack('<II', cluster, offset)
        all_data += entry_data  # 4 bytes
    
    with open(backup_file, 'wb') as f:
        f.write(all_data)
    
    # Metadata JSON
    metadata = {
        "format": "XBSV",
        "version": 3,
        "game_id": game_id,
        "game_name": game['name'],
        "backup_date": datetime.now().isoformat(),
        "source_hdd": str(HDD_SOURCE),
        "dir_entry_offset": game['dir_entry_offset'],
        "first_cluster": game['first_cluster'],
        "fat_chain_length": len(fat_chain),
        "fat_chain": fat_chain[:100],  # Primi 100 per debug
        "data_clusters": len(data_chunks),
        "extra_areas": len(extra_areas),
        "fat32_entries": len(fat32_entries),
        "total_size": len(all_data),
        "data_hash": hashlib.md5(all_data).hexdigest(),
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✅ Backup completato!")
    print(f"   File: {backup_file.name}")
    print(f"   Size: {len(all_data):,} bytes ({len(all_data) // 1024} KB)")
    print(f"   Metadata: {metadata_file.name}")
    
    return str(backup_file), str(metadata_file)

# =============================================================================
# RESTORE SINGOLO GIOCO (MERGE CHIRURGICO)
# =============================================================================

def restore_single_game(backup_file: str, metadata_file: str) -> bool:
    """
    Ripristina un singolo gioco con MERGE chirurgico.
    NON sovrascrive le aree degli altri giochi!
    """
    print("=" * 70)
    print("💉 RESTORE CHIRURGICO (MERGE)")
    print("=" * 70)
    
    # Leggi metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    print(f"\n🎮 Gioco: {metadata['game_name']} ({metadata['game_id']})")
    print(f"📅 Backup: {metadata['backup_date']}")
    
    # Leggi backup
    with open(backup_file, 'rb') as f:
        backup_data = f.read()
    
    # Verifica hash
    actual_hash = hashlib.md5(backup_data).hexdigest()
    if actual_hash != metadata['data_hash']:
        print("❌ Hash non corrisponde! Backup corrotto?")
        return False
    print("✅ Hash verificato")
    
    # Parsa backup
    pos = 0
    
    # Header
    magic = backup_data[pos:pos + 4]
    pos += 4
    if magic != b"XBSV":
        print(f"❌ Magic non valido: {magic}")
        return False
    
    version = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    print(f"   Versione formato: {version}")
    
    # Directory entry
    dir_entry_size = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    dir_entry = backup_data[pos:pos + dir_entry_size]
    pos += dir_entry_size
    print(f"   Directory entry: {dir_entry_size} bytes")
    
    # FAT entries
    fat_entries_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat_entries = []
    for _ in range(fat_entries_count):
        cluster, fat_val = struct.unpack('<HH', backup_data[pos:pos + 4])
        fat_entries.append((cluster, fat_val))
        pos += 4
    print(f"   FAT entries: {fat_entries_count}")
    
    # Data chunks
    data_chunks_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    data_chunks = []
    for _ in range(data_chunks_count):
        cluster, offset = struct.unpack('<II', backup_data[pos:pos + 8])
        pos += 8
        chunk_size = struct.unpack('<I', backup_data[pos:pos + 4])[0]
        pos += 4
        chunk_data = backup_data[pos:pos + chunk_size]
        pos += chunk_size
        data_chunks.append((cluster, offset, chunk_data))
    print(f"   Data clusters: {data_chunks_count}")
    
    # Extra areas
    extra_areas_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    extra_areas = []
    for _ in range(extra_areas_count):
        offset = struct.unpack('<I', backup_data[pos:pos + 4])[0]
        pos += 4
        area_size = struct.unpack('<I', backup_data[pos:pos + 4])[0]
        pos += 4
        area_data = backup_data[pos:pos + area_size]
        pos += area_size
        extra_areas.append((offset, area_data))
    print(f"   Extra areas: {extra_areas_count}")
    
    # FAT32 entries (versione 3) o metadata_areas (versione 2)
    fat32_entries = []
    legacy_metadata_areas = []  # Per V2
    
    if version >= 3:
        fat32_entries_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
        pos += 4
        for _ in range(fat32_entries_count):
            cluster, offset = struct.unpack('<II', backup_data[pos:pos + 8])
            pos += 8
            entry_data = backup_data[pos:pos + 4]
            pos += 4
            fat32_entries.append((cluster, offset, entry_data))
        print(f"   FAT32 entries: {fat32_entries_count} (dinamico)")
    elif version >= 2:
        # Compatibilità con versione 2 (hardcoded) - USA LISTA SEPARATA!
        metadata_areas_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
        pos += 4
        for _ in range(metadata_areas_count):
            offset = struct.unpack('<I', backup_data[pos:pos + 4])[0]
            pos += 4
            area_size = struct.unpack('<I', backup_data[pos:pos + 4])[0]
            pos += 4
            area_data = backup_data[pos:pos + area_size]
            pos += area_size
            # Mantieni TUTTI i dati, non troncare a 4 bytes!
            legacy_metadata_areas.append((offset, area_size, area_data))
        print(f"   Metadata areas (legacy v2): {metadata_areas_count}")
    
    # --- MERGE CHIRURGICO ---
    print(f"\n🔧 MERGE CHIRURGICO in {Path(HDD_TARGET).name}")
    
    with open(HDD_TARGET, 'r+b') as f:
        
        # 1. Scrivi directory entry
        print(f"\n   1. Directory entry @ 0x{metadata['dir_entry_offset']:08x}")
        f.seek(metadata['dir_entry_offset'])
        f.write(dir_entry)
        
        # 2. Scrivi FAT16 entries (MERGE: solo queste, non toccare le altre!)
        print(f"\n   2. FAT16 entries ({len(fat_entries)} entries)")
        for cluster, fat_val in fat_entries:
            fat_offset = FAT_TABLE_OFFSET + (cluster * 2)
            f.seek(fat_offset)
            f.write(struct.pack('<H', fat_val))
        print(f"      Scritte {len(fat_entries)} FAT16 entries")
        
        # 3. Scrivi data clusters
        print(f"\n   3. Data clusters ({len(data_chunks)} chunks)")
        for cluster, offset, chunk_data in data_chunks:
            f.seek(offset)
            f.write(chunk_data)
        total_data = sum(len(c[2]) for c in data_chunks)
        print(f"      Scritti {total_data:,} bytes di dati")
        
        # 4. Scrivi extra areas
        if extra_areas:
            print(f"\n   4. Extra areas ({len(extra_areas)} aree)")
            for offset, area_data in extra_areas:
                f.seek(offset)
                f.write(area_data)
                print(f"      0x{offset:08x}: {len(area_data)} bytes")
        
        # 5. Scrivi FAT32 entries (V3) o legacy metadata areas (V2)
        if fat32_entries:
            print(f"\n   5. FAT32 entries ({len(fat32_entries)} entries) 🔑")
            written = 0
            for cluster, offset, entry_data in fat32_entries:
                f.seek(offset)
                f.write(entry_data)
                written += 1
            print(f"      Scritte {written} FAT32 entries")
        
        # 5b. Scrivi legacy metadata areas (V2) - CRITICO!
        if legacy_metadata_areas:
            print(f"\n   5. Legacy metadata areas ({len(legacy_metadata_areas)} aree) 🔑")
            for offset, size, area_data in legacy_metadata_areas:
                f.seek(offset)
                f.write(area_data)
                print(f"      0x{offset:08x}: {size} bytes")
        
        # Forza scrittura
        f.flush()
        os.fsync(f.fileno())
    
    print(f"\n✅ RESTORE CHIRURGICO COMPLETATO!")
    print(f"   Gli altri giochi NON sono stati toccati.")
    print(f"\n🎮 Ora puoi avviare xemu e verificare!")
    
    return True

# =============================================================================
# MAIN
# =============================================================================

def list_surgical_backups():
    """Lista i backup chirurgici disponibili."""
    backup_dir = Path(BACKUP_DIR)
    if not backup_dir.exists():
        print("❌ Nessun backup trovato")
        return []
    
    backups = list(backup_dir.glob("*_surgical_*.json"))
    
    print("\n📋 BACKUP CHIRURGICI DISPONIBILI:")
    for i, meta_file in enumerate(backups):
        with open(meta_file) as f:
            meta = json.load(f)
        print(f"  {i+1}. {meta['game_name']} ({meta['game_id']}) - {meta['backup_date']}")
    
    return backups

def main():
    print("=" * 70)
    print("🎮 SINGLE GAME MERGER - Backup/Restore Chirurgico")
    print("=" * 70)
    
    while True:
        print("\n📋 MENU:")
        print("1. 📦 Backup chirurgico singolo gioco")
        print("2. 💉 Restore chirurgico (merge)")
        print("3. 📋 Lista backup disponibili")
        print("4. 🔧 Restore TUTTO (metodo classico)")
        print("0. ❌ Esci")
        
        choice = input("\nScelta: ").strip()
        
        if choice == "1":
            print("\nGiochi disponibili:")
            for gid, info in GAMES.items():
                print(f"  {gid}: {info['name']}")
            game_id = input("ID gioco da backuppare: ").strip().lower()
            if game_id in GAMES:
                backup_single_game(game_id)
            else:
                print("❌ ID non valido")
        
        elif choice == "2":
            backups = list_surgical_backups()
            if backups:
                try:
                    idx = int(input("Numero backup da ripristinare: ")) - 1
                    if 0 <= idx < len(backups):
                        meta_file = backups[idx]
                        bin_file = meta_file.with_suffix('.bin')
                        restore_single_game(str(bin_file), str(meta_file))
                    else:
                        print("❌ Numero non valido")
                except ValueError:
                    print("❌ Input non valido")
        
        elif choice == "3":
            list_surgical_backups()
        
        elif choice == "4":
            # Importa il vecchio metodo
            try:
                from restore_filesystem_areas import restore_filesystem_areas
                restore_filesystem_areas()
            except ImportError:
                print("❌ Script restore_filesystem_areas.py non trovato")
        
        elif choice == "0":
            break

if __name__ == "__main__":
    main()
