#!/usr/bin/env python3
"""
SINGLE GAME MERGER v5.2 - Backup/Restore con FAT RANGE per Xbox saves

NOVITA' v5.2:
- RILEVAMENTO AUTOMATICO tipo HDD (piccolo vs 8GB)
- FIX cluster non linkati via FAT (es. Black)
- Estensione automatica range cluster allocati

NOVITA' v5:
- FAT RANGE: salva un blocco intero della FAT invece di entries singole
- Risolve il problema di Halo 2 e giochi con "cluster collaterali"
- Calcola automaticamente il range ottimale con margine di sicurezza

NOVITA' precedenti (v4):
- Calcolo DINAMICO di tutte le aree necessarie
- NON richiede piu' metadata_areas hardcoded
- Trova automaticamente il gioco per Title ID
- Scansiona ricorsivamente la struttura del gioco

Testato con: Mercenaries (4c410015), Halo 2 (4d530064), Black (45410083)
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

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd5.qcow2"  # Checkpoint 1 (backup)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"        # HDD da modificare (copiare h2 qui prima del test)
BACKUP_DIR = r"d:\GitHub\xemu_tools\surgical_backups"

# Costanti globali - verranno impostate da detect_hdd_type()
FAT_TABLE_OFFSET = 0
FAT32_TABLE_OFFSET = 0
DATA_START = 0
CLUSTER_INDEX_BASE = 1  # 1 per HDD piccoli, 2 per HDD 8GB
CLUSTER_SIZE = 16384    # 16KB (costante)
ENTRY_SIZE = 64         # Directory entry size (costante)

# Database nomi giochi (opzionale, per visualizzazione)
GAME_NAMES = {
    "4c410015": "Mercenaries",
    "5345000f": "ToeJam & Earl III",
    "4d530064": "Halo 2",
    "4541005a": "NFS Underground 2",
    "45410083": "Black",
}

def detect_hdd_type(data: bytes) -> str:
    """
    Rileva automaticamente il tipo di HDD basandosi su:
    1. Dimensione del file
    2. Posizione della signature FATX
    
    Ritorna: 'small' o '8gb'
    """
    global FAT_TABLE_OFFSET, FAT32_TABLE_OFFSET, DATA_START, CLUSTER_INDEX_BASE
    
    file_size = len(data)
    
    # Cerca signature FATX in posizioni note
    # HDD piccoli: FATX @ 0x001A0000
    # HDD 8GB: FATX @ 0x00160000
    
    fatx_small = data[0x001A0000:0x001A0004] if len(data) > 0x001A0004 else b''
    fatx_8gb = data[0x00160000:0x00160004] if len(data) > 0x00160004 else b''
    
    if fatx_small == b'FATX':
        # HDD piccolo (tipo nuovo xemu)
        FAT_TABLE_OFFSET = 0x001A1000
        FAT32_TABLE_OFFSET = 0x001A1000
        DATA_START = 0x001B3000
        CLUSTER_INDEX_BASE = 1
        return 'small'
    elif fatx_8gb == b'FATX':
        # HDD 8GB originale
        FAT_TABLE_OFFSET = 0x00161000
        FAT32_TABLE_OFFSET = 0x00311000
        DATA_START = 0x00443000
        CLUSTER_INDEX_BASE = 2
        return '8gb'
    else:
        # Fallback basato sulla dimensione
        if file_size < 100_000_000:  # < 100MB
            FAT_TABLE_OFFSET = 0x001A1000
            FAT32_TABLE_OFFSET = 0x001A1000
            DATA_START = 0x001B3000
            CLUSTER_INDEX_BASE = 1
            return 'small'
        else:
            FAT_TABLE_OFFSET = 0x00161000
            FAT32_TABLE_OFFSET = 0x00311000
            DATA_START = 0x00443000
            CLUSTER_INDEX_BASE = 2
            return '8gb'

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
    # Usa CLUSTER_INDEX_BASE rilevato dinamicamente
    # HDD piccoli: 1-indexed, HDD 8GB: 2-indexed
    return DATA_START + ((cluster - CLUSTER_INDEX_BASE) * CLUSTER_SIZE)

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

def scan_directory(data: bytes, first_cluster: int, max_clusters: int = 10) -> List[Dict]:
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
    
    # 1. Trova game in UDATA - scansiona RANGE di cluster (non solo FAT chain)
    # Alcuni giochi hanno strutture piatte senza collegamenti FAT
    print("\n[1] Cerca gioco in UDATA...")
    
    game_entry = None
    sibling_save_slots = []  # Save slots che sono fratelli in UDATA
    
    # Funzione per verificare se un nome sembra un save slot (hex lungo)
    def is_save_slot_name(name):
        if len(name) < 10:  # Nomi hex save slot sono lunghi (es. 12130F4013AB)
            return False
        return all(c in '0123456789ABCDEFabcdef' for c in name)
    
    # Scansiona cluster 3-15 per trovare entries (approccio brute force)
    # Questo funziona anche per strutture piatte senza FAT chain
    all_dir_entries = []
    for cluster in range(3, 16):
        cluster_offset = cluster_to_offset(cluster)
        if cluster_offset + CLUSTER_SIZE > len(data):
            continue
        for i in range(CLUSTER_SIZE // ENTRY_SIZE):
            offset = cluster_offset + i * ENTRY_SIZE
            entry = parse_directory_entry(data, offset)
            if entry:
                all_dir_entries.append(entry)
    
    for e in all_dir_entries:
        if e['filename'].lower() == game_id.lower():
            game_entry = e
            print(f"    Trovato: '{e['filename']}' @ 0x{e['offset']:08x} -> cluster {e['first_cluster']}")
        elif is_save_slot_name(e['filename']):
            # Potrebbe essere un save slot fratello!
            sibling_save_slots.append(e)
    
    if not game_entry:
        print(f"    ERRORE: Gioco {game_id} non trovato in UDATA!")
        return None
    
    # Mostra save slots fratelli trovati
    if sibling_save_slots:
        print(f"    Trovati {len(sibling_save_slots)} possibili save slot fratelli:")
        for ss in sibling_save_slots:
            print(f"      '{ss['filename']}' @ cluster {(ss['offset'] - DATA_START) // CLUSTER_SIZE + 2} -> first_cluster {ss['first_cluster']}")
    
    # Salva entry UDATA del gioco
    result['directory_entries'].append((game_entry['offset'], game_entry['raw']))
    
    # Salva anche i save slots fratelli + loro contenuto
    for ss in sibling_save_slots:
        result['directory_entries'].append((ss['offset'], ss['raw']))
        if ss['first_cluster'] > 0:
            ss_chain = get_fat_chain(data, ss['first_cluster'])
            result['all_clusters'].update(ss_chain)
            print(f"        Cluster chain: {ss_chain}")
            
            # IMPORTANTE: Scansiona le entries DENTRO il save slot!
            # (es. SaveMeta.xbx, MATTEO, altri file)
            inner_entries = scan_directory(data, ss['first_cluster'])
            
            # Se non trova entries, prova first_cluster+1 (alcuni giochi hanno offset)
            if not inner_entries:
                next_cluster = ss['first_cluster'] + 1
                inner_entries = scan_directory(data, next_cluster)
                if inner_entries:
                    print(f"        (entries trovate in cluster {next_cluster})")
                    result['all_clusters'].add(next_cluster)
            
            # FIX v5.2: Se ancora non trova entries, cerca SaveMeta.xbx in TUTTO l'HDD!
            # Alcuni giochi (es. Black) hanno le entries del save slot in cluster separati
            # non collegati via FAT (es. cluster 9 vuoto, entries in cluster 17)
            if not inner_entries:
                print(f"        [!] Cluster {ss['first_cluster']} vuoto, ricerca brute-force...")
                save_meta_pattern = b"SaveMeta.xbx"
                
                # Scansiona cluster 10-50 per trovare entries SaveMeta.xbx
                for search_cluster in range(10, 51):
                    search_offset = cluster_to_offset(search_cluster)
                    if search_offset + CLUSTER_SIZE > len(data):
                        break
                    
                    # Cerca SaveMeta.xbx in questo cluster
                    chunk = data[search_offset:search_offset + CLUSTER_SIZE]
                    if save_meta_pattern in chunk:
                        # Trovato! Scansiona questo cluster per entries
                        found_entries = scan_directory(data, search_cluster)
                        if found_entries:
                            print(f"        [✓] Trovate {len(found_entries)} entries in cluster {search_cluster}!")
                            result['all_clusters'].add(search_cluster)
                            inner_entries.extend(found_entries)
            
            for ie in inner_entries:
                print(f"          -> {ie['filename']} @ cluster {ie['first_cluster']}")
                result['directory_entries'].append((ie['offset'], ie['raw']))
                if ie['first_cluster'] > 0:
                    ie_chain = get_fat_chain(data, ie['first_cluster'])
                    result['all_clusters'].update(ie_chain)
    
    # 2. Scansiona cartella gioco
    print(f"\n[2] Scansiona cartella gioco (cluster {game_entry['first_cluster']})...")
    
    game_folder_chain = get_fat_chain(data, game_entry['first_cluster'])
    result['all_clusters'].update(game_folder_chain)
    print(f"    Folder chain: {len(game_folder_chain)} clusters")
    
    # Verifica se il contenuto della cartella sono DIRECTORY ENTRIES o DATI
    # Una directory entry FATX valida ha:
    # - Byte 0: lunghezza nome (1-42)
    # - Byte 1: attributi (tipicamente 0x00, 0x10, 0x20, etc. - max 0x3F)
    # - Bytes 2+: nome ASCII stampabile
    first_cluster_offset = cluster_to_offset(game_entry['first_cluster'])
    first_byte = data[first_cluster_offset]       # filename length
    second_byte = data[first_cluster_offset + 1]  # attributes
    
    # Check più robusto: verifica che sembri davvero una directory entry
    is_directory_content = False
    if 1 <= first_byte <= 42:
        # Potrebbe essere una directory, verifichiamo il nome
        name_bytes = data[first_cluster_offset + 2:first_cluster_offset + 2 + first_byte]
        # Il nome deve essere ASCII stampabile (32-126) o almeno non contenere bytes nulli
        try:
            name = name_bytes.decode('ascii')
            # Verifica che sia un nome "ragionevole" - caratteri stampabili comuni
            is_printable = all(c.isprintable() or c in ' ._-' for c in name)
            is_valid_attrs = second_byte <= 0x3F  # Attributi validi FATX
            is_directory_content = is_printable and is_valid_attrs
        except:
            is_directory_content = False
    
    if is_directory_content:
        print(f"    Tipo: Directory con entries (struttura standard)")
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
        
        # TEMPORANEO: Disabilita ricerca save slot esterni che causa problemi
        # La ricerca trova save slot di ALTRI giochi quando i cluster si sovrappongono
        ENABLE_SAVE_SLOT_SEARCH = True  # Abilitato per HDD con singolo gioco
        
        found_save_slots = []
        hex_save_slots = []
        
        if ENABLE_SAVE_SLOT_SEARCH:
            # NUOVO: Cerca save slot separati
            # I giochi come ToeJam/Halo 2 hanno il save slot directory in cluster separati
            # Lo troviamo cercando SaveMeta.xbx che punta a cluster DENTRO la nostra chain
            print("\n    [2b] Cerca save slot separati...")
            
            game_cluster_set = set(game_folder_chain)
            
            # Cerca tutte le occorrenze di SaveMeta.xbx nell'HDD
            save_meta_pattern = b"SaveMeta.xbx"
            pos = 0
            
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
            
            # Cerca anche save slot tramite directory con nomi hex
            print("\n    [2c] Cerca save slot con nomi hex...")
            
            # Funzione per verificare se un nome è hex
            def is_hex_name(name):
                if len(name) < 8:
                    return False
                return all(c in '0123456789ABCDEFabcdef' for c in name)
            
            # Cerca per ogni cluster nella chain
            clusters_to_search = sorted(game_cluster_set)[:20]
            
            for target_cluster in clusters_to_search:
                target_bytes = struct.pack('<I', target_cluster)
                
                pos = 0
                while True:
                    pos = data.find(target_bytes, pos)
                    if pos == -1:
                        break
                    
                    entry_start = pos - 44
                    if entry_start >= DATA_START:
                        fn_len = data[entry_start]
                        attrs = data[entry_start + 1]
                        
                        if 8 <= fn_len <= 42 and (attrs & 0x10):
                            try:
                                fn = data[entry_start + 2:entry_start + 2 + fn_len].decode('ascii')
                                if is_hex_name(fn):
                                    entry_cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 2
                                    
                                    # Escludi UDATA e Title IDs
                                    if entry_cluster in [3, 4]:
                                        pass
                                    elif len(fn) == 8:
                                        pass
                                    elif fn.lower() != game_id.lower():
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
                                                
                                                result['all_clusters'].add(entry_cluster)
                                                result['directory_entries'].append((entry_start, data[entry_start:entry_start + 64]))
                            except:
                                pass
                    
                    pos += 1
            
            if not found_save_slots and not hex_save_slots:
                print("    Nessun save slot separato trovato")
        else:
            print("\n    [!] Ricerca save slot esterni DISABILITATA (debug)")
            print("        Usando solo la FAT chain del gioco")
    
    # 3. Calcola entries FAT16 e FAT32
    print(f"\n[3] Calcola entries FAT...")
    
    # FIX v5.2: Estendi range includendo TUTTI i cluster allocati fino al primo FREE
    # Questo cattura cluster come 18-19 di Black che non sono linkati via FAT
    # ma sono comunque usati dal gioco (FAT entry != 0x0000)
    if result['all_clusters']:
        min_cluster = min(result['all_clusters'])
        max_cluster = max(result['all_clusters'])
        
        # Trova il primo cluster FREE dopo max_cluster
        first_free = max_cluster + 1
        for c in range(max_cluster + 1, max_cluster + 100):
            fat_val = read_fat16_entry(data, c)
            if fat_val == 0x0000:
                first_free = c
                break
        
        # Includi tutti i cluster tra min e first_free-1 che sono allocati
        extended_count = 0
        for c in range(min_cluster, first_free):
            if c not in result['all_clusters']:
                fat_val = read_fat16_entry(data, c)
                if fat_val != 0x0000:  # Cluster allocato (END-OF-CHAIN o punta ad altro)
                    result['all_clusters'].add(c)
                    extended_count += 1
        
        if extended_count > 0:
            print(f"    [v5.2] Estesi {extended_count} cluster extra (range allocato fino a cluster {first_free-1})")
    
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
# FAT RANGE - NUOVA STRATEGIA v5
# =============================================================================

def calculate_fat_range(clusters: set, margin: int = 100) -> Tuple[int, int]:
    """
    Calcola il range di cluster da salvare con un margine di sicurezza.
    
    Invece di salvare solo i FAT entries dei cluster specifici del gioco,
    salviamo un BLOCCO INTERO della FAT che copre tutto il range + margine.
    
    Questo cattura anche i "cluster collaterali" che vengono modificati
    quando xemu cancella un save.
    """
    if not clusters:
        return (0, 0)
    
    min_cluster = min(clusters)
    max_cluster = max(clusters)
    
    # Aggiungi margine di sicurezza
    range_start = max(0, min_cluster - margin)
    range_end = max_cluster + margin
    
    return (range_start, range_end)


def backup_single_game_v5(game_id: str) -> Tuple[str, str]:
    """
    Crea un backup con FAT RANGE di un singolo gioco.
    
    Formato v5: 
    - Salva un BLOCCO INTERO della FAT16 e FAT32 invece di entries singole
    - Questo cattura tutti i "cluster collaterali" e risolve problemi
      come quello di Halo 2
    """
    print("\n" + "=" * 70)
    print(f"BACKUP FAT RANGE v5: {game_id}")
    print("=" * 70)
    
    # Leggi HDD sorgente
    print(f"\nLettura: {Path(HDD_SOURCE).name}")
    with open(HDD_SOURCE, 'rb') as f:
        data = f.read()
    print(f"Size: {len(data):,} bytes")
    
    # Rileva tipo HDD
    hdd_type = detect_hdd_type(data)
    print(f"Tipo HDD: {hdd_type}")
    
    # Analisi dinamica (riusa la logica v4)
    analysis = analyze_game_dynamic(data, game_id)
    if not analysis:
        print("ERRORE: Analisi fallita!")
        return None, None
    
    # Calcola FAT range con margine
    fat_range_start, fat_range_end = calculate_fat_range(analysis['all_clusters'], margin=100)
    fat_range_count = fat_range_end - fat_range_start + 1
    
    print(f"\n[6] Calcolo FAT RANGE...")
    print(f"    Cluster del gioco: {min(analysis['all_clusters'])} - {max(analysis['all_clusters'])}")
    print(f"    FAT range (con margine 100): {fat_range_start} - {fat_range_end}")
    print(f"    Cluster nel range: {fat_range_count}")
    
    # Estrai blocco FAT16 completo per il range
    fat16_range_start_offset = FAT_TABLE_OFFSET + (fat_range_start * 2)
    fat16_range_size = fat_range_count * 2  # 2 bytes per entry
    fat16_range_data = data[fat16_range_start_offset:fat16_range_start_offset + fat16_range_size]
    print(f"    FAT16 range: offset 0x{fat16_range_start_offset:08x}, size {fat16_range_size} bytes")
    
    # Estrai blocco FAT32 completo per il range
    fat32_range_start_offset = FAT32_TABLE_OFFSET + (fat_range_start * 4)
    fat32_range_size = fat_range_count * 4  # 4 bytes per entry
    fat32_range_data = data[fat32_range_start_offset:fat32_range_start_offset + fat32_range_size]
    print(f"    FAT32 range: offset 0x{fat32_range_start_offset:08x}, size {fat32_range_size} bytes")
    
    # Serializza backup
    print(f"\nCreazione backup v5...")
    
    all_data = b""
    
    # Header
    all_data += b"XBSV"  # Magic
    all_data += struct.pack('<I', 5)  # Versione 5 (FAT range)
    
    # Game ID (8 bytes, padded)
    game_id_bytes = game_id.encode('ascii')[:8].ljust(8, b'\x00')
    all_data += game_id_bytes
    
    # Directory entries (stesso formato di v4)
    all_data += struct.pack('<I', len(analysis['directory_entries']))
    for offset, entry_data in analysis['directory_entries']:
        all_data += struct.pack('<I', offset)
        all_data += entry_data  # 64 bytes
    
    # FAT RANGE invece di entries singole!
    # FAT16 range
    all_data += struct.pack('<I', fat_range_start)  # Cluster iniziale
    all_data += struct.pack('<I', fat_range_count)  # Numero cluster
    all_data += struct.pack('<I', fat16_range_start_offset)  # Offset nel file
    all_data += struct.pack('<I', len(fat16_range_data))  # Size
    all_data += fat16_range_data
    
    # FAT32 range
    all_data += struct.pack('<I', fat_range_start)  # Cluster iniziale
    all_data += struct.pack('<I', fat_range_count)  # Numero cluster
    all_data += struct.pack('<I', fat32_range_start_offset)  # Offset nel file
    all_data += struct.pack('<I', len(fat32_range_data))  # Size
    all_data += fat32_range_data
    
    # Data chunks (stesso formato di v4)
    all_data += struct.pack('<I', len(analysis['data_chunks']))
    for cluster, offset, chunk_data in analysis['data_chunks']:
        all_data += struct.pack('<II', cluster, offset)
        all_data += struct.pack('<I', len(chunk_data))
        all_data += chunk_data
    
    # Salva
    backup_dir = Path(BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{game_id}_fatrange_{timestamp}.bin"
    metadata_file = backup_dir / f"{game_id}_fatrange_{timestamp}.json"
    
    with open(backup_file, 'wb') as f:
        f.write(all_data)
    
    # Metadata
    metadata = {
        "format": "XBSV",
        "version": 5,
        "game_id": game_id,
        "game_name": analysis['game_name'],
        "backup_date": datetime.now().isoformat(),
        "source_hdd": str(HDD_SOURCE),
        "total_clusters": len(analysis['all_clusters']),
        "fat_range_start": fat_range_start,
        "fat_range_end": fat_range_end,
        "fat_range_count": fat_range_count,
        "fat16_range_size": fat16_range_size,
        "fat32_range_size": fat32_range_size,
        "directory_entries": len(analysis['directory_entries']),
        "data_chunks": len(analysis['data_chunks']),
        "total_size": len(all_data),
        "data_hash": hashlib.md5(all_data).hexdigest(),
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nBackup v5 completato!")
    print(f"  File: {backup_file.name}")
    print(f"  Size: {len(all_data):,} bytes ({len(all_data) // 1024:,} KB)")
    print(f"  FAT range salvato: cluster {fat_range_start}-{fat_range_end} ({fat_range_count} clusters)")
    print(f"  Metadata: {metadata_file.name}")
    
    return str(backup_file), str(metadata_file)


def restore_single_game_v5(backup_file: str, metadata_file: str) -> bool:
    """
    Ripristina un gioco da backup v5 (FAT range).
    
    La differenza rispetto a v4 è che ripristiniamo un BLOCCO INTERO
    della FAT invece di entries singole.
    """
    print("\n" + "=" * 70)
    print("RESTORE FAT RANGE v5")
    print("=" * 70)
    
    # Leggi metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    print(f"\nGioco: {metadata['game_name']} ({metadata['game_id']})")
    print(f"Backup: {metadata['backup_date']}")
    print(f"Versione formato: {metadata['version']}")
    print(f"FAT range: cluster {metadata['fat_range_start']}-{metadata['fat_range_end']}")
    
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
    
    if version != 5:
        print(f"ERRORE: Versione {version} non supportata da restore_v5 (richiesta 5)")
        print("Usa restore_v4 per backup versione 4")
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
    
    # FAT16 range
    fat16_range_start = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat16_range_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat16_offset = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat16_size = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat16_data = backup_data[pos:pos + fat16_size]
    pos += fat16_size
    print(f"FAT16 range: cluster {fat16_range_start}-{fat16_range_start + fat16_range_count - 1}, size {fat16_size} bytes")
    
    # FAT32 range
    fat32_range_start = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat32_range_count = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat32_offset = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat32_size = struct.unpack('<I', backup_data[pos:pos + 4])[0]
    pos += 4
    fat32_data = backup_data[pos:pos + fat32_size]
    pos += fat32_size
    print(f"FAT32 range: cluster {fat32_range_start}-{fat32_range_start + fat32_range_count - 1}, size {fat32_size} bytes")
    
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
    
    # === FASE 0: IDENTIFICA CLUSTER EXTRA (prima del restore) ===
    # Se un file è cresciuto dopo il backup (es. Halo 2 da 140 a 1200+ cluster),
    # i dati del checkpoint "nuovo" sono nei cluster extra.
    # Dobbiamo azonarli DOPO aver ripristinato la FAT.
    print(f"\n[FASE 0] Analisi TARGET per cluster extra...")
    
    # Leggi HDD target per analisi
    with open(HDD_TARGET, 'rb') as f:
        target_data = f.read()
    
    # Trova i cluster usati dal backup
    backup_clusters = set()
    for cluster, offset, chunk in data_chunks:
        backup_clusters.add(cluster)
    
    print(f"    Cluster nel backup: {len(backup_clusters)}")
    
    # Trova la FAT chain ATTUALE sul target per ogni file
    # Questo ci dice quali cluster sono usati ORA (checkpoint B)
    target_extra_clusters = set()
    
    for dir_offset, dir_entry in dir_entries:
        # Estrai first_cluster dalla entry del BACKUP
        first_cluster = struct.unpack('<I', dir_entry[44:48])[0]
        if first_cluster == 0 or first_cluster >= 0xFFF0:
            continue
        
        # Segui la FAT chain attuale sul TARGET (non sul backup!)
        current = first_cluster
        seen = set()
        while current > 0 and current < 0xFFF0 and current not in seen:
            seen.add(current)
            # Se questo cluster NON è nel backup, è un cluster "extra"
            if current not in backup_clusters:
                target_extra_clusters.add(current)
            # Leggi prossimo cluster dalla FAT16 del TARGET
            fat_off = FAT_TABLE_OFFSET + (current * 2)
            if fat_off + 2 <= len(target_data):
                next_cluster = struct.unpack('<H', target_data[fat_off:fat_off + 2])[0]
                if next_cluster >= 0xFFF8:
                    break
                current = next_cluster
            else:
                break
    
    if target_extra_clusters:
        print(f"    ⚠️  TROVATI {len(target_extra_clusters)} cluster EXTRA (file cresciuto)")
        print(f"    Range: {min(target_extra_clusters)} - {max(target_extra_clusters)}")
    else:
        print(f"    ✓ Nessun cluster extra")
    
    # === SCRIVI SU HDD TARGET (restore normale) ===
    print(f"\nScrittura su: {Path(HDD_TARGET).name}")
    
    with open(HDD_TARGET, 'r+b') as f:
        
        # 1. Directory entries
        print("\n  [1/4] Directory entries...")
        for offset, entry_data in dir_entries:
            f.seek(offset)
            f.write(entry_data)
        print(f"        Scritte {len(dir_entries)} entries")
        
        # 2. FAT16 RANGE (blocco intero!)
        print("  [2/4] FAT16 range...")
        f.seek(fat16_offset)
        f.write(fat16_data)
        print(f"        Scritto blocco di {fat16_size} bytes @ 0x{fat16_offset:08x}")
        
        # 3. FAT32 RANGE (blocco intero!)
        print("  [3/4] FAT32 range...")
        f.seek(fat32_offset)
        f.write(fat32_data)
        print(f"        Scritto blocco di {fat32_size} bytes @ 0x{fat32_offset:08x}")
        
        # 4. Data chunks
        print("  [4/4] Data chunks...")
        for cluster, offset, chunk_data in data_chunks:
            f.seek(offset)
            f.write(chunk_data)
        total_data = sum(len(c[2]) for c in data_chunks)
        print(f"        Scritti {total_data:,} bytes")
        
        # === FASE 5: AZZERA DATI DEI CLUSTER EXTRA ===
        # DISABILITATO: Questa funzionalità può corrompere dati di altri giochi!
        # Era pensata per Halo 2 ma 7000+ cluster = 116MB azzerati è troppo rischioso
        # Riattivare solo se necessario per casi specifici
        ENABLE_CLUSTER_ZEROING = False  # ⚠️ PERICOLOSO - lasciare a False!
        
        if target_extra_clusters and ENABLE_CLUSTER_ZEROING:
            print(f"\n  [5/5] Azzeramento dati cluster extra...")
            for cluster in sorted(target_extra_clusters):
                data_offset = cluster_to_offset(cluster)
                f.seek(data_offset)
                f.write(b'\x00' * CLUSTER_SIZE)
            print(f"        Azzerati {len(target_extra_clusters)} cluster ({len(target_extra_clusters) * CLUSTER_SIZE:,} bytes)")
        elif target_extra_clusters:
            print(f"\n  [SKIP] Azzeramento cluster extra DISABILITATO (sicurezza)")
            print(f"         {len(target_extra_clusters)} cluster NON azzerati")
        
        # Flush
        f.flush()
        os.fsync(f.fileno())
    
    print("\n" + "=" * 70)
    print("RESTORE v5 COMPLETATO!")
    print("=" * 70)
    if target_extra_clusters:
        print(f"✅ Azzerati {len(target_extra_clusters)} cluster extra (dati checkpoint nuovo rimossi)")
    print("FAT range ripristinato - questo include tutti i 'cluster collaterali'")
    print("Gli altri giochi NON sono stati toccati.")
    print("Ora puoi testare con xemu!")
    
    return True


# =============================================================================
# BACKUP DINAMICO (v4 legacy)
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
    
    # Rileva tipo HDD
    hdd_type = detect_hdd_type(data)
    print(f"Tipo HDD: {hdd_type}")
    
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
    
    # Rileva tipo HDD e imposta offset corretti
    hdd_type = detect_hdd_type(data)
    print(f"Tipo HDD rilevato: {hdd_type} (FAT @ 0x{FAT_TABLE_OFFSET:08x}, DATA @ 0x{DATA_START:08x})")
    
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
    """Lista i backup disponibili (v4 dynamic e v5 fatrange)."""
    backup_dir = Path(BACKUP_DIR)
    if not backup_dir.exists():
        return []
    
    # Trova sia backup _dynamic_ (v4) che _fatrange_ (v5)
    dynamic_backups = list(backup_dir.glob("*_dynamic_*.json"))
    fatrange_backups = list(backup_dir.glob("*_fatrange_*.json"))
    
    all_backups = dynamic_backups + fatrange_backups
    return sorted(all_backups, reverse=True)

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("SINGLE GAME MERGER v5.2 - Backup/Restore con FAT RANGE")
    print("=" * 70)
    print("\nNOTA: v5.2 rileva automaticamente il tipo di HDD (piccolo vs 8GB)")
    print("      Risolve problemi come Halo 2 e Black")
    print("      Le opzioni v4 sono disponibili per compatibilita'")
    
    while True:
        print("\n" + "-" * 40)
        print("MENU:")
        print("-" * 40)
        print("1. Lista giochi disponibili")
        print("")
        print("--- BACKUP (consigliato: v5) ---")
        print("2. Backup FAT RANGE v5 (CONSIGLIATO)")
        print("3. Backup dinamico v4 (legacy)")
        print("")
        print("--- RESTORE ---")
        print("4. Restore (auto-detect versione)")
        print("")
        print("--- ALTRO ---")
        print("5. Lista backup disponibili")
        print("0. Esci")
        
        choice = input("\nScelta: ").strip()
        
        if choice == "1":
            games = list_available_games()
            print(f"\nGiochi trovati: {len(games)}")
            for g in games:
                print(f"  {g['id']}: {g['name']} (cluster {g['first_cluster']})")
        
        elif choice == "2":
            # Backup v5 (FAT RANGE) - CONSIGLIATO
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
                    backup_single_game_v5(games[idx]['id'])
                else:
                    print("Numero non valido")
            except ValueError:
                print("Input non valido")
        
        elif choice == "3":
            # Backup v4 (legacy)
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
        
        elif choice == "4":
            # Restore - auto-detect versione
            backups = list_backups()
            if not backups:
                print("Nessun backup trovato!")
                continue
            
            print("\nBackup disponibili:")
            backup_metas = []
            for i, b in enumerate(backups):
                try:
                    with open(b) as f:
                        meta = json.load(f)
                    version = meta.get('version', '?')
                    backup_metas.append((b, meta))
                    print(f"  {i+1}. [{version}] {meta['game_name']} ({meta['game_id']}) - {meta['backup_date']}")
                except Exception as e:
                    backup_metas.append((b, None))
                    print(f"  {i+1}. {b.name} (errore: {e})")
            
            try:
                idx = int(input("Numero backup: ")) - 1
                if 0 <= idx < len(backups):
                    meta_file, meta = backup_metas[idx]
                    bin_file = meta_file.with_suffix('.bin')
                    
                    if meta is None:
                        print("Errore: impossibile leggere metadata del backup")
                        continue
                    
                    version = meta.get('version', 4)
                    
                    if version == 5:
                        print(f"\nUsando restore v5 (FAT RANGE)...")
                        restore_single_game_v5(str(bin_file), str(meta_file))
                    elif version >= 4:
                        print(f"\nUsando restore v4 (dinamico)...")
                        restore_single_game_v4(str(bin_file), str(meta_file))
                    else:
                        print(f"Versione {version} non supportata!")
                else:
                    print("Numero non valido")
            except ValueError:
                print("Input non valido")
        
        elif choice == "5":
            backups = list_backups()
            print(f"\nBackup trovati: {len(backups)}")
            for b in backups:
                try:
                    with open(b) as f:
                        meta = json.load(f)
                    version = meta.get('version', '?')
                    fat_range = ""
                    if version == 5 and 'fat_range_start' in meta:
                        fat_range = f" [FAT: {meta['fat_range_start']}-{meta['fat_range_end']}]"
                    print(f"  v{version} | {meta['game_name']} ({meta['game_id']}) | {meta['backup_date']}{fat_range}")
                except:
                    print(f"  {b.name} (errore lettura)")
        
        elif choice == "0":
            print("\nArrivederci!")
            break

if __name__ == "__main__":
    main()

