#!/usr/bin/env python3
"""
FATX ANALYZER - Analizza la struttura del filesystem FATX dell'HDD Xbox

Struttura FATX:
- Header: Magic "FATX" + metadata
- FAT: File Allocation Table  
- Root Directory: Entry di 64 bytes per file/cartella
- File Area: Dati effettivi
"""

import os
import struct
from pathlib import Path

# Config
HDD_PATH = r"D:\xemu\bk\xbox_hdd2.qcow2"

# Offsets conosciuti
FATX_PARTITIONS = {
    'FATX_1': 0x00160000,  # Boot FATX
    'FATX_2': 0x001f0000,  # System FATX
    'FATX_3': 0x00280000,  # Cache FATX
}


def read_fatx_header(data, offset):
    """Legge l'header FATX (primi 4096 bytes della partizione)."""
    header = data[offset:offset+4096]
    
    result = {
        'offset': offset,
        'magic': header[0:4].decode('ascii', errors='replace'),
        'volume_id': struct.unpack('<I', header[4:8])[0],
        'cluster_size_sectors': struct.unpack('<I', header[8:12])[0],
        'fat_copies': struct.unpack('<I', header[12:16])[0],
    }
    
    # Cluster size in bytes (sectors * 512)
    result['cluster_size_bytes'] = result['cluster_size_sectors'] * 512
    
    return result


def read_directory_entry(data, offset):
    """Legge una singola directory entry (64 bytes)."""
    entry_data = data[offset:offset+64]
    
    if len(entry_data) < 64:
        return None
    
    # Struttura directory entry
    filename_size = entry_data[0]
    
    # 0xFF o 0x00 significa entry vuota/eliminata
    if filename_size == 0xFF or filename_size == 0x00:
        return None
    
    if filename_size > 42:
        filename_size = 42
    
    try:
        filename = entry_data[1:1+filename_size].decode('ascii', errors='replace')
    except:
        filename = "<invalid>"
    
    attributes = entry_data[43]
    first_cluster = struct.unpack('<I', entry_data[44:48])[0]
    file_size = struct.unpack('<I', entry_data[48:52])[0]
    
    # Timestamp (creation)
    create_time = struct.unpack('<H', entry_data[52:54])[0]
    create_date = struct.unpack('<H', entry_data[54:56])[0]
    
    # Timestamp (last write)
    write_time = struct.unpack('<H', entry_data[56:58])[0]
    write_date = struct.unpack('<H', entry_data[58:60])[0]
    
    # Timestamp (last access)
    access_time = struct.unpack('<H', entry_data[60:62])[0]
    access_date = struct.unpack('<H', entry_data[62:64])[0]
    
    is_directory = bool(attributes & 0x10)
    
    return {
        'offset': offset,
        'filename_size': filename_size,
        'filename': filename,
        'attributes': attributes,
        'is_directory': is_directory,
        'first_cluster': first_cluster,
        'file_size': file_size,
        'create_date': create_date,
        'create_time': create_time,
        'write_date': write_date,
        'write_time': write_time,
    }


def decode_fatx_date(date_val):
    """Decodifica data FATX in formato leggibile."""
    if date_val == 0:
        return "N/A"
    
    year = ((date_val >> 9) & 0x7F) + 1980
    month = (date_val >> 5) & 0x0F
    day = date_val & 0x1F
    
    return f"{year}-{month:02d}-{day:02d}"


def scan_for_directory_entries(data, start_offset, max_entries=1000):
    """Scansiona un'area per trovare directory entries."""
    entries = []
    
    for i in range(max_entries):
        offset = start_offset + (i * 64)
        
        if offset + 64 > len(data):
            break
        
        entry = read_directory_entry(data, offset)
        if entry:
            entries.append(entry)
    
    return entries


def find_game_entries(entries, game_id):
    """Trova le entry relative a un gioco specifico."""
    game_entries = []
    
    for entry in entries:
        # Cerca l'ID del gioco nel filename
        if game_id.lower() in entry['filename'].lower():
            game_entries.append(entry)
    
    return game_entries


def main():
    print("=" * 70)
    print("🔍 FATX FILESYSTEM ANALYZER")
    print("=" * 70)
    
    print(f"\n📁 HDD: {Path(HDD_PATH).name}")
    print(f"   Size: {os.path.getsize(HDD_PATH):,} bytes")
    
    # Leggi tutto l'HDD
    print("\n⏳ Lettura HDD...")
    with open(HDD_PATH, 'rb') as f:
        data = f.read()
    
    # Analizza partizioni FATX
    print("\n📊 PARTIZIONI FATX:")
    for name, offset in FATX_PARTITIONS.items():
        # Verifica magic "FATX"
        magic = data[offset:offset+4]
        if magic == b'FATX':
            header = read_fatx_header(data, offset)
            print(f"\n  {name} @ 0x{offset:08x}")
            print(f"    Magic: {header['magic']}")
            print(f"    Volume ID: 0x{header['volume_id']:08x}")
            print(f"    Cluster size: {header['cluster_size_bytes']:,} bytes")
        else:
            print(f"\n  {name} @ 0x{offset:08x}: NOT FATX (magic: {magic})")
    
    # Cerca directory entries nell'area dei save
    # L'area dei save sembra essere intorno a 0x440000
    print("\n📂 DIRECTORY ENTRIES (Area Save 0x440000):")
    
    save_area_start = 0x440000
    entries = scan_for_directory_entries(data, save_area_start, max_entries=500)
    
    if entries:
        print(f"   Trovate {len(entries)} entry:")
        for entry in entries[:20]:  # Prime 20
            date_str = decode_fatx_date(entry['write_date'])
            type_str = "DIR" if entry['is_directory'] else "FILE"
            print(f"   0x{entry['offset']:08x}: [{type_str}] {entry['filename']:<42} "
                  f"Size: {entry['file_size']:>10,} Cluster: {entry['first_cluster']}")
    else:
        print("   Nessuna entry trovata in questa area")
    
    # Cerca pattern di giochi conosciuti
    print("\n🎮 RICERCA GIOCHI:")
    
    games = {
        '4c410015': 'Mercenaries',
        '5345000f': 'ToeJam & Earl III',
    }
    
    for game_id, game_name in games.items():
        print(f"\n   {game_name} ({game_id}):")
        
        # Cerca l'ID nel file
        id_bytes = game_id.encode('ascii')
        pos = 0
        positions = []
        while True:
            pos = data.find(id_bytes, pos)
            if pos == -1:
                break
            positions.append(pos)
            pos += 1
        
        if positions:
            print(f"     Trovato in {len(positions)} posizioni:")
            for p in positions[:5]:
                # Mostra contesto
                context = data[p-16:p+48]
                # Cerca stringhe leggibili
                try:
                    context_str = context.decode('ascii', errors='replace')
                except:
                    context_str = ""
                print(f"       0x{p:08x}")
        else:
            print(f"     NON TROVATO")
    
    # Cerca UDATA e TDATA (marker directory Xbox)
    print("\n📁 MARKER DIRECTORY XBOX:")
    for marker in [b'UDATA', b'TDATA']:
        pos = data.find(marker)
        if pos != -1:
            print(f"   {marker.decode()}: 0x{pos:08x}")
            # Mostra area intorno
            area = data[pos-32:pos+64]
            # Cerca entry di directory
            entries = scan_for_directory_entries(data, pos - 64, max_entries=10)
            for e in entries:
                print(f"     Entry: {e['filename']}")


if __name__ == "__main__":
    main()
