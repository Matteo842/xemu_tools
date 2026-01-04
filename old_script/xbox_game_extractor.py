#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XBOX GAME EXTRACTOR - Estrazione mirata per singolo gioco
Input: Nome gioco + ID → Output: Area specifica del gioco
"""

import os
import json
import hashlib
import struct
from datetime import datetime
from pathlib import Path

class XboxGameDatabase:
    """Database dei giochi Xbox con ID e pattern."""
    
    def __init__(self):
        self.games = {
            'mercenaries': {
                'name': 'Mercenaries: Playground of Destruction',
                'id': '4c410015',
                'id_bytes': bytes.fromhex('4c410015'),
                'markers': [b'JAC01', b'UDATA', b'TDATA'],
                'typical_size': 0x20000,  # 128KB
                'description': 'Mercenaries save data'
            },
            'toejam': {
                'name': 'ToeJam & Earl III: Mission to Earth',
                'id': 'TJ&E3',
                'id_bytes': b'TJ&E',
                'markers': [b'SEGA', b'SaveMeta.xbx'],
                'typical_size': 0x30000,  # 192KB
                'description': 'ToeJam & Earl III save data'
            },
            'halo': {
                'name': 'Halo: Combat Evolved',
                'id': 'HALO',
                'id_bytes': b'HALO',
                'markers': [b'checkpoint', b'UDATA'],
                'typical_size': 0x10000,  # 64KB
                'description': 'Halo save data'
            },
            'halo2': {
                'name': 'Halo 2',
                'id': 'HALO2',
                'id_bytes': b'HALO2',
                'markers': [b'checkpoint', b'profile'],
                'typical_size': 0x15000,  # 84KB
                'description': 'Halo 2 save data'
            },
            'fable': {
                'name': 'Fable',
                'id': 'FABLE',
                'id_bytes': b'FABLE',
                'markers': [b'HERO', b'UDATA'],
                'typical_size': 0x25000,  # 148KB
                'description': 'Fable save data'
            }
        }
    
    def get_game_info(self, game_key):
        """Ottiene info di un gioco."""
        return self.games.get(game_key.lower())
    
    def list_games(self):
        """Lista tutti i giochi supportati."""
        print("🎮 GIOCHI SUPPORTATI:")
        for key, info in self.games.items():
            print(f"  {key}: {info['name']} (ID: {info['id']})")
    
    def add_custom_game(self, key, name, game_id, markers=None, size=0x20000):
        """Aggiunge un gioco personalizzato."""
        if markers is None:
            markers = [b'UDATA', b'TDATA']
        
        # Converti ID in bytes
        if isinstance(game_id, str):
            if len(game_id) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in game_id):
                id_bytes = bytes.fromhex(game_id)
            else:
                id_bytes = game_id.encode('ascii')
        else:
            id_bytes = game_id
        
        self.games[key.lower()] = {
            'name': name,
            'id': game_id,
            'id_bytes': id_bytes,
            'markers': markers,
            'typical_size': size,
            'description': f'Custom game: {name}'
        }
        
        print(f"✅ Gioco aggiunto: {key} ({name})")

class SimpleQCOW2Reader:
    """Lettore QCOW2 semplificato per estrazione mirata."""
    
    def __init__(self, qcow2_path):
        self.path = Path(qcow2_path)
        self.file = None
        self.cluster_size = 0
    
    def __enter__(self):
        self.file = open(self.path, 'rb')
        self._parse_header()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
    
    def _parse_header(self):
        """Parse header QCOW2."""
        self.file.seek(0)
        header = self.file.read(32)
        
        magic = struct.unpack('>I', header[0:4])[0]
        if magic != 0x514649fb:
            raise ValueError("Non è un file QCOW2")
        
        cluster_bits = struct.unpack('>I', header[20:24])[0]
        self.cluster_size = 1 << cluster_bits
    
    def find_game_areas(self, game_info):
        """Trova tutte le aree di un gioco specifico."""
        print(f"🔍 Ricerca: {game_info['name']}")
        print(f"   ID: {game_info['id']}")
        print(f"   Pattern: {game_info['id_bytes'].hex()}")
        
        found_areas = []
        
        # Scansiona file per ID del gioco
        chunk_size = 1024 * 1024  # 1MB chunk
        file_size = self.path.stat().st_size
        
        for offset in range(0, file_size, chunk_size):
            self.file.seek(offset)
            chunk = self.file.read(chunk_size)
            
            # Cerca ID principale
            pos = 0
            while True:
                pos = chunk.find(game_info['id_bytes'], pos)
                if pos == -1:
                    break
                
                absolute_pos = offset + pos
                print(f"  ✅ ID trovato a: 0x{absolute_pos:08x}")
                
                # Determina area intorno all'ID
                area_start = max(0, absolute_pos - 0x8000)  # -32KB
                area_end = absolute_pos + game_info['typical_size']
                area_size = area_end - area_start
                
                # Verifica presenza di marker aggiuntivi
                self.file.seek(area_start)
                area_data = self.file.read(area_size)
                
                markers_found = []
                for marker in game_info['markers']:
                    if marker in area_data:
                        marker_pos = area_data.find(marker)
                        markers_found.append({
                            'marker': marker.decode('ascii', errors='ignore'),
                            'offset': area_start + marker_pos
                        })
                
                found_areas.append({
                    'id_offset': absolute_pos,
                    'area_start': area_start,
                    'area_size': area_size,
                    'markers_found': markers_found,
                    'confidence': len(markers_found) / len(game_info['markers'])
                })
                
                pos += 1
        
        # Ordina per confidenza
        found_areas.sort(key=lambda x: x['confidence'], reverse=True)
        
        print(f"📊 Trovate {len(found_areas)} aree per {game_info['name']}")
        for i, area in enumerate(found_areas):
            print(f"  [{i+1}] 0x{area['area_start']:08x} (confidenza: {area['confidence']:.1%})")
            for marker in area['markers_found']:
                print(f"      - {marker['marker']}: 0x{marker['offset']:08x}")
        
        return found_areas
    
    def extract_game_area(self, area_info, output_dir, game_key):
        """Estrae una specifica area di gioco."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Leggi area
        self.file.seek(area_info['area_start'])
        area_data = self.file.read(area_info['area_size'])
        
        # Salva area
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        area_file = output_dir / f"{game_key}_save_{timestamp}.bin"
        
        with open(area_file, 'wb') as f:
            f.write(area_data)
        
        # Metadati
        metadata = {
            'game_key': game_key,
            'extraction_method': 'targeted_game_extraction',
            'timestamp': datetime.now().isoformat(),
            'source_qcow2': str(self.path),
            'area_start': f"0x{area_info['area_start']:08x}",
            'area_size': area_info['area_size'],
            'id_offset': f"0x{area_info['id_offset']:08x}",
            'markers_found': area_info['markers_found'],
            'confidence': area_info['confidence'],
            'data_hash': hashlib.md5(area_data).hexdigest()
        }
        
        metadata_file = area_file.with_suffix('.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Area estratta:")
        print(f"  📄 {area_file.name}")
        print(f"  📋 {metadata_file.name}")
        print(f"  📏 {len(area_data):,} bytes")
        print(f"  🎯 Confidenza: {area_info['confidence']:.1%}")
        
        return area_file, metadata_file

class XboxGameExtractor:
    """Estrattore principale per giochi Xbox."""
    
    def __init__(self):
        self.db = XboxGameDatabase()
    
    def extract_game(self, qcow2_path, game_key, output_dir="./game_extractions"):
        """Estrae un gioco specifico."""
        print(f"🎮 ESTRAZIONE GIOCO MIRATA")
        print(f"="*50)
        
        # Verifica gioco
        game_info = self.db.get_game_info(game_key)
        if not game_info:
            print(f"❌ Gioco '{game_key}' non trovato!")
            self.db.list_games()
            return None
        
        print(f"🎯 Target: {game_info['name']}")
        
        # Estrai
        with SimpleQCOW2Reader(qcow2_path) as reader:
            areas = reader.find_game_areas(game_info)
            
            if not areas:
                print(f"❌ Nessuna area trovata per {game_info['name']}")
                return None
            
            # Prendi l'area con confidenza più alta
            best_area = areas[0]
            
            if best_area['confidence'] < 0.5:
                print(f"⚠️  Confidenza bassa ({best_area['confidence']:.1%})")
                confirm = input("Procedere comunque? (s/N): ").strip().lower()
                if confirm != 's':
                    return None
            
            return reader.extract_game_area(best_area, output_dir, game_key)
    
    def inject_game(self, area_file, metadata_file, target_qcow2):
        """Inietta area di gioco in un QCOW2."""
        print(f"💉 INIEZIONE GIOCO MIRATA")
        print(f"="*50)
        
        # Leggi metadati
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        game_key = metadata['game_key']
        game_info = self.db.get_game_info(game_key)
        
        print(f"🎯 Gioco: {game_info['name'] if game_info else game_key}")
        print(f"📍 Offset: {metadata['area_start']}")
        print(f"🎯 Confidenza: {metadata['confidence']:.1%}")
        
        # Leggi area
        with open(area_file, 'rb') as f:
            area_data = f.read()
        
        # Backup
        target_path = Path(target_qcow2)
        backup_path = target_path.with_suffix('.qcow2.backup')
        
        if not backup_path.exists():
            import shutil
            shutil.copy2(target_path, backup_path)
            print(f"🔄 Backup: {backup_path.name}")
        
        # Inietta
        area_start = int(metadata['area_start'], 16)
        
        with open(target_qcow2, 'r+b') as f:
            f.seek(area_start)
            bytes_written = f.write(area_data)
            f.flush()
            os.fsync(f.fileno())
        
        print(f"✅ Iniettati {bytes_written:,} bytes")
        return True
    
    def add_game(self, key, name, game_id, markers=None):
        """Aggiunge un nuovo gioco al database."""
        self.db.add_custom_game(key, name, game_id, markers)

def main():
    """Menu principale."""
    print("🎮 XBOX GAME EXTRACTOR")
    print("Estrazione mirata per singolo gioco")
    print("="*50)
    
    extractor = XboxGameExtractor()
    
    while True:
        print(f"\n🎯 MENU:")
        print("1. 📦 Estrai gioco specifico")
        print("2. 💉 Inietta gioco specifico")
        print("3. 🎮 Lista giochi supportati")
        print("4. ➕ Aggiungi gioco personalizzato")
        print("0. ❌ Esci")
        
        choice = input("Scelta: ").strip()
        
        if choice == "1":
            qcow2_file = input("File QCOW2 sorgente: ").strip()
            game_key = input("Chiave gioco (es: mercenaries, toejam): ").strip()
            output_dir = input("Directory output (default: ./game_extractions): ").strip()
            if not output_dir:
                output_dir = "./game_extractions"
            
            result = extractor.extract_game(qcow2_file, game_key, output_dir)
            if result:
                print("✅ Estrazione completata!")
        
        elif choice == "2":
            area_file = input("File area gioco (.bin): ").strip()
            metadata_file = input("File metadati (.json): ").strip()
            target_qcow2 = input("QCOW2 target: ").strip()
            
            if extractor.inject_game(area_file, metadata_file, target_qcow2):
                print("✅ Iniezione completata!")
        
        elif choice == "3":
            extractor.db.list_games()
        
        elif choice == "4":
            key = input("Chiave gioco (es: mygame): ").strip()
            name = input("Nome completo: ").strip()
            game_id = input("ID gioco (hex o testo): ").strip()
            
            extractor.add_game(key, name, game_id)
        
        elif choice == "0":
            break

if __name__ == "__main__":
    main()