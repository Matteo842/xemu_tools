#!/usr/bin/env python3
"""
ANALISI STRUTTURA QCOW2 + FATX
Analizza il file Xbox HDD per capire esattamente la struttura.
"""

import os
import struct

# File da analizzare (il backup funzionante)
HDD_PATH = r"D:\xemu\bk\xbox_hdd2.qcow2"

print("=" * 70)
print("🔍 ANALISI STRUTTURA QCOW2 + FATX")
print("=" * 70)

if not os.path.exists(HDD_PATH):
    print(f"❌ File non trovato: {HDD_PATH}")
    exit(1)

file_size = os.path.getsize(HDD_PATH)
print(f"\n📁 File: {HDD_PATH}")
print(f"📏 Dimensione: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")

with open(HDD_PATH, 'rb') as f:
    data = f.read()

# =============================================================================
# STEP 1: HEADER QCOW2
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 1: HEADER QCOW2")
print("=" * 70)

# QCOW2 Magic: 0x514649fb
magic = struct.unpack('>I', data[0:4])[0]
if magic == 0x514649fb:
    print(f"✅ Magic QCOW2: 0x{magic:08x}")
    
    version = struct.unpack('>I', data[4:8])[0]
    backing_file_offset = struct.unpack('>Q', data[8:16])[0]
    backing_file_size = struct.unpack('>I', data[16:20])[0]
    cluster_bits = struct.unpack('>I', data[20:24])[0]
    virtual_size = struct.unpack('>Q', data[24:32])[0]
    
    cluster_size = 1 << cluster_bits
    
    print(f"   Versione: {version}")
    print(f"   Cluster bits: {cluster_bits} → Cluster size: {cluster_size:,} bytes")
    print(f"   Virtual size: {virtual_size:,} bytes ({virtual_size / 1024 / 1024 / 1024:.2f} GB)")
else:
    print(f"❌ Non è un file QCOW2! Magic: 0x{magic:08x}")
    # Continua comunque per vedere se è un file RAW

# =============================================================================
# STEP 2: CERCA HEADER FATX
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 2: RICERCA HEADER FATX")
print("=" * 70)

fatx_positions = []
pos = 0
while True:
    pos = data.find(b'FATX', pos)
    if pos == -1:
        break
    fatx_positions.append(pos)
    pos += 1

print(f"Trovati {len(fatx_positions)} header FATX:")
for i, pos in enumerate(fatx_positions[:10]):  # Mostra primi 10
    # Leggi info header
    header_data = data[pos:pos+16]
    if len(header_data) >= 12:
        volume_id = struct.unpack('<I', header_data[4:8])[0]
        sectors_per_cluster = struct.unpack('<I', header_data[8:12])[0]
        cluster_size_fatx = sectors_per_cluster * 512
        print(f"  {i+1}. 0x{pos:08x}: VolumeID={volume_id:08x}, SectorsPerCluster={sectors_per_cluster} → ClusterSize={cluster_size_fatx}")

# =============================================================================
# STEP 3: CERCA DIRECTORY ENTRIES
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 3: RICERCA DIRECTORY ENTRIES")
print("=" * 70)

# Cerca pattern noti delle directory Xbox
patterns = {
    b'UDATA': 'UDATA (User saves)',
    b'TDATA': 'TDATA (Title data)', 
    b'4c410015': 'Mercenaries ID',
    b'5345000f': 'ToeJam & Earl III ID',
    b'SaveMeta.xbx': 'SaveMeta file',
    b'SaveImage.xbx': 'SaveImage file',
    b'JAC01': 'JAC01 save',
}

for pattern, description in patterns.items():
    positions = []
    pos = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += 1
    
    if positions:
        print(f"\n🎯 {description}:")
        for p in positions[:5]:  # Mostra prime 5
            # Contesto
            ctx_start = max(0, p - 16)
            ctx = data[ctx_start:p + len(pattern) + 16]
            ascii_ctx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in ctx)
            print(f"   0x{p:08x}: \"{ascii_ctx[:50]}...\"")

# =============================================================================
# STEP 4: ANALISI AREA DIRECTORY (0x440000)
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 4: ANALISI AREA DIRECTORY (0x440000)")
print("=" * 70)

dir_start = 0x00440000
dir_area = data[dir_start:dir_start + 0x10000]

print(f"Area 0x{dir_start:08x} - 0x{dir_start + 0x10000:08x}:")

# Scansiona directory entries (64 bytes ciascuna)
valid_entries = []
for i in range(256):  # Max 256 entries in un cluster 16KB
    offset = i * 64
    entry = dir_area[offset:offset + 64]
    
    filename_size = entry[0]
    
    # Entry valida?
    if filename_size == 0xFF or filename_size == 0x00:
        continue  # Empty/end
    
    is_deleted = (filename_size == 0xE5)
    
    if is_deleted:
        actual_size = entry[1]
        if actual_size > 42:
            continue
        try:
            filename = entry[2:2+actual_size].decode('ascii', errors='replace')
        except:
            continue
    else:
        if filename_size > 42:
            continue
        try:
            # CORREZIONE: il filename inizia da offset 0x02 (dopo size e attributes)
            # ma in alcuni formati può essere a offset 0x01
            # Proviamo entrambi
            filename = entry[1:1+filename_size].decode('ascii', errors='replace')
        except:
            continue
    
    attributes = entry[0x2B] if len(entry) > 0x2B else 0
    
    # First cluster - offset 0x2C (4 bytes)
    if len(entry) >= 0x30:
        first_cluster = struct.unpack('<I', entry[0x2C:0x30])[0]
    else:
        first_cluster = 0
    
    # File size - offset 0x30 (4 bytes)
    if len(entry) >= 0x34:
        file_size = struct.unpack('<I', entry[0x30:0x34])[0]
    else:
        file_size = 0
    
    is_dir = bool(attributes & 0x10)
    
    if filename and len(filename.strip()) > 0:
        valid_entries.append({
            'index': i,
            'offset': dir_start + offset,
            'filename': filename,
            'is_deleted': is_deleted,
            'is_directory': is_dir,
            'first_cluster': first_cluster,
            'file_size': file_size,
            'attributes': attributes,
        })

print(f"\nTrovate {len(valid_entries)} directory entries valide:\n")
for entry in valid_entries:
    status = "[DEL]" if entry['is_deleted'] else "[OK] "
    type_str = "DIR " if entry['is_directory'] else "FILE"
    print(f"  {status} {type_str} 0x{entry['offset']:08x}: {entry['filename']:<30} cluster:{entry['first_cluster']:<6} size:{entry['file_size']:>10,}")

# =============================================================================
# STEP 5: CERCA ALTRE AREE DIRECTORY
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 5: ALTRE AREE DIRECTORY (0x447000, 0x450000)")
print("=" * 70)

for area_offset in [0x00447000, 0x00450000, 0x00460000]:
    print(f"\n--- Area 0x{area_offset:08x} ---")
    area = data[area_offset:area_offset + 0x1000]
    
    for i in range(64):  # Check first 64 entries
        offset = i * 64
        entry = area[offset:offset + 64]
        
        if len(entry) < 64:
            break
        
        filename_size = entry[0]
        if filename_size == 0xFF or filename_size == 0x00:
            continue
        if filename_size > 42 and filename_size != 0xE5:
            continue
        
        is_deleted = (filename_size == 0xE5)
        
        try:
            if is_deleted:
                actual_size = min(entry[1], 42)
                filename = entry[2:2+actual_size].decode('ascii', errors='replace')
            else:
                filename = entry[1:1+filename_size].decode('ascii', errors='replace')
        except:
            continue
        
        if len(filename.strip()) > 2:
            if len(entry) >= 0x34:
                first_cluster = struct.unpack('<I', entry[0x2C:0x30])[0]
            else:
                first_cluster = 0
            
            status = "[DEL]" if is_deleted else "[OK] "
            print(f"  {status} 0x{area_offset + offset:08x}: {filename:<20} cluster:{first_cluster}")

# =============================================================================
# STEP 6: ANALISI FAT TABLE
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 6: ANALISI FAT TABLE")
print("=" * 70)

# Le tabelle FAT dovrebbero essere dopo l'header FATX
# Per il primo header FATX trovato, analizziamo la FAT

if fatx_positions:
    first_fatx = fatx_positions[0]
    fat_start = first_fatx + 0x1000  # FAT inizia 0x1000 dopo l'header
    
    print(f"Prima FAT table teorica: 0x{fat_start:08x}")
    
    # Leggi primi entries FAT (assumendo FAT16 = 2 bytes per entry)
    print("\nPrimi 32 FAT entries (FAT16, 2 bytes each):")
    for i in range(32):
        if fat_start + i*2 + 2 <= len(data):
            entry = struct.unpack('<H', data[fat_start + i*2:fat_start + i*2 + 2])[0]
            if entry != 0:
                print(f"  FAT[{i:3}] = 0x{entry:04x}", end="")
                if entry == 0xFFFF:
                    print(" (END)")
                elif entry >= 0xFFF8:
                    print(" (RESERVED)")
                else:
                    print(f" → cluster {entry}")

# =============================================================================
# STEP 7: RIEPILOGO PER SINGOLO GIOCO
# =============================================================================
print("\n" + "=" * 70)
print("📋 STEP 7: RIEPILOGO PER BACKUP SINGOLO GIOCO")
print("=" * 70)

print("""
Per fare backup/restore di un SINGOLO gioco, servono:

1. DIRECTORY ENTRY del gioco (64 bytes)
   - Contiene: nome, first_cluster, size, attributi
   
2. FAT CHAIN del gioco
   - Serie di entry FAT che formano la catena del file
   
3. DATA CLUSTERS
   - I dati effettivi puntati dalla FAT chain
   
4. SUBDIRECTORY (per UDATA/TDATA)
   - I giochi sono in E:\\UDATA\\<GAME_ID>\\...
   - Ogni sottocartella ha la sua directory entry
   
PROBLEMA: La FAT table è CONDIVISA!
SOLUZIONE: Fare MERGE della FAT, non sovrascrittura totale.
""")

print("=" * 70)
print("✅ ANALISI COMPLETATA")
print("=" * 70)
