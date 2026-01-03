#!/usr/bin/env python3
"""
FATX DEEP PARSER - Parser avanzato per estrarre/iniettare singoli giochi

Obiettivo: Capire esattamente quali cluster appartengono a quale gioco
per poter fare backup/restore per singolo gioco.
"""

import os
import struct
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

# Config
HDD_PATH = r"D:\xemu\bk\xbox_hdd2.qcow2"

# Struttura Xbox HDD (dalle nostre analisi)
PARTITION_E_START = 0x00120000  # Partizione E (saves)
FATX_HEADER_OFFSET = PARTITION_E_START
FAT_TABLE_OFFSET = PARTITION_E_START + 0x1000  # Dopo l'header
ROOT_DIR_OFFSET = 0x00440000  # Directory entries dei saves
SAVE_DATA_OFFSET = 0x00460000  # Inizio dati saves


@dataclass
class FATXHeader:
    """Header della partizione FATX."""
    magic: str
    volume_id: int
    cluster_size: int
    fat_type: str  # FAT16 o FAT32


@dataclass 
class DirectoryEntry:
    """Entry di directory FATX (64 bytes)."""
    offset: int
    filename: str
    filename_size: int
    attributes: int
    is_directory: bool
    first_cluster: int
    file_size: int
    create_date: int
    create_time: int
    write_date: int
    write_time: int
    is_deleted: bool


@dataclass
class GameSaveInfo:
    """Informazioni complete su un salvataggio di gioco."""
    game_id: str
    game_name: str
    directory_entry: DirectoryEntry
    sub_entries: List[DirectoryEntry]
    cluster_chain: List[int]
    total_size: int


class FATXParser:
    """Parser avanzato per filesystem FATX."""
    
    def __init__(self, hdd_path: str):
        self.hdd_path = hdd_path
        self.data = None
        self.header = None
        self.fat_entries = []
        
    def load(self):
        """Carica l'HDD in memoria."""
        print(f"📂 Caricamento: {Path(self.hdd_path).name}")
        with open(self.hdd_path, 'rb') as f:
            self.data = f.read()
        print(f"   Dimensione: {len(self.data):,} bytes")
        
    def parse_header(self, offset: int) -> Optional[FATXHeader]:
        """Parsa l'header FATX a un dato offset."""
        if self.data[offset:offset+4] != b'FATX':
            return None
            
        volume_id = struct.unpack('<I', self.data[offset+4:offset+8])[0]
        cluster_sectors = struct.unpack('<I', self.data[offset+8:offset+12])[0]
        cluster_size = cluster_sectors * 512
        
        # FAT16 se cluster < 65525, altrimenti FAT32
        fat_type = "FAT16" if cluster_size < 65525 else "FAT32"
        
        return FATXHeader(
            magic="FATX",
            volume_id=volume_id,
            cluster_size=cluster_size,
            fat_type=fat_type
        )
        
    def parse_directory_entry(self, offset: int) -> Optional[DirectoryEntry]:
        """Parsa una directory entry da 64 bytes."""
        entry_data = self.data[offset:offset+64]
        
        if len(entry_data) < 64:
            return None
            
        filename_size = entry_data[0]
        
        # Entry speciali
        is_deleted = (filename_size == 0xE5)
        if filename_size == 0xFF or filename_size == 0x00:
            return None
        if filename_size == 0xE5:
            filename_size = entry_data[1]  # Il size reale è nel secondo byte per entry eliminate
            
        if filename_size > 42:
            filename_size = 42
            
        try:
            if is_deleted:
                filename = entry_data[2:2+filename_size].decode('ascii', errors='replace')
            else:
                filename = entry_data[1:1+filename_size].decode('ascii', errors='replace')
        except:
            filename = "<invalid>"
            
        attributes = entry_data[43]
        first_cluster = struct.unpack('<I', entry_data[44:48])[0]
        file_size = struct.unpack('<I', entry_data[48:52])[0]
        
        create_time = struct.unpack('<H', entry_data[52:54])[0]
        create_date = struct.unpack('<H', entry_data[54:56])[0]
        write_time = struct.unpack('<H', entry_data[56:58])[0]
        write_date = struct.unpack('<H', entry_data[58:60])[0]
        
        return DirectoryEntry(
            offset=offset,
            filename=filename,
            filename_size=filename_size,
            attributes=attributes,
            is_directory=bool(attributes & 0x10),
            first_cluster=first_cluster,
            file_size=file_size,
            create_date=create_date,
            create_time=create_time,
            write_date=write_date,
            write_time=write_time,
            is_deleted=is_deleted
        )
        
    def scan_directory(self, start_offset: int, max_entries: int = 256) -> List[DirectoryEntry]:
        """Scansiona una directory per trovare tutte le entry."""
        entries = []
        
        for i in range(max_entries):
            offset = start_offset + (i * 64)
            entry = self.parse_directory_entry(offset)
            if entry:
                entries.append(entry)
                
        return entries
        
    def find_game_saves(self) -> Dict[str, GameSaveInfo]:
        """Trova tutti i save di giochi."""
        print("\n🔍 Ricerca salvataggi giochi...")
        
        games = {}
        
        # Scans la root directory dei saves
        entries = self.scan_directory(ROOT_DIR_OFFSET)
        
        print(f"   Trovate {len(entries)} entry nella root directory")
        
        for entry in entries:
            print(f"   📁 {entry.filename} @ 0x{entry.offset:08x} "
                  f"(cluster: {entry.first_cluster}, {'DIR' if entry.is_directory else 'FILE'}"
                  f"{', DELETED' if entry.is_deleted else ''})")
            
            # Cerca subdirectory che sembrano ID di giochi (8 caratteri hex)
            if entry.is_directory and len(entry.filename) == 8:
                try:
                    # Prova a interpretare come hex
                    int(entry.filename, 16)
                    
                    # È un ID di gioco!
                    game_id = entry.filename.lower()
                    
                    # Trova sub-entries (file dentro la cartella del gioco)
                    # Per ora usiamo un offset stimato
                    sub_entries = []
                    
                    games[game_id] = GameSaveInfo(
                        game_id=game_id,
                        game_name=self._get_game_name(game_id),
                        directory_entry=entry,
                        sub_entries=sub_entries,
                        cluster_chain=[entry.first_cluster],
                        total_size=entry.file_size
                    )
                except ValueError:
                    pass
                    
        return games
        
    def _get_game_name(self, game_id: str) -> str:
        """Ottiene il nome del gioco dall'ID."""
        names = {
            "4c410015": "Mercenaries",
            "5345000f": "ToeJam & Earl III",
        }
        return names.get(game_id, f"Unknown ({game_id})")
        
    def analyze_fat_usage(self, start_offset: int, num_entries: int = 1000):
        """Analizza l'uso della FAT per capire quali cluster sono usati."""
        print(f"\n📊 Analisi FAT da 0x{start_offset:08x}...")
        
        used_clusters = 0
        free_clusters = 0
        
        for i in range(num_entries):
            # FAT16: 2 bytes per entry
            offset = start_offset + (i * 2)
            entry = struct.unpack('<H', self.data[offset:offset+2])[0]
            
            if entry == 0x0000:
                free_clusters += 1
            elif entry == 0xFFFF:
                # End of chain
                used_clusters += 1
            elif entry >= 0xFFF8:
                # Reserved
                pass
            else:
                # Pointer to next cluster
                used_clusters += 1
                
        print(f"   Cluster usati: {used_clusters}")
        print(f"   Cluster liberi: {free_clusters}")
        
    def find_all_game_data_areas(self) -> Dict[str, List[Tuple[int, int]]]:
        """Trova tutte le aree dati per ogni gioco scansionando per pattern."""
        print("\n🎮 Ricerca aree dati giochi...")
        
        games = {
            "4c410015": "Mercenaries",
            "5345000f": "ToeJam & Earl III",
        }
        
        result = {}
        
        for game_id, game_name in games.items():
            print(f"\n   {game_name} ({game_id}):")
            
            areas = []
            id_bytes = game_id.encode('ascii')
            
            pos = 0
            while True:
                pos = self.data.find(id_bytes, pos)
                if pos == -1:
                    break
                    
                # Trova l'inizio dell'area (allineato a 0x1000)
                area_start = (pos // 0x1000) * 0x1000
                
                # Stima la fine dell'area cercando il prossimo pattern o area vuota
                area_end = area_start + 0x10000  # Default 64KB
                
                # Evita duplicati
                if not any(a[0] == area_start for a in areas):
                    areas.append((area_start, area_end - area_start))
                    print(f"     Area: 0x{area_start:08x} - 0x{area_end:08x}")
                    
                pos += 1
                
            result[game_id] = areas
            
        return result


def main():
    print("=" * 70)
    print("🎮 FATX DEEP PARSER - Analisi per backup/restore singolo gioco")
    print("=" * 70)
    
    parser = FATXParser(HDD_PATH)
    parser.load()
    
    # Header FATX
    print("\n📋 HEADER FATX:")
    for name, offset in [("FATX1", 0x160000), ("FATX2", 0x1f0000), ("FATX3", 0x280000)]:
        header = parser.parse_header(offset)
        if header:
            print(f"   {name} @ 0x{offset:08x}: {header.magic}, "
                  f"cluster={header.cluster_size:,} bytes")
    
    # Directory entries
    print("\n📂 DIRECTORY ROOT (0x440000):")
    entries = parser.scan_directory(ROOT_DIR_OFFSET)
    for e in entries[:10]:
        status = "DEL" if e.is_deleted else "OK"
        type_str = "DIR" if e.is_directory else "FILE"
        print(f"   [{status}] [{type_str}] {e.filename:<42} "
              f"cluster:{e.first_cluster:>4} size:{e.file_size:>10,}")
    
    # Game saves
    games = parser.find_game_saves()
    print(f"\n🎯 GIOCHI TROVATI: {len(games)}")
    for gid, info in games.items():
        print(f"   {info.game_name}: {gid}")
        print(f"     Entry offset: 0x{info.directory_entry.offset:08x}")
        print(f"     First cluster: {info.directory_entry.first_cluster}")
    
    # Aree dati
    data_areas = parser.find_all_game_data_areas()
    
    print("\n" + "=" * 70)
    print("📊 CONCLUSIONI:")
    print("=" * 70)
    print("""
Per fare backup/restore di un singolo gioco, devo estrarre:
1. La DIRECTORY ENTRY del gioco (64 bytes)
2. La catena FAT per quel gioco
3. I CLUSTER DATI puntati dalla FAT

Al ripristino:
1. Scrivere i cluster dati
2. Aggiornare la FAT
3. Inserire/aggiornare la directory entry
""")


if __name__ == "__main__":
    main()
