#!/usr/bin/env python3
"""
SINGLE GAME RESTORE - Ripristina un singolo gioco Xbox senza toccare gli altri

Strategia:
1. Trova le directory entries del gioco nel backup
2. Trova i dati del gioco nel backup  
3. Scrivi SOLO quelle entry e dati nell'HDD target
4. NON toccare le aree degli altri giochi
"""

import os
import struct
import json
import hashlib
from datetime import datetime
from pathlib import Path

# Config
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # Backup con saves
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"       # HDD da ripristinare
BACKUP_DIR = r"d:\GitHub\xemu_tools\game_backups"

# Game IDs
GAMES = {
    "4c410015": "Mercenaries",
    "5345000f": "ToeJam & Earl III",
}

# Directory entries conosciute (dai nostri test)
GAME_ENTRIES = {
    "4c410015": {
        "dir_entry_offset": 0x00447000,  # Entry principale del gioco
        "data_area_start": 0x0044b000,   # Inizio area dati
        "data_area_size": 0x30000,       # ~192KB
    },
    "5345000f": {
        "dir_entry_offset": 0x00447040,  # Entry principale del gioco
        "data_area_start": 0x14520000,   # Area dati ToeJam (dalle analisi)
        "data_area_size": 0x10000,       # ~64KB
    },
}


def find_game_entries_and_data(data: bytes, game_id: str) -> dict:
    """Trova tutte le entry e i dati relativi a un gioco."""
    print(f"\n🔍 Ricerca dati per: {GAMES.get(game_id, game_id)}")
    
    result = {
        "game_id": game_id,
        "game_name": GAMES.get(game_id, "Unknown"),
        "directory_entries": [],
        "data_areas": [],
    }
    
    game_id_bytes = game_id.encode('ascii')
    
    # Trova tutte le occorrenze del game ID
    pos = 0
    while True:
        pos = data.find(game_id_bytes, pos)
        if pos == -1:
            break
        
        # L'entry dovrebbe essere allineata a 64 bytes e iniziare 2 bytes prima
        entry_offset = (pos // 64) * 64
        if pos - entry_offset <= 8:  # Il game ID è vicino all'inizio dell'entry
            # Leggi l'entry
            entry_data = data[entry_offset:entry_offset + 64]
            filename_size = entry_data[0]
            
            if filename_size != 0xFF and filename_size != 0x00:
                result["directory_entries"].append({
                    "offset": entry_offset,
                    "size": 64,
                    "data": entry_data,
                })
                print(f"   Entry trovata: 0x{entry_offset:08x}")
        
        # Area dati intorno al game ID
        area_start = (pos // 0x1000) * 0x1000
        area_size = 0x10000  # 64KB default
        
        # Evita duplicati
        if not any(a["offset"] == area_start for a in result["data_areas"]):
            result["data_areas"].append({
                "offset": area_start,
                "size": area_size,
                "data": data[area_start:area_start + area_size],
            })
            print(f"   Area dati: 0x{area_start:08x} - 0x{area_start+area_size:08x}")
        
        pos += 1
    
    # Aggiungi area Save_Files (0x460000) che contiene SaveMeta, etc
    save_area_start = 0x00460000
    save_area_size = 0x20000
    
    # Verifica se contiene riferimenti al gioco
    save_area = data[save_area_start:save_area_start + save_area_size]
    if game_id_bytes in save_area or b"SaveMeta" in save_area:
        result["data_areas"].append({
            "offset": save_area_start,
            "size": save_area_size,
            "data": save_area,
        })
        print(f"   Save area: 0x{save_area_start:08x} - 0x{save_area_start+save_area_size:08x}")
    
    return result


def backup_single_game(game_id: str):
    """Crea backup dei dati di un singolo gioco."""
    print("=" * 60)
    print(f"📦 BACKUP SINGOLO GIOCO: {GAMES.get(game_id, game_id)}")
    print("=" * 60)
    
    # Leggi HDD sorgente
    print(f"\n📂 Lettura: {Path(HDD_SOURCE).name}")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    
    # Trova dati del gioco
    game_data = find_game_entries_and_data(data, game_id)
    
    # Crea directory backup
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{game_id}_{timestamp}.bin"
    metadata_file = backup_dir / f"{game_id}_{timestamp}.json"
    
    # Salva dati binari (tutte le aree)
    all_data = b""
    areas_info = []
    
    for entry in game_data["directory_entries"]:
        areas_info.append({
            "type": "directory_entry",
            "offset": entry["offset"],
            "size": entry["size"],
            "data_offset": len(all_data),
        })
        all_data += entry["data"]
    
    for area in game_data["data_areas"]:
        areas_info.append({
            "type": "data_area",
            "offset": area["offset"],
            "size": area["size"],
            "data_offset": len(all_data),
        })
        all_data += area["data"]
    
    with open(backup_file, 'wb') as f:
        f.write(all_data)
    
    # Salva metadata
    metadata = {
        "game_id": game_id,
        "game_name": game_data["game_name"],
        "backup_date": datetime.now().isoformat(),
        "source_hdd": str(HDD_SOURCE),
        "total_size": len(all_data),
        "data_hash": hashlib.md5(all_data).hexdigest(),
        "areas": areas_info,
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✅ Backup completato:")
    print(f"   File: {backup_file.name}")
    print(f"   Size: {len(all_data):,} bytes")
    print(f"   Aree: {len(areas_info)}")
    
    return str(backup_file), str(metadata_file)


def restore_single_game(backup_file: str, metadata_file: str):
    """Ripristina un singolo gioco dal backup."""
    print("=" * 60)
    print("💉 RIPRISTINO SINGOLO GIOCO")
    print("=" * 60)
    
    # Leggi metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    print(f"\n🎮 Gioco: {metadata['game_name']} ({metadata['game_id']})")
    print(f"📅 Backup: {metadata['backup_date']}")
    
    # Leggi dati backup
    with open(backup_file, 'rb') as f:
        backup_data = f.read()
    
    # Verifica hash
    actual_hash = hashlib.md5(backup_data).hexdigest()
    if actual_hash != metadata['data_hash']:
        print("❌ Hash non corrisponde! Backup corrotto?")
        return False
    
    print(f"✅ Hash verificato")
    
    # Apri HDD target per scrittura
    print(f"\n📝 Scrittura in: {Path(HDD_TARGET).name}")
    
    with open(HDD_TARGET, 'r+b') as f:
        for area in metadata['areas']:
            offset = area['offset']
            size = area['size']
            data_offset = area['data_offset']
            area_type = area['type']
            
            # Estrai dati dal backup
            area_data = backup_data[data_offset:data_offset + size]
            
            # Scrivi nell'HDD
            f.seek(offset)
            f.write(area_data)
            
            print(f"   {area_type}: 0x{offset:08x} ({size:,} bytes)")
        
        f.flush()
        os.fsync(f.fileno())
    
    print(f"\n✅ Ripristino completato!")
    return True


def list_backups():
    """Elenca i backup disponibili."""
    backup_dir = Path(BACKUP_DIR)
    if not backup_dir.exists():
        print("❌ Nessun backup trovato")
        return []
    
    backups = list(backup_dir.glob("*.json"))
    
    print("\n📋 BACKUP DISPONIBILI:")
    for i, meta_file in enumerate(backups):
        with open(meta_file) as f:
            meta = json.load(f)
        print(f"  {i+1}. {meta['game_name']} ({meta['game_id']}) - {meta['backup_date']}")
    
    return backups


def main():
    print("=" * 60)
    print("🎮 SINGLE GAME BACKUP/RESTORE")
    print("=" * 60)
    
    while True:
        print("\n📋 MENU:")
        print("1. 📦 Backup singolo gioco")
        print("2. 💉 Ripristina singolo gioco")
        print("3. 📋 Lista backup")
        print("4. 🔧 Ripristina TUTTO (metodo classico)")
        print("0. ❌ Esci")
        
        choice = input("\nScelta: ").strip()
        
        if choice == "1":
            print("\nGiochi disponibili:")
            for gid, name in GAMES.items():
                print(f"  {gid}: {name}")
            game_id = input("ID gioco: ").strip().lower()
            if game_id in GAMES:
                backup_single_game(game_id)
            else:
                print("❌ ID non valido")
        
        elif choice == "2":
            backups = list_backups()
            if backups:
                idx = int(input("Numero backup: ")) - 1
                meta_file = backups[idx]
                bin_file = meta_file.with_suffix('.bin')
                restore_single_game(str(bin_file), str(meta_file))
        
        elif choice == "3":
            list_backups()
        
        elif choice == "4":
            from restore_filesystem_areas import restore_filesystem_areas
            restore_filesystem_areas()
        
        elif choice == "0":
            break


if __name__ == "__main__":
    main()
