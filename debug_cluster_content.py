#!/usr/bin/env python3
"""
DEBUG - Cosa c'è realmente nei cluster del gioco?
SOLO LETTURA!
"""

import struct
from pathlib import Path

# SOLO LETTURA!
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"

# Costanti
FAT_TABLE_OFFSET = 0x00161000
FAT32_TABLE_OFFSET = 0x00311000
CLUSTER_SIZE = 16384
DATA_START = 0x00443000

def cluster_to_offset(cluster: int) -> int:
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)

def hex_dump(data: bytes, offset: int, length: int = 256) -> None:
    """Stampa hex dump con ASCII."""
    for i in range(0, min(len(data), length), 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f"  0x{offset + i:08x}: {hex_part:<48} {ascii_part}")

print("=" * 70)
print("🔍 DEBUG CLUSTER CONTENT")
print("=" * 70)

with open(HDD_SOURCE, 'rb') as f:
    data = f.read()

print(f"File size: {len(data):,} bytes")

# Game info
games = {
    "4c410015": {"name": "Mercenaries", "dir_entry_offset": 0x00447000, "first_cluster": 4},
    "5345000f": {"name": "ToeJam & Earl III", "dir_entry_offset": 0x00447040, "first_cluster": 39},
}

for game_id, game in games.items():
    print(f"\n{'='*70}")
    print(f"🎮 {game['name']} ({game_id})")
    print(f"{'='*70}")
    
    # 1. Directory entry del gioco stesso (nel parent UDATA)
    print(f"\n📋 1. DIRECTORY ENTRY @ 0x{game['dir_entry_offset']:08x}")
    dir_entry = data[game['dir_entry_offset']:game['dir_entry_offset'] + 64]
    hex_dump(dir_entry, game['dir_entry_offset'], 64)
    
    # Parse directory entry
    filename_len = dir_entry[0]
    attributes = dir_entry[1]
    filename = dir_entry[2:2+min(filename_len, 42)].decode('ascii', errors='replace')
    first_cluster = struct.unpack('<I', dir_entry[44:48])[0]
    file_size = struct.unpack('<I', dir_entry[48:52])[0]
    
    print(f"\n   Parsed:")
    print(f"   - Filename: '{filename}' (len={filename_len})")
    print(f"   - Attributes: 0x{attributes:02x} ({'DIR' if attributes & 0x10 else 'FILE'})")
    print(f"   - First cluster: {first_cluster}")
    print(f"   - Size: {file_size:,}")
    
    # 2. Contenuto del primo cluster (dovrebbe contenere directory entries interne)
    cluster_offset = cluster_to_offset(game['first_cluster'])
    print(f"\n📋 2. PRIMO CLUSTER ({game['first_cluster']}) @ 0x{cluster_offset:08x}")
    cluster_data = data[cluster_offset:cluster_offset + 512]  # Solo primi 512 bytes
    hex_dump(cluster_data, cluster_offset, 256)
    
    # 3. Proviamo a parsare le prime directory entries
    print(f"\n📋 3. PARSE PRIME DIRECTORY ENTRIES (nel cluster {game['first_cluster']})")
    
    for i in range(4):  # Prime 4 entry
        entry_offset = cluster_offset + (i * 64)
        entry = data[entry_offset:entry_offset + 64]
        
        fn_len = entry[0]
        if fn_len == 0xFF or fn_len == 0x00:
            print(f"   Entry {i}: VUOTA/FINE (len=0x{fn_len:02x})")
            continue
        if fn_len == 0xE5:
            print(f"   Entry {i}: DELETED")
            continue
            
        attrs = entry[1]
        fn = entry[2:2+min(fn_len, 42)]
        fc = struct.unpack('<I', entry[44:48])[0]
        fs = struct.unpack('<I', entry[48:52])[0]
        
        try:
            fn_str = fn.decode('ascii', errors='replace')
        except:
            fn_str = "<binary>"
        
        print(f"   Entry {i}: '{fn_str}' attr=0x{attrs:02x} cluster={fc} size={fs:,}")

# 4. Verifica cosa c'è a 0x31102C (l'offset critico che sappiamo funziona)
print(f"\n{'='*70}")
print("📋 4. COSA C'È A 0x31102C (OFFSET CRITICO)")
print(f"{'='*70}")

critical_offset = 0x0031102C
critical_data = data[critical_offset:critical_offset + 128]
hex_dump(critical_data, critical_offset, 128)

# Calcola a quale cluster corrisponde
cluster_num = (critical_offset - FAT32_TABLE_OFFSET) // 4
print(f"\n   Questo offset corrisponde al cluster {cluster_num} nella FAT32")
print(f"   (0x{FAT32_TABLE_OFFSET:08x} + {cluster_num} * 4 = 0x{critical_offset:08x})")

# 5. Verifica cosa c'è a 0x463040 (altro offset critico)
print(f"\n{'='*70}")
print("📋 5. COSA C'È A 0x463040 (SAVE ENTRY)")
print(f"{'='*70}")

save_offset = 0x00463040
save_data = data[save_offset:save_offset + 128]
hex_dump(save_data, save_offset, 128)

# Calcola a quale cluster corrisponde
save_cluster = (save_offset - DATA_START) // CLUSTER_SIZE + 2
print(f"\n   Questo offset è nel cluster {save_cluster}")
print(f"   Offset dentro cluster: 0x{(save_offset - cluster_to_offset(save_cluster)):04x}")

print(f"\n{'='*70}")
print("✅ DEBUG COMPLETATO")
print(f"{'='*70}")
