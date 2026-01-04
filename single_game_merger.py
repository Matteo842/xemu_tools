#!/usr/bin/env python3
"""
SINGLE GAME MERGER v4 - Backup/Restore DINAMICO per Xbox saves

NOVITA' v4:
- Calcolo DINAMICO di tutte le aree necessarie
- NON richiede piu' metadata_areas hardcoded
- Trova automaticamente il gioco per Title ID
- Scansiona ricorsivamente la struttura del gioco

Testato con: Mercenaries (4c410015)
"""

import os
import struct
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

# =============================================================================
# CONFIGURAZIONE
# =============================================================================

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd3.qcow2"  # Backup funzionante (SOLO LETTURA)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"       # HDD da modificare
BACKUP_DIR = r"d:\GitHub\xemu_tools\surgical_backups"

# Struttura Xbox FATX
FAT_TABLE_OFFSET = 0x00161000   # FAT16 Table
FAT32_TABLE_OFFSET = 0x00311000 # FAT32 Table
CLUSTER_SIZE = 16384            # 16KB
DATA_START = 0x00443000         # Inizio area dati
ENTRY_SIZE = 64                 # Directory entry size

# Database nomi giochi (opzionale, per visualizzazione)
GAME_NAMES = {
    "4c410015": "Mercenaries",
    "5345000f": "ToeJam & Earl III",
    "4d530064": "Halo 2",
}

# =============================================================================
# FUNZIONI FAT
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

def get_fat_chain(data: bytes, first_cluster: int, max_length: int = 50000) -> List[int]:
    """Costruisce la catena FAT partendo dal primo cluster."""
    if first_cluster == 0 or first_cluster >= 0xFFF0:
        return []
    
    chain = [first_cluster]
    current = first_cluster
    seen = set([first_cluster])
    
    for _ in range(max_length):
        next_cluster = read_fat16_entry(data, current)
        
        if next_cluster >= 0xFFF8 or next_cluster == 0x0000:
            break
        if next_cluster in seen:  # Loop protection
            break
        
        chain.append(next_cluster)
        seen.add(next_cluster)
        current = next_cluster
    
    return chain

def cluster_to_offset(cluster: int) -> int:
    """Converte numero cluster in offset fisico nei dati."""
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)

# =============================================================================
# PARSING DIRECTORY
# =============================================================================

def parse_directory_entry(data: bytes, offset: int) -> Optional[Dict]:
    """Parsa una directory entry FATX (64 bytes)."""
    if offset + ENTRY_SIZE > len(data):
        return None
    
    entry_data = data[offset:offset + ENTRY_SIZE]
    fn_len = entry_data[0]
    
    # Entry vuote, fine directory, o eliminate
    if fn_len == 0xFF or fn_len == 0x00 or fn_len == 0xE5:
        return None
    
    if fn_len > 42:
        return None
    
    attrs = entry_data[1]
    try:
        filename = entry_data[2:2 + fn_len].decode('ascii', errors='replace').rstrip('\x00\xff')
    except:
        return None
    
    first_cluster = struct.unpack('<I', entry_data[44:48])[0]
    file_size = struct.unpack('<I', entry_data[48:52])[0]
    
    # Validazione: cluster troppo alto = garbage
    if first_cluster > 50000:
        return None
    
    return {
        'offset': offset,
        'filename': filename,
        'attrs': attrs,
        'is_dir': bool(attrs & 0x10),
        'first_cluster': first_cluster,
        'file_size': file_size,
        'raw': entry_data
    }

def scan_directory(data: bytes, first_cluster: int, max_clusters: int = 2) -> List[Dict]:
    """Scansiona una directory e ritorna le entries valide."""
    entries = []
    chain = get_fat_chain(data, first_cluster)
    
    for cluster in chain[:max_clusters]:
        cluster_offset = cluster_to_offset(cluster)
        for i in range(CLUSTER_SIZE // ENTRY_SIZE):
            offset = cluster_offset + i * ENTRY_SIZE
            entry = parse_directory_entry(data, offset)
            if entry:
                entries.append(entry)
    
    return entries

# =============================================================================
# ANALISI DINAMICA GIOCO
# =============================================================================

def analyze_game_dynamic(data: bytes, game_id: str) -> Optional[Dict]:
    """
    Analizza dinamicamente un gioco e calcola TUTTE le aree necessarie.
    
    Ritorna un dizionario con:
    - all_clusters: set di tutti i cluster usati
    - directory_entries: lista di (offset, data) per ogni directory entry
    - fat16_entries: lista di (cluster, value) per FAT16
    - fat32_entries: lista di (cluster, offset, data) per FAT32
    - data_chunks: lista di (cluster, offset, data) per i dati
    """
    print(f"\n{'='*60}")
    print(f"ANALISI DINAMICA: {game_id}")
    print(f"{'='*60}")
    
    result = {
        'game_id': game_id,
        'game_name': GAME_NAMES.get(game_id, game_id),
        'all_clusters': set(),
        'directory_entries': [],  # (offset, raw_data)
        'fat16_entries': [],      # (cluster, value)
        'fat32_entries': [],      # (cluster, offset, data)
        'data_chunks': [],        # (cluster, offset, data)
    }
    
    # 1. Trova game in UDATA (cluster 4)
    print("\n[1] Cerca gioco in UDATA...")
    udata_entries = scan_directory(data, 4)
    game_entry = None
    
    for e in udata_entries:
        if e['filename'].lower() == game_id.lower():
            game_entry = e
            print(f"    Trovato: '{e['filename']}' @ 0x{e['offset']:08x} -> cluster {e['first_cluster']}")
            break
    
    if not game_entry:
        print(f"    ERRORE: Gioco {game_id} non trovato in UDATA!")
        return None
    
    # Salva entry UDATA del gioco
    result['directory_entries'].append((game_entry['offset'], game_entry['raw']))
    
    # 2. Scansiona cartella gioco
    print(f"\n[2] Scansiona cartella gioco (cluster {game_entry['first_cluster']})...")
    
    game_folder_chain = get_fat_chain(data, game_entry['first_cluster'])
    result['all_clusters'].update(game_folder_chain)
    print(f"    Folder chain: {len(game_folder_chain)} clusters")
    
    # Verifica se il contenuto della cartella sono DIRECTORY ENTRIES o DATI
    # Leggi il primo cluster della cartella e controlla se sembra una directory entry
    first_cluster_offset = cluster_to_offset(game_entry['first_cluster'])
    first_byte = data[first_cluster_offset]
    is_directory_content = 1 <= first_byte <= 42  # Filename length valido
    
    if is_directory_content:
        # Struttura normale con subdirectory (come Mercenaries)
        print("    Tipo: Directory con entries (struttura standard)")
        game_contents = scan_directory(data, game_entry['first_cluster'])
        print(f"    Entries trovate: {len(game_contents)}")
        
        for e in game_contents:
            t = 'DIR' if e['is_dir'] else 'FILE'
            print(f"    {t:4} {e['filename']:<25} cluster={e['first_cluster']:>5}")
            
            result['directory_entries'].append((e['offset'], e['raw']))
            
            if e['first_cluster'] > 0:
                chain = get_fat_chain(data, e['first_cluster'])
                result['all_clusters'].update(chain)
            
            # Subdirectory - scansiona ricorsivamente
            if e['is_dir'] and e['first_cluster'] > 0:
                sub_entries = scan_directory(data, e['first_cluster'])
                for se in sub_entries:
                    st = 'DIR' if se['is_dir'] else 'FILE'
                    print(f"      -> {st:4} {se['filename']:<20} cluster={se['first_cluster']:>5}")
                    
                    result['directory_entries'].append((se['offset'], se['raw']))
                    
                    if se['first_cluster'] > 0:
                        sub_chain = get_fat_chain(data, se['first_cluster'])
                        result['all_clusters'].update(sub_chain)
    else:
        # Struttura senza subdirectory - dati diretti (come ToeJam, Halo 2)
        # La cartella contiene direttamente dati, non directory entries
        print("    Tipo: Dati diretti (NO subdirectory)")
        print(f"    Primo byte: 0x{first_byte:02x} (non e' una directory entry)")
        print(f"    Usando solo FAT chain: {len(game_folder_chain)} clusters")
        
        # NUOVO: Cerca save slot separati
        # I giochi come ToeJam/Halo 2 hanno il save slot directory in cluster separati
        # Lo troviamo cercando SaveMeta.xbx che punta a cluster DENTRO la nostra chain
        print("\n    [2b] Cerca save slot separati...")
        
        game_cluster_set = set(game_folder_chain)
        
        # Cerca tutte le occorrenze di SaveMeta.xbx nell'HDD
        save_meta_pattern = b"SaveMeta.xbx"
        pos = 0
        found_save_slots = []
        
        while True:
            pos = data.find(save_meta_pattern, pos)
            if pos == -1:
                break
            
            # Verifica se è una directory entry valida
            entry_start = pos - 2
            if entry_start >= 0:
                fn_len = data[entry_start]
                if fn_len == 12:  # "SaveMeta.xbx" ha 12 caratteri
                    # Ottieni il first_cluster di questo SaveMeta
                    save_data_cluster = struct.unpack('<I', data[entry_start + 44:entry_start + 48])[0]
                    
                    # Se punta a un cluster nella nostra chain, questo è il nostro save slot!
                    if save_data_cluster in game_cluster_set:
                        # Calcola quale cluster contiene questa entry
                        if entry_start >= DATA_START:
                            save_slot_cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2
                            
                            print(f"    TROVATO save slot @ cluster {save_slot_cluster}")
                            print(f"      SaveMeta.xbx -> cluster {save_data_cluster}")
                            
                            found_save_slots.append({
                                'entry_offset': entry_start,
                                'slot_cluster': save_slot_cluster,
                                'data_cluster': save_data_cluster
                            })
            
            pos += 1
        
        # Aggiungi i save slot trovati (da SaveMeta.xbx)
        for slot in found_save_slots:
            slot_cluster = slot['slot_cluster']
            
            # Aggiungi il cluster del save slot
            result['all_clusters'].add(slot_cluster)
            
            # Scansiona le entries nel save slot
            slot_entries = scan_directory(data, slot_cluster)
            for se in slot_entries:
                st = 'DIR' if se['is_dir'] else 'FILE'
                print(f"      -> {st:4} {se['filename']:<20} cluster={se['first_cluster']:>5}")
                
                result['directory_entries'].append((se['offset'], se['raw']))
                
                # IMPORTANTE: Segui le chain dei file interni al save slot!
                # Potrebbero usare cluster FUORI dalla game_folder_chain
                if se['first_cluster'] > 0 and se['first_cluster'] not in game_cluster_set:
                    file_chain = get_fat_chain(data, se['first_cluster'])
                    new_clusters = [c for c in file_chain if c not in result['all_clusters']]
                    if new_clusters:
                        result['all_clusters'].update(file_chain)
                        print(f"         + {len(new_clusters)} cluster extra (chain: {file_chain[:5]}...)")
        
        # NUOVO: Cerca anche save slot tramite directory con nomi hex
        # Esempio: "589BCCD01326" che punta a cluster nella nostra chain
        print("\n    [2c] Cerca save slot con nomi hex...")
        
        # Funzione per verificare se un nome è hex
        def is_hex_name(name):
            if len(name) < 8:
                return False
            return all(c in '0123456789ABCDEFabcdef' for c in name)
        
        # Cerca in TUTTO l'HDD entry che puntano a cluster nella nostra chain
        # Strategia: cerchiamo il pattern first_cluster (come 4 byte little-endian)
        hex_save_slots = []
        
        # Cerca per ogni cluster nella chain
        clusters_to_search = sorted(game_cluster_set)[:20]  # Limita ai primi 20 per velocità
        
        for target_cluster in clusters_to_search:
            # Pattern da cercare: first_cluster come 4 byte a offset +44
            target_bytes = struct.pack('<I', target_cluster)
            
            pos = 0
            while True:
                pos = data.find(target_bytes, pos)
                if pos == -1:
                    break
                
                # Verifica se potrebbe essere a offset +44 di una directory entry
                entry_start = pos - 44
                if entry_start >= DATA_START:
                    fn_len = data[entry_start]
                    attrs = data[entry_start + 1]
                    
                    # Deve essere una directory (0x10) con nome hex
                    if 8 <= fn_len <= 42 and (attrs & 0x10):
                        try:
                            fn = data[entry_start + 2:entry_start + 2 + fn_len].decode('ascii')
                            if is_hex_name(fn):
                                entry_cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2
                                
                                # Evita duplicati e l'entry del gioco stesso
                                if fn.lower() != game_id.lower():
                                    if entry_cluster not in [s['slot_cluster'] for s in found_save_slots]:
                                        if entry_cluster not in [s['cluster'] for s in hex_save_slots]:
                                            print(f"    TROVATO save slot hex @ cluster {entry_cluster}")
                                            print(f"      '{fn}' -> cluster {target_cluster}")
                                            
                                            hex_save_slots.append({
                                                'cluster': entry_cluster,
                                                'offset': entry_start,
                                                'name': fn,
                                                'first_cluster': target_cluster
                                            })
                                            
                                            # Aggiungi il cluster
                                            result['all_clusters'].add(entry_cluster)
                                            result['directory_entries'].append((entry_start, data[entry_start:entry_start + 64]))
                        except:
                            pass
                
                pos += 1
        
        
        if not found_save_slots and not hex_save_slots:
            print("    Nessun save slot separato trovato")
    
    # 3. Calcola entries FAT16 e FAT32
    print(f"\n[3] Calcola entries FAT...")
    sorted_clusters = sorted(result['all_clusters'])
    print(f"    Cluster totali: {len(sorted_clusters)}")
    print(f"    Range: {sorted_clusters[0]} - {sorted_clusters[-1]}")
    
    for cluster in sorted_clusters:
        # FAT16
        fat16_value = read_fat16_entry(data, cluster)
        result['fat16_entries'].append((cluster, fat16_value))
        
        # FAT32
        fat32_offset = FAT32_TABLE_OFFSET + (cluster * 4)
        fat32_data = data[fat32_offset:fat32_offset + 4]
        result['fat32_entries'].append((cluster, fat32_offset, fat32_data))
    
    print(f"    FAT16 entries: {len(result['fat16_entries'])}")
    print(f"    FAT32 entries: {len(result['fat32_entries'])}")
    
    # 4. Estrai data chunks
    print(f"\n[4] Estrai data chunks...")
    for cluster in sorted_clusters:
        cluster_offset = cluster_to_offset(cluster)
        if cluster_offset + CLUSTER_SIZE <= len(data):
            chunk_data = data[cluster_offset:cluster_offset + CLUSTER_SIZE]
            result['data_chunks'].append((cluster, cluster_offset, chunk_data))
    
    total_data = len(result['data_chunks']) * CLUSTER_SIZE
    print(f"    Data chunks: {len(result['data_chunks'])} ({total_data:,} bytes)")
    
    # 5. Riepilogo
    print(f"\n[5] Riepilogo:")
    print(f"    Directory entries: {len(result['directory_entries'])}")
    print(f"    FAT16 entries: {len(result['fat16_entries'])}")
    print(f"    FAT32 entries: {len(result['fat32_entries'])}")
    print(f"    Data chunks: {len(result['data_chunks'])}")
    
    return result

# =============================================================================
# BACKUP DINAMICO
# =============================================================================

def backup_single_game_v4(game_id: str) -> Tuple[str, str]:
    """
    Crea un backup DINAMICO di un singolo gioco.
    Formato v4: calcola automaticamente tutte le aree necessarie.
    """
    print("\n" + "=" * 70)
    print(f"BACKUP DINAMICO v4: {game_id}")
    print("=" * 70)
    
    # Leggi HDD sorgente
    print(f"\nLettura: {Path(HDD_SOURCE).name}")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    print(f"Size: {len(data):,} bytes")
    
    # Analisi dinamica
    analysis = analyze_game_dynamic(data, game_id)
    if not analysis:
        print("ERRORE: Analisi fallita!")
        return None, None
    
    # Serializza backup
    print(f"\nCreazione backup...")
    
    all_data = b""
    
    # Header
    all_data += b"XBSV"  # Magic
    all_data += struct.pack('<I', 4)  # Versione 4 (dinamico)
    
    # Game ID (8 bytes, padded)
    game_id_bytes = game_id.encode('ascii')[:8].ljust(8, b'\x00')
    all_data += game_id_bytes
    
    # Directory entries
    all_data += struct.pack('<I', len(analysis['directory_entries']))
    for offset, entry_data in analysis['directory_entries']:
        all_data += struct.pack('<I', offset)
        all_data += entry_data  # 64 bytes
    
    # FAT16 entries
    all_data += struct.pack('<I', len(analysis['fat16_entries']))
    for cluster, fat_val in analysis['fat16_entries']:
        all_data += struct.pack('<HH', cluster, fat_val)
    
    # FAT32 entries
    all_data += struct.pack('<I', len(analysis['fat32_entries']))
    for cluster, offset, entry_data in analysis['fat32_entries']:
        all_data += struct.pack('<II', cluster, offset)
        all_data += entry_data  # 4 bytes
    
    # Data chunks
    all_data += struct.pack('<I', len(analysis['data_chunks']))
    for cluster, offset, chunk_data in analysis['data_chunks']:
        all_data += struct.pack('<II', cluster, offset)
        all_data += struct.pack('<I', len(chunk_data))
        all_data += chunk_data
    
    # Salva
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{game_id}_dynamic_{timestamp}.bin"
    metadata_file = backup_dir / f"{game_id}_dynamic_{timestamp}.json"
    
    with open(backup_file, 'wb') as f:
        f.write(all_data)
    
    # Metadata
    metadata = {
        "format": "XBSV",
        "version": 4,
        "game_id": game_id,
        "game_name": analysis['game_name'],
        "backup_date": datetime.now().isoformat(),
        "source_hdd": str(HDD_SOURCE),
        "total_clusters": len(analysis['all_clusters']),
        "directory_entries": len(analysis['directory_entries']),
        "fat16_entries": len(analysis['fat16_entries']),
        "fat32_entries": len(analysis['fat32_entries']),
        "data_chunks": len(analysis['data_chunks']),
        "total_size": len(all_data),
        "data_hash": hashlib.md5(all_data).hexdigest(),
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nBackup completato!")
    print(f"  File: {backup_file.name}")
    print(f"  Size: {len(all_data):,} bytes ({len(all_data) // 1024:,} KB)")
    print(f"  Metadata: {metadata_file.name}")
    
    return str(backup_file), str(metadata_file)

# =============================================================================
# RESTORE DINAMICO
# =============================================================================

def restore_single_game_v4(backup_file: str, metadata_file: str) -> bool:
    """
    Ripristina un gioco da backup v4 (dinamico).
    """
    print("\n" + "=" * 70)
    print("RESTORE DINAMICO v4")
    print("=" * 70)
    
    # Leggi metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    print(f"\nGioco: {metadata['game_name']} ({metadata['game_id']})")
    print(f"Backup: {metadata['backup_date']}")
    print(f"Versione formato: {metadata['version']}")
    
    # Leggi backup
    with open(backup_file, 'rb') as f:
        backup_data = f.read()
    
    # Verifica hash
    actual_hash = hashlib.md5(backup_data).hexdigest()
    if actual_hash != metadata['data_hash']:
        print("ERRORE: Hash non corrisponde! Backup corrotto?")
        return False
    print("Hash verificato OK")
    
    # Parse backup
    pos = 0
    
    # Header
    magic = backup_data[pos:pos + 4]
    pos += 4
    if magic != b"XBSV":
        print(f"ERRORE: Magic non valido: {magic}")
        return False
    
    version = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    
    if version < 4:
        print(f"ERRORE: Versione {version} non supportata (richiesta >= 4)")
        return False
    
    # Game ID
    game_id = backup_data[pos:pos + 8].decode('ascii').rstrip('\x00')
    pos += 8
    print(f"Game ID: {game_id}")
    
    # Directory entries
    dir_entries_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    dir_entries = []
    for _ in range(dir_entries_count):
        offset = struct.unpack('<I', backup_data[pos:pos + 4])[0]
        pos += 4
        entry_data = backup_data[pos:pos + 64]
        pos += 64
        dir_entries.append((offset, entry_data))
    print(f"Directory entries: {len(dir_entries)}")
    
    # FAT16 entries
    fat16_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat16_entries = []
    for _ in range(fat16_count):
        cluster, fat_val = struct.unpack('<HH', backup_data[pos:pos + 4])
        pos += 4
        fat16_entries.append((cluster, fat_val))
    print(f"FAT16 entries: {len(fat16_entries)}")
    
    # FAT32 entries
    fat32_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat32_entries = []
    for _ in range(fat32_count):
        cluster, offset = struct.unpack('<II', backup_data[pos:pos + 8])
        pos += 8
        entry_data = backup_data[pos:pos + 4]
        pos += 4
        fat32_entries.append((cluster, offset, entry_data))
    print(f"FAT32 entries: {len(fat32_entries)}")
    
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
    print(f"Data chunks: {len(data_chunks)}")
    
    # === SCRIVI SU HDD TARGET ===
    print(f"\nScrittura su: {Path(HDD_TARGET).name}")
    
    with open(HDD_TARGET, 'r+b') as f:
        
        # 1. Directory entries
        print("\n  [1/4] Directory entries...")
        for offset, entry_data in dir_entries:
            f.seek(offset)
            f.write(entry_data)
        print(f"        Scritte {len(dir_entries)} entries")
        
        # 2. FAT16 entries
        print("  [2/4] FAT16 entries...")
        for cluster, fat_val in fat16_entries:
            fat_offset = FAT_TABLE_OFFSET + (cluster * 2)
            f.seek(fat_offset)
            f.write(struct.pack('<H', fat_val))
        print(f"        Scritte {len(fat16_entries)} entries")
        
        # 3. FAT32 entries
        print("  [3/4] FAT32 entries...")
        for cluster, offset, entry_data in fat32_entries:
            f.seek(offset)
            f.write(entry_data)
        print(f"        Scritte {len(fat32_entries)} entries")
        
        # 4. Data chunks
        print("  [4/4] Data chunks...")
        for cluster, offset, chunk_data in data_chunks:
            f.seek(offset)
            f.write(chunk_data)
        total_data = sum(len(c[2]) for c in data_chunks)
        print(f"        Scritti {total_data:,} bytes")
        
        # Flush
        f.flush()
        os.fsync(f.fileno())
    
    print("\n" + "=" * 70)
    print("RESTORE COMPLETATO!")
    print("=" * 70)
    print("Gli altri giochi NON sono stati toccati.")
    print("Ora puoi testare con xemu!")
    
    return True

# =============================================================================
# LISTA GIOCHI DISPONIBILI
# =============================================================================

def list_available_games() -> List[Dict]:
    """
    Scansiona l'HDD sorgente e ritorna i giochi disponibili.
    """
    print(f"\nScansione: {Path(HDD_SOURCE).name}")
    
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    
    # Scan UDATA (cluster 4)
    udata_entries = scan_directory(data, 4)
    
    games = []
    for e in udata_entries:
        # Game ID sono stringhe hex di 8 caratteri
        if len(e['filename']) == 8:
            try:
                int(e['filename'], 16)  # Verifica che sia hex
                game_id = e['filename'].lower()
                games.append({
                    'id': game_id,
                    'name': GAME_NAMES.get(game_id, f"Unknown ({game_id})"),
                    'first_cluster': e['first_cluster'],
                    'entry_offset': e['offset'],
                })
            except ValueError:
                pass
    
    return games

def list_backups() -> List[Path]:
    """Lista i backup disponibili."""
    backup_dir = Path(BACKUP_DIR)
    if not backup_dir.exists():
        return []
    
    return sorted(backup_dir.glob("*_dynamic_*.json"), reverse=True)

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("SINGLE GAME MERGER v4 - Backup/Restore DINAMICO")
    print("=" * 70)
    
    while True:
        print("\nMENU:")
        print("1. Lista giochi disponibili")
        print("2. Backup dinamico singolo gioco")
        print("3. Restore dinamico")
        print("4. Lista backup disponibili")
        print("0. Esci")
        
        choice = input("\nScelta: ").strip()
        
        if choice == "1":
            games = list_available_games()
            print(f"\nGiochi trovati: {len(games)}")
            for g in games:
                print(f"  {g['id']}: {g['name']} (cluster {g['first_cluster']})")
        
        elif choice == "2":
            games = list_available_games()
            if not games:
                print("Nessun gioco trovato!")
                continue
            
            print("\nGiochi disponibili:")
            for i, g in enumerate(games):
                print(f"  {i+1}. {g['id']}: {g['name']}")
            
            try:
                idx = int(input("Numero gioco: ")) - 1
                if 0 <= idx < len(games):
                    backup_single_game_v4(games[idx]['id'])
                else:
                    print("Numero non valido")
            except ValueError:
                print("Input non valido")
        
        elif choice == "3":
            backups = list_backups()
            if not backups:
                print("Nessun backup trovato!")
                continue
            
            print("\nBackup disponibili:")
            for i, b in enumerate(backups):
                with open(b) as f:
                    meta = json.load(f)
                print(f"  {i+1}. {meta['game_name']} ({meta['game_id']}) - {meta['backup_date']}")
            
            try:
                idx = int(input("Numero backup: ")) - 1
                if 0 <= idx < len(backups):
                    meta_file = backups[idx]
                    bin_file = meta_file.with_suffix('.bin')
                    restore_single_game_v4(str(bin_file), str(meta_file))
                else:
                    print("Numero non valido")
            except ValueError:
                print("Input non valido")
        
        elif choice == "4":
            backups = list_backups()
            print(f"\nBackup trovati: {len(backups)}")
            for b in backups:
                try:
                    with open(b) as f:
                        meta = json.load(f)
                    print(f"  {meta['game_name']} ({meta['game_id']}) - {meta['backup_date']} - v{meta['version']}")
                except:
                    print(f"  {b.name} (errore lettura)")
        
        elif choice == "0":
            break

if __name__ == "__main__":
    main()
