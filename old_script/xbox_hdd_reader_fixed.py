#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XBOX HDD READER FIXED - Versione modificata per lavorare dalla root
Trova automaticamente i giochi e permette estrazione/iniezione mirata
"""

import os
import logging
import struct
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

# Percorsi fissi per semplificare
DEFAULT_HDD_PATH = r"D:\xemu\xbox_hdd.qcow2"
WORKING_HDD_PATH = r"D:\xemu\bk\xbox_hdd2.qcow2"
JSON_DB_PATH = "xbox_title_id_map.json"

# Carica database giochi Xbox
_xbox_game_map: Dict[str, str] = {}
try:
    if os.path.exists(JSON_DB_PATH):
        with open(JSON_DB_PATH, 'r', encoding='utf-8') as f:
            _xbox_game_map = json.load(f)
        print(f"✅ Caricati {len(_xbox_game_map)} giochi Xbox dal database")
    else:
        print(f"⚠️ Database non trovato: {JSON_DB_PATH}")
        _xbox_game_map = {}
except Exception as e:
    print(f"❌ Errore caricamento database: {e}")
    _xbox_game_map = {}

class XboxHDDReader:
    """Lettore per HDD Xbox con funzioni di estrazione/iniezione."""
    
    def __init__(self, hdd_path: str = None):
        self.hdd_path = hdd_path or DEFAULT_HDD_PATH
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def find_xbox_saves(self, quick_scan: bool = True) -> List[Dict]:
        """Trova salvataggi Xbox nell'HDD."""
        print(f"🔍 Scansione HDD: {Path(self.hdd_path).name}")
        
        if quick_scan:
            raw_saves = self.quick_qcow2_scan()
        else:
            raw_saves = self.fallback_qcow2_scan()

        if not raw_saves:
            print("❌ Nessun pattern di salvataggio trovato")
            return []
            
        return self.group_and_filter_saves(raw_saves)
    
    def quick_qcow2_scan(self) -> List[Dict]:
        """Scan veloce ottimizzato per performance massime."""
        title_id_offsets = []
        save_pattern_offsets = []
        patterns = {b'UDATA': 'UDATA', b'TDATA': 'TDATA', b'SaveMeta.xbx': 'SaveMeta.xbx'}

        try:
            with open(self.hdd_path, 'rb') as f:
                # Verifica QCOW2
                if f.read(4) != b'QFI\xfb':
                    print(f"❌ '{self.hdd_path}' non è un file QCOW2 valido")
                    return []

                file_size = os.path.getsize(self.hdd_path)
                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                
                # Scansiona solo prime e ultime parti (dove sono i salvataggi)
                scan_size = file_size // 5  # 20% del file
                scan_ranges = [
                    (0, scan_size),  # Primi 20%
                    (file_size - scan_size, file_size)  # Ultimi 20%
                ]
                
                print(f"📊 Scan veloce: {len(scan_ranges)} regioni ({scan_size * 2 / 1024 / 1024:.1f}MB totali)")
                
                # Regex precompilata per Title ID
                tid_regex = re.compile(b'[0-9a-fA-F]{8}')
                known_tids = set(_xbox_game_map.keys())
                
                for range_start, range_end in scan_ranges:
                    for offset in range(range_start, range_end, chunk_size):
                        if offset >= range_end:
                            break
                            
                        f.seek(offset)
                        read_size = min(chunk_size, range_end - offset)
                        chunk = f.read(read_size)
                        if not chunk:
                            break
                        
                        # Cerca Title ID
                        for match in tid_regex.finditer(chunk):
                            potential_tid = match.group(0).decode('ascii').lower()
                            if potential_tid in known_tids:
                                found_offset = offset + match.start()
                                title_id_offsets.append({'tid': potential_tid, 'offset': found_offset})
                        
                        # Cerca pattern di salvataggio
                        for pattern_bytes, pattern_name in patterns.items():
                            start_pos = 0
                            while True:
                                pos = chunk.find(pattern_bytes, start_pos)
                                if pos == -1:
                                    break
                                save_pattern_offsets.append({
                                    'pattern': pattern_name, 
                                    'offset': offset + pos
                                })
                                start_pos = pos + 1
                        
                        # Exit anticipato se troviamo abbastanza dati
                        if len(title_id_offsets) > 10 and len(save_pattern_offsets) > 20:
                            print("⚡ Exit anticipato: trovati dati sufficienti")
                            break
                    
                    if len(title_id_offsets) > 10 and len(save_pattern_offsets) > 20:
                        break

                print(f"📋 Scan trovato: {len(title_id_offsets)} Title ID, {len(save_pattern_offsets)} pattern")

        except Exception as e:
            print(f"❌ Errore durante scan QCOW2: {e}")
            return []

        if not title_id_offsets or not save_pattern_offsets:
            print("⚠️ Non trovati sia Title ID che pattern di salvataggio")
            return []

        # Correlazione ottimizzata
        title_id_offsets.sort(key=lambda x: x['offset'])
        correlated_saves = []
        
        for save in save_pattern_offsets:
            # Trova Title ID più vicino
            closest_tid = min(title_id_offsets, key=lambda tid: abs(tid['offset'] - save['offset']))
            context_strings = [closest_tid['tid']]
            
            correlated_saves.append({
                'pattern': save['pattern'],
                'offset': save['offset'],
                'context_strings': context_strings
            })

        return correlated_saves

    def fallback_qcow2_scan(self) -> List[Dict]:
        """Scan di fallback (usa quick scan)."""
        return self.quick_qcow2_scan()

    def group_and_filter_saves(self, raw_saves: List[Dict]) -> List[Dict]:
        """Raggruppa e filtra i salvataggi trovati."""
        print(f"📊 Analisi {len(raw_saves)} pattern grezzi")

        game_scores = {}

        for i, save in enumerate(raw_saves):
            possible_games = self.extract_real_game_name(save['context_strings'])

            if not possible_games:
                continue

            for game_name, title_id in possible_games:
                if game_name not in game_scores:
                    game_scores[game_name] = {'score': 0, 'title_id': title_id}
                game_scores[game_name]['score'] += 1

        if not game_scores:
            print("❌ Nessun gioco riconosciuto dai pattern")
            return []

        print(f"🎮 Identificati {len(game_scores)} giochi: {', '.join(game_scores.keys())}")

        final_saves = []
        for game_name, data in game_scores.items():
            title_id = data['title_id']
            final_saves.append({
                'name': game_name,
                'id': title_id,
                'path': self.hdd_path,
                'dir_name': title_id,
                'score': data['score']
            })

        print(f"✅ Filtrati {len(final_saves)} salvataggi significativi")
        return final_saves

    def extract_real_game_name(self, context_strings: List[str]) -> List[Tuple[str, str]]:
        """Estrae nomi reali dei giochi dal contesto."""
        context_text = ' '.join(context_strings).lower()
        found_games = []
        
        for tid, name in _xbox_game_map.items():
            if tid in context_text or (len(name) > 4 and name.lower() in context_text):
                if (name, tid) not in found_games:
                    found_games.append((name, tid))
                    
        return found_games

    def extract_game_save_area(self, game_id: str, output_dir: str = "./game_saves") -> Optional[Tuple[str, str]]:
        """Estrae l'area di salvataggio di un gioco specifico."""
        print(f"📦 ESTRAZIONE GIOCO: {game_id}")
        
        # Trova il gioco
        saves = self.find_xbox_saves()
        target_game = None
        
        for save in saves:
            if save['id'].lower() == game_id.lower():
                target_game = save
                break
        
        if not target_game:
            print(f"❌ Gioco {game_id} non trovato")
            print("🎮 Giochi disponibili:")
            for save in saves:
                print(f"  - {save['id']}: {save['name']}")
            return None
        
        print(f"🎯 Target: {target_game['name']} (ID: {target_game['id']})")
        
        # Trova area del gioco nell'HDD
        game_areas = self._find_game_areas_in_hdd(game_id)
        
        if not game_areas:
            print(f"❌ Nessuna area trovata per {game_id}")
            return None
        
        # Usa l'area più ricca di dati
        best_area = max(game_areas, key=lambda x: x['data_density'])
        
        print(f"📍 Migliore area: 0x{best_area['offset']:08x} (densità: {best_area['data_density']:.1%})")
        
        # Estrai area
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        area_file = output_dir / f"{game_id}_save_{timestamp}.bin"
        
        with open(self.hdd_path, 'rb') as f:
            f.seek(best_area['offset'])
            area_data = f.read(best_area['size'])
        
        with open(area_file, 'wb') as f:
            f.write(area_data)
        
        # Metadati
        metadata = {
            'game_id': game_id,
            'game_name': target_game['name'],
            'extraction_date': datetime.now().isoformat(),
            'source_hdd': str(self.hdd_path),
            'area_offset': f"0x{best_area['offset']:08x}",
            'area_size': best_area['size'],
            'data_density': best_area['data_density'],
            'data_hash': hashlib.md5(area_data).hexdigest()
        }
        
        metadata_file = area_file.with_suffix('.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Estrazione completata:")
        print(f"  📄 {area_file.name}")
        print(f"  📋 {metadata_file.name}")
        print(f"  📏 {len(area_data):,} bytes")
        
        return str(area_file), str(metadata_file)
    
    def _find_game_areas_in_hdd(self, game_id: str) -> List[Dict]:
        """Trova aree del gioco nell'HDD."""
        areas = []
        
        try:
            with open(self.hdd_path, 'rb') as f:
                file_size = os.path.getsize(self.hdd_path)
                chunk_size = 1024 * 1024  # 1MB
                
                # Cerca ID del gioco
                game_id_bytes = game_id.encode('ascii')
                
                for offset in range(0, file_size, chunk_size):
                    f.seek(offset)
                    chunk = f.read(chunk_size)
                    
                    pos = chunk.find(game_id_bytes)
                    if pos != -1:
                        absolute_pos = offset + pos
                        
                        # Analizza area intorno
                        area_start = max(0, absolute_pos - 0x10000)  # -64KB
                        area_size = 0x20000  # 128KB
                        
                        f.seek(area_start)
                        area_data = f.read(area_size)
                        
                        # Calcola densità dati
                        non_zero = sum(1 for b in area_data if b != 0)
                        data_density = non_zero / len(area_data)
                        
                        areas.append({
                            'offset': area_start,
                            'size': area_size,
                            'data_density': data_density,
                            'id_position': absolute_pos
                        })
        
        except Exception as e:
            print(f"❌ Errore ricerca aree: {e}")
        
        return areas
    
    def inject_game_save_area(self, area_file: str, metadata_file: str, target_hdd: str = None) -> bool:
        """Inietta area di salvataggio in un HDD."""
        if target_hdd is None:
            target_hdd = self.hdd_path
        
        print(f"💉 INIEZIONE GIOCO")
        print(f"Sorgente: {Path(area_file).name}")
        print(f"Target: {Path(target_hdd).name}")
        
        # Leggi metadati
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        # Leggi area
        with open(area_file, 'rb') as f:
            area_data = f.read()
        
        game_id = metadata['game_id']
        area_offset = int(metadata['area_offset'], 16)
        
        print(f"🎯 Gioco: {metadata['game_name']} ({game_id})")
        print(f"📍 Offset: 0x{area_offset:08x}")
        print(f"📏 Dimensione: {len(area_data):,} bytes")
        
        # Backup
        target_path = Path(target_hdd)
        backup_path = target_path.with_suffix('.qcow2.backup')
        
        if not backup_path.exists():
            import shutil
            shutil.copy2(target_path, backup_path)
            print(f"🔄 Backup: {backup_path.name}")
        
        # Inietta
        try:
            with open(target_hdd, 'r+b') as f:
                f.seek(area_offset)
                bytes_written = f.write(area_data)
                f.flush()
                os.fsync(f.fileno())
            
            print(f"✅ Iniettati {bytes_written:,} bytes")
            return True
        
        except Exception as e:
            print(f"❌ Errore iniezione: {e}")
            return False

def find_xbox_game_saves(hdd_path: str = None, quick_scan: bool = True) -> List[Dict]:
    """Funzione di convenienza per trovare salvataggi Xbox."""
    with XboxHDDReader(hdd_path) as reader:
        return reader.find_xbox_saves(quick_scan=quick_scan)

def extract_game_by_name(game_name_or_id: str, source_hdd: str = None, output_dir: str = "./game_saves") -> Optional[Tuple[str, str]]:
    """Estrae un gioco per nome o ID."""
    with XboxHDDReader(source_hdd or WORKING_HDD_PATH) as reader:
        # Prima trova tutti i giochi
        saves = reader.find_xbox_saves()
        
        # Cerca per nome o ID
        target_game = None
        search_term = game_name_or_id.lower()
        
        for save in saves:
            if (search_term in save['name'].lower() or 
                search_term == save['id'].lower()):
                target_game = save
                break
        
        if not target_game:
            print(f"❌ Gioco '{game_name_or_id}' non trovato")
            return None
        
        return reader.extract_game_save_area(target_game['id'], output_dir)

def inject_game_save(area_file: str, metadata_file: str, target_hdd: str = None) -> bool:
    """Inietta salvataggio di un gioco."""
    with XboxHDDReader() as reader:
        return reader.inject_game_save_area(area_file, metadata_file, target_hdd or DEFAULT_HDD_PATH)

def main():
    """Menu principale."""
    print("🎮 XBOX HDD READER FIXED")
    print("="*50)
    
    while True:
        print(f"\n🎯 MENU:")
        print("1. 🔍 Scansiona giochi nell'HDD")
        print("2. 📦 Estrai gioco specifico")
        print("3. 💉 Inietta salvataggio gioco")
        print("4. 🔄 Copia gioco da HDD funzionante")
        print("0. ❌ Esci")
        
        choice = input("Scelta: ").strip()
        
        if choice == "1":
            hdd_path = input(f"HDD path (default: {DEFAULT_HDD_PATH}): ").strip()
            if not hdd_path:
                hdd_path = DEFAULT_HDD_PATH
            
            saves = find_xbox_game_saves(hdd_path)
            
            if saves:
                print(f"\n🎮 GIOCHI TROVATI ({len(saves)}):")
                for save in saves:
                    print(f"  ID: {save['id']} | {save['name']} (score: {save.get('score', 0)})")
            else:
                print("❌ Nessun gioco trovato")
        
        elif choice == "2":
            game_name = input("Nome o ID gioco: ").strip()
            source_hdd = input(f"HDD sorgente (default: {WORKING_HDD_PATH}): ").strip()
            if not source_hdd:
                source_hdd = WORKING_HDD_PATH
            
            result = extract_game_by_name(game_name, source_hdd)
            if result:
                print("✅ Estrazione completata!")
        
        elif choice == "3":
            area_file = input("File area (.bin): ").strip()
            metadata_file = input("File metadati (.json): ").strip()
            target_hdd = input(f"HDD target (default: {DEFAULT_HDD_PATH}): ").strip()
            if not target_hdd:
                target_hdd = DEFAULT_HDD_PATH
            
            if inject_game_save(area_file, metadata_file, target_hdd):
                print("✅ Iniezione completata!")
        
        elif choice == "4":
            game_name = input("Nome o ID gioco da copiare: ").strip()
            
            print("📦 Estrazione da HDD funzionante...")
            result = extract_game_by_name(game_name, WORKING_HDD_PATH)
            
            if result:
                area_file, metadata_file = result
                print("💉 Iniezione in HDD corrente...")
                
                if inject_game_save(area_file, metadata_file, DEFAULT_HDD_PATH):
                    print("✅ Copia completata!")
        
        elif choice == "0":
            break

if __name__ == "__main__":
    main()