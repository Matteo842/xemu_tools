#!/usr/bin/env python3
"""
BACKUP SPECIFICO per ToeJam & Earl III

Questo script crea un backup che include TUTTE le aree differenti
tra source e target, identificate tramite diff_complete.py

Game: ToeJam & Earl III (5345000f)
"""

import struct
import json
import hashlib
from datetime import datetime
from pathlib import Path

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd3.qcow2"
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"
BACKUP_DIR = r"d:\GitHub\xemu_tools\surgical_backups"

# Aree identificate da diff_complete.py per ToeJam
TOEJAM_AREAS = [
    # (offset, size, description)
    (0x00050000, 0x1000, "Header/counter"),
    (0x00160000, 0x10000, "FAT16 area"),
    (0x00170000, 0x10000, "Directory TEMP_SAVE"),
    (0x0f730000, 0x10000, "Save slot 14C78A5E3BB8"),
    (0x118f0000, 0x10000, "SaveMeta.xbx area"),
    (0x2a990000, 0x10000, "Save data"),
    # Aggiungo anche l'area cluster originale del gioco
    (0x00443000 + (40-2)*16384, 107*16384, "Game folder cluster 40-146"),
]

def backup_toejam():
    print("=" * 70)
    print("BACKUP SPECIFICO: ToeJam & Earl III (5345000f)")
    print("=" * 70)
    
    print(f"\nLettura: {Path(HDD_SOURCE).name}")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    print(f"Size: {len(data):,} bytes")
    
    # Crea backup con tutte le aree
    backup_data = b"XBSV"  # Magic
    backup_data += struct.pack('<I', 99)  # Versione 99 = custom areas
    backup_data += b"5345000f"  # Game ID
    
    # Numero aree
    backup_data += struct.pack('<I', len(TOEJAM_AREAS))
    
    print(f"\nAree da includere: {len(TOEJAM_AREAS)}")
    
    for offset, size, desc in TOEJAM_AREAS:
        # Verifica che l'area sia nel range del file
        if offset + size > len(data):
            actual_size = max(0, len(data) - offset)
            print(f"  [!] {desc}: 0x{offset:08x} - troncato a {actual_size} bytes")
            size = actual_size
        else:
            print(f"  {desc}: 0x{offset:08x} - {size:,} bytes")
        
        if size > 0:
            area_data = data[offset:offset + size]
            backup_data += struct.pack('<I', offset)
            backup_data += struct.pack('<I', size)
            backup_data += area_data
    
    # Salva
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"5345000f_custom_{timestamp}.bin"
    metadata_file = backup_dir / f"5345000f_custom_{timestamp}.json"
    
    with open(backup_file, 'wb') as f:
        f.write(backup_data)
    
    metadata = {
        "format": "XBSV",
        "version": 99,
        "game_id": "5345000f",
        "game_name": "ToeJam & Earl III",
        "backup_date": datetime.now().isoformat(),
        "source_hdd": str(HDD_SOURCE),
        "areas": [{"offset": o, "size": s, "desc": d} for o, s, d in TOEJAM_AREAS],
        "total_size": len(backup_data),
        "data_hash": hashlib.md5(backup_data).hexdigest(),
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nBackup completato!")
    print(f"  File: {backup_file.name}")
    print(f"  Size: {len(backup_data):,} bytes ({len(backup_data) // 1024:,} KB)")
    
    return str(backup_file), str(metadata_file)


def restore_toejam(backup_file: str, metadata_file: str):
    print("=" * 70)
    print("RESTORE SPECIFICO: ToeJam & Earl III")
    print("=" * 70)
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    with open(backup_file, 'rb') as f:
        backup_data = f.read()
    
    # Verifica hash
    if hashlib.md5(backup_data).hexdigest() != metadata['data_hash']:
        print("ERRORE: Hash non corrisponde!")
        return False
    print("Hash verificato OK")
    
    # Parse
    pos = 4 + 4 + 8  # Magic + version + game_id
    num_areas = struct.unpack('<I', backup_data[pos:pos+4])[0]
    pos += 4
    
    print(f"\nAree da ripristinare: {num_areas}")
    
    with open(HDD_TARGET, 'r+b') as f:
        for i in range(num_areas):
            offset = struct.unpack('<I', backup_data[pos:pos+4])[0]
            pos += 4
            size = struct.unpack('<I', backup_data[pos:pos+4])[0]
            pos += 4
            area_data = backup_data[pos:pos+size]
            pos += size
            
            f.seek(offset)
            f.write(area_data)
            print(f"  0x{offset:08x}: {size:,} bytes")
        
        f.flush()
    
    print("\nRestore completato!")
    return True


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "restore":
        # Trova ultimo backup
        backup_dir = Path(BACKUP_DIR)
        backups = list(backup_dir.glob("5345000f_custom_*.json"))
        if backups:
            latest = sorted(backups)[-1]
            restore_toejam(str(latest.with_suffix('.bin')), str(latest))
    else:
        backup_toejam()
