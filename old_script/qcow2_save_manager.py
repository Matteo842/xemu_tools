#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QCOW2 SAVE MANAGER - Sistema robusto per gestire salvataggi Xbox usando librerie Python
Gestisce l'intera area di salvataggio di un gioco, non solo singoli file
"""

import os
import sys
import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

# Verifica e installa dipendenze necessarie
def install_dependencies():
    """Installa le librerie necessarie per gestire QCOW2."""
    required_packages = [
        'qemu-img',  # Per conversioni QCOW2
        'python-qemu',  # Binding Python per QEMU
        'pycryptodome',  # Per hash e crittografia
    ]
    
    print("🔧 Verifico dipendenze...")
    
    # Verifica qemu-img
    try:
        result = subprocess.run(['qemu-img', '--version'], 
                              capture_output=True, text=True, check=True)
        print("✅ qemu-img disponibile")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ qemu-img non trovato")
        print("💡 Installa QEMU: https://www.qemu.org/download/")
        return False
    
    # Verifica Python packages
    try:
        import struct
        import mmap
        print("✅ Moduli Python base disponibili")
    except ImportError as e:
        print(f"❌ Modulo mancante: {e}")
        return False
    
    return True

class QCOW2SaveManager:
    """Manager per gestire salvataggi Xbox in formato QCOW2."""
    
    def __init__(self, qcow2_path):
        self.qcow2_path = Path(qcow2_path)
        self.raw_path = None
        self.temp_files = []
        
        # Aree Xbox conosciute
        self.xbox_areas = {
            'save_area_main': (0x00440000, 0x00030000),  # Area principale salvataggi
            'save_area_extended': (0x00470000, 0x00020000),  # Area estesa
            'partition_table': (0x00080000, 0x00010000),
            'fatx_partition_1': (0x00160000, 0x00010000),
            'fatx_partition_2': (0x001f0000, 0x00010000),
            'fatx_partition_3': (0x00280000, 0x00010000),
        }
        
        # Pattern di giochi Xbox
        self.game_patterns = {
            'mercenaries': {
                'id': b'4c410015',
                'markers': [b'JAC01', b'UDATA', b'TDATA'],
                'area_size': 0x00020000  # 128KB per gioco
            },
            'toejam_earl': {
                'id': b'TJ&E3',
                'markers': [b'SEGA', b'SaveMeta.xbx'],
                'area_size': 0x00020000
            },
            'generic_xbox': {
                'id': None,
                'markers': [b'UDATA', b'TDATA', b'SaveMeta.xbx'],
                'area_size': 0x00010000
            }
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - pulisce file temporanei."""
        self.cleanup()
    
    def cleanup(self):
        """Pulisce file temporanei."""
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                print(f"⚠️ Errore pulizia {temp_file}: {e}")
    
    def convert_to_raw(self):
        """Converte QCOW2 in RAW per accesso diretto."""
        print("🔄 Conversione QCOW2 -> RAW...")
        
        self.raw_path = self.qcow2_path.with_suffix('.raw')
        self.temp_files.append(self.raw_path)
        
        cmd = [
            'qemu-img', 'convert',
            '-f', 'qcow2',
            '-O', 'raw',
            str(self.qcow2_path),
            str(self.raw_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ RAW creato: {self.raw_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Errore conversione: {e.stderr}")
            return False
    
    def convert_to_qcow2(self, raw_path, output_qcow2):
        """Converte RAW in QCOW2."""
        print("🔄 Conversione RAW -> QCOW2...")
        
        cmd = [
            'qemu-img', 'convert',
            '-f', 'raw',
            '-O', 'qcow2',
            str(raw_path),
            str(output_qcow2)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ QCOW2 creato: {output_qcow2}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Errore conversione: {e.stderr}")
            return False
    
    def scan_game_saves(self, game_name=None):
        """Scansiona e identifica salvataggi di un gioco specifico."""
        if not self.raw_path:
            if not self.convert_to_raw():
                return None
        
        print(f"🔍 Scansione salvataggi per: {game_name or 'tutti i giochi'}")
        
        found_saves = []
        
        with open(self.raw_path, 'rb') as f:
            # Scansiona area principale salvataggi
            start, size = self.xbox_areas['save_area_main']
            f.seek(start)
            save_data = f.read(size)
            
            # Se specificato un gioco, cerca i suoi pattern
            if game_name and game_name in self.game_patterns:
                game_info = self.game_patterns[game_name]
                found_saves.extend(self._find_game_saves(save_data, start, game_info, game_name))
            else:
                # Cerca tutti i giochi
                for gname, ginfo in self.game_patterns.items():
                    found_saves.extend(self._find_game_saves(save_data, start, ginfo, gname))
        
        return found_saves
    
    def _find_game_saves(self, data, base_offset, game_info, game_name):
        """Trova salvataggi di un gioco specifico nei dati."""
        found = []
        
        # Cerca ID del gioco se specificato
        if game_info['id']:
            pos = 0
            while True:
                pos = data.find(game_info['id'], pos)
                if pos == -1:
                    break
                
                # Trovato ID, cerca area completa del gioco
                game_start = pos - (pos % 0x1000)  # Allinea a 4KB
                game_end = min(game_start + game_info['area_size'], len(data))
                game_area = data[game_start:game_end]
                
                # Verifica presenza di altri marker
                markers_found = []
                for marker in game_info['markers']:
                    if marker in game_area:
                        marker_pos = game_area.find(marker)
                        markers_found.append({
                            'marker': marker.decode('ascii', errors='ignore'),
                            'offset': base_offset + game_start + marker_pos
                        })
                
                if markers_found:
                    found.append({
                        'game': game_name,
                        'id_offset': base_offset + pos,
                        'area_start': base_offset + game_start,
                        'area_size': len(game_area),
                        'markers': markers_found,
                        'data_hash': hashlib.md5(game_area).hexdigest()[:16]
                    })
                
                pos += 1
        
        return found
    
    def extract_game_save_area(self, game_name, output_dir):
        """Estrae l'intera area di salvataggio di un gioco."""
        saves = self.scan_game_saves(game_name)
        
        if not saves:
            print(f"❌ Nessun salvataggio trovato per {game_name}")
            return None
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        extracted_areas = []
        
        with open(self.raw_path, 'rb') as f:
            for i, save in enumerate(saves):
                print(f"📦 Estrazione area {i+1}/{len(saves)} per {game_name}")
                
                # Leggi area completa del gioco
                f.seek(save['area_start'])
                area_data = f.read(save['area_size'])
                
                # Salva area
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                area_file = output_dir / f"{game_name}_save_area_{i+1}_{timestamp}.bin"
                
                with open(area_file, 'wb') as af:
                    af.write(area_data)
                
                # Crea metadati
                metadata = {
                    'game': game_name,
                    'extraction_date': datetime.now().isoformat(),
                    'source_qcow2': str(self.qcow2_path),
                    'area_start': f"0x{save['area_start']:08x}",
                    'area_size': save['area_size'],
                    'data_hash': save['data_hash'],
                    'markers': save['markers']
                }
                
                metadata_file = area_file.with_suffix('.json')
                with open(metadata_file, 'w') as mf:
                    json.dump(metadata, mf, indent=2)
                
                extracted_areas.append({
                    'area_file': area_file,
                    'metadata_file': metadata_file,
                    'metadata': metadata
                })
                
                print(f"  ✅ Area salvata: {area_file.name}")
                print(f"  📋 Metadati: {metadata_file.name}")
        
        return extracted_areas
    
    def inject_game_save_area(self, area_file, metadata_file, target_qcow2=None):
        """Inietta un'area di salvataggio in un QCOW2."""
        if target_qcow2 is None:
            target_qcow2 = self.qcow2_path
        
        print(f"💉 Iniezione area salvataggio in {target_qcow2}")
        
        # Leggi metadati
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        # Leggi area da iniettare
        with open(area_file, 'rb') as f:
            area_data = f.read()
        
        # Verifica hash
        current_hash = hashlib.md5(area_data).hexdigest()[:16]
        if current_hash != metadata['data_hash']:
            print(f"⚠️ Hash diverso - file potrebbe essere corrotto")
        
        # Converte target in RAW se necessario
        target_raw = Path(str(target_qcow2).replace('.qcow2', '_temp.raw'))
        self.temp_files.append(target_raw)
        
        if not self.convert_qcow2_to_raw(target_qcow2, target_raw):
            return False
        
        # Inietta nell'area corretta
        area_start = int(metadata['area_start'], 16)
        
        with open(target_raw, 'r+b') as f:
            f.seek(area_start)
            f.write(area_data)
            f.flush()
            os.fsync(f.fileno())
        
        # Riconverte in QCOW2
        backup_path = Path(str(target_qcow2) + '.backup')
        target_qcow2.rename(backup_path)
        
        if self.convert_to_qcow2(target_raw, target_qcow2):
            print(f"✅ Iniezione completata")
            print(f"🔄 Backup: {backup_path}")
            return True
        else:
            # Ripristina backup in caso di errore
            backup_path.rename(target_qcow2)
            print(f"❌ Iniezione fallita - backup ripristinato")
            return False
    
    def convert_qcow2_to_raw(self, qcow2_path, raw_path):
        """Converte QCOW2 specifico in RAW."""
        cmd = [
            'qemu-img', 'convert',
            '-f', 'qcow2',
            '-O', 'raw',
            str(qcow2_path),
            str(raw_path)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except subprocess.CalledProcessError:
            return False

def main():
    """Funzione principale con menu interattivo."""
    print("🎮 QCOW2 SAVE MANAGER")
    print("="*60)
    
    if not install_dependencies():
        print("❌ Dipendenze mancanti - impossibile continuare")
        return
    
    qcow2_path = input("Percorso file QCOW2: ").strip()
    if not qcow2_path:
        qcow2_path = r"D:\xemu\xbox_hdd.qcow2"
    
    with QCOW2SaveManager(qcow2_path) as manager:
        while True:
            print(f"\n🎯 MENU PRINCIPALE")
            print("1. 🔍 Scansiona salvataggi")
            print("2. 📦 Estrai area gioco completa")
            print("3. 💉 Inietta area gioco")
            print("4. 🔄 Converti QCOW2 <-> RAW")
            print("0. ❌ Esci")
            
            choice = input("\nScelta: ").strip()
            
            if choice == "1":
                game = input("Nome gioco (mercenaries/toejam_earl/vuoto per tutti): ").strip()
                if not game:
                    game = None
                saves = manager.scan_game_saves(game)
                
                if saves:
                    print(f"\n📋 Trovati {len(saves)} salvataggi:")
                    for i, save in enumerate(saves):
                        print(f"  [{i+1}] {save['game']}: 0x{save['area_start']:08x} ({save['area_size']} bytes)")
                        for marker in save['markers']:
                            print(f"      - {marker['marker']}: 0x{marker['offset']:08x}")
                else:
                    print("❌ Nessun salvataggio trovato")
            
            elif choice == "2":
                game = input("Nome gioco da estrarre: ").strip()
                output_dir = input("Directory output (default: ./extracted_saves): ").strip()
                if not output_dir:
                    output_dir = "./extracted_saves"
                
                areas = manager.extract_game_save_area(game, output_dir)
                if areas:
                    print(f"✅ Estratte {len(areas)} aree di salvataggio")
                
            elif choice == "3":
                area_file = input("File area (.bin): ").strip()
                metadata_file = input("File metadati (.json): ").strip()
                target = input("QCOW2 target (vuoto per stesso file): ").strip()
                
                if manager.inject_game_save_area(area_file, metadata_file, target or None):
                    print("✅ Iniezione completata")
                
            elif choice == "4":
                print("🔄 Conversione formato")
                print("1. QCOW2 -> RAW")
                print("2. RAW -> QCOW2")
                conv_choice = input("Scelta: ").strip()
                
                if conv_choice == "1":
                    if manager.convert_to_raw():
                        print(f"✅ RAW creato: {manager.raw_path}")
                elif conv_choice == "2":
                    raw_file = input("File RAW: ").strip()
                    qcow2_file = input("File QCOW2 output: ").strip()
                    if manager.convert_to_qcow2(raw_file, qcow2_file):
                        print("✅ Conversione completata")
            
            elif choice == "0":
                break

if __name__ == "__main__":
    main()