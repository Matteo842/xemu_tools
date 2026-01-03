#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XBOX SAVE TOOL - Tool semplificato per backup/restore salvataggi Xbox
Usa qemu-img per gestire QCOW2 in modo sicuro
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

class XboxSaveTool:
    """Tool semplificato per gestire salvataggi Xbox."""
    
    def __init__(self):
        self.games_db = {
            'mercenaries': {
                'name': 'Mercenaries: Playground of Destruction',
                'id_pattern': b'4c410015',
                'save_markers': [b'JAC01', b'UDATA', b'TDATA'],
                'typical_size': 0x20000  # 128KB
            },
            'toejam': {
                'name': 'ToeJam & Earl III',
                'id_pattern': b'TJ&E',
                'save_markers': [b'SEGA', b'SaveMeta.xbx'],
                'typical_size': 0x20000
            },
            'halo': {
                'name': 'Halo: Combat Evolved',
                'id_pattern': b'HALO',
                'save_markers': [b'UDATA', b'checkpoint'],
                'typical_size': 0x10000
            }
        }
        
        # Area Xbox standard dove si trovano i salvataggi
        self.xbox_save_area = {
            'start': 0x440000,
            'size': 0x100000,  # 1MB - area estesa per sicurezza
            'description': 'Xbox Save Area (FATX Partition)'
        }
    
    def check_qemu_img(self):
        """Verifica che qemu-img sia disponibile."""
        try:
            result = subprocess.run(['qemu-img', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ qemu-img disponibile")
                return True
        except FileNotFoundError:
            pass
        
        print("❌ qemu-img non trovato!")
        print("💡 Installa QEMU da: https://www.qemu.org/download/")
        print("   Su Windows: scarica il binario e aggiungi al PATH")
        return False
    
    def qcow2_to_raw(self, qcow2_path, raw_path):
        """Converte QCOW2 in RAW usando qemu-img."""
        cmd = [
            'qemu-img', 'convert',
            '-f', 'qcow2',
            '-O', 'raw',
            str(qcow2_path),
            str(raw_path)
        ]
        
        print(f"🔄 Conversione {Path(qcow2_path).name} -> RAW...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ RAW creato: {Path(raw_path).name}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Errore conversione: {e.stderr}")
            return False
    
    def raw_to_qcow2(self, raw_path, qcow2_path):
        """Converte RAW in QCOW2 usando qemu-img."""
        cmd = [
            'qemu-img', 'convert',
            '-f', 'raw',
            '-O', 'qcow2',
            str(raw_path),
            str(qcow2_path)
        ]
        
        print(f"🔄 Conversione RAW -> {Path(qcow2_path).name}...")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✅ QCOW2 creato: {Path(qcow2_path).name}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Errore conversione: {e.stderr}")
            return False
    
    def extract_save_area(self, qcow2_path, output_dir, game_filter=None):
        """Estrae l'area completa dei salvataggi da un QCOW2."""
        qcow2_path = Path(qcow2_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📦 ESTRAZIONE AREA SALVATAGGI")
        print(f"Sorgente: {qcow2_path.name}")
        print(f"Output: {output_dir}")
        
        # Crea file RAW temporaneo
        temp_raw = output_dir / f"temp_{qcow2_path.stem}.raw"
        
        try:
            # Converti in RAW
            if not self.qcow2_to_raw(qcow2_path, temp_raw):
                return False
            
            # Estrai area salvataggi
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_area_file = output_dir / f"xbox_saves_{timestamp}.bin"
            
            with open(temp_raw, 'rb') as raw_f:
                raw_f.seek(self.xbox_save_area['start'])
                save_data = raw_f.read(self.xbox_save_area['size'])
                
                with open(save_area_file, 'wb') as save_f:
                    save_f.write(save_data)
            
            # Analizza contenuto
            games_found = self.analyze_save_data(save_data)
            
            # Crea metadati
            metadata = {
                'extraction_date': datetime.now().isoformat(),
                'source_qcow2': str(qcow2_path),
                'save_area_start': f"0x{self.xbox_save_area['start']:08x}",
                'save_area_size': self.xbox_save_area['size'],
                'games_found': games_found,
                'total_games': len(games_found)
            }
            
            metadata_file = save_area_file.with_suffix('.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"\n📊 ESTRAZIONE COMPLETATA:")
            print(f"  📄 Area salvataggi: {save_area_file.name}")
            print(f"  📋 Metadati: {metadata_file.name}")
            print(f"  🎮 Giochi trovati: {len(games_found)}")
            
            for game in games_found:
                print(f"    - {game['name']}: 0x{game['offset']:08x}")
            
            return {
                'save_file': save_area_file,
                'metadata_file': metadata_file,
                'games_found': games_found
            }
        
        finally:
            # Pulisci file temporaneo
            if temp_raw.exists():
                temp_raw.unlink()
    
    def inject_save_area(self, save_area_file, metadata_file, target_qcow2):
        """Inietta un'area di salvataggi in un QCOW2."""
        save_area_file = Path(save_area_file)
        metadata_file = Path(metadata_file)
        target_qcow2 = Path(target_qcow2)
        
        print(f"💉 INIEZIONE AREA SALVATAGGI")
        print(f"Area: {save_area_file.name}")
        print(f"Target: {target_qcow2.name}")
        
        # Leggi metadati
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        # Leggi area da iniettare
        with open(save_area_file, 'rb') as f:
            save_data = f.read()
        
        print(f"📋 Giochi nell'area: {metadata['total_games']}")
        for game in metadata['games_found']:
            print(f"  - {game['name']}")
        
        # Conferma
        confirm = input("\n⚠️  Procedere con l'iniezione? (s/N): ").strip().lower()
        if confirm != 's':
            print("❌ Operazione annullata")
            return False
        
        # Backup del target
        backup_path = target_qcow2.with_suffix('.qcow2.backup')
        shutil.copy2(target_qcow2, backup_path)
        print(f"🔄 Backup creato: {backup_path.name}")
        
        # Crea RAW temporaneo
        temp_raw = target_qcow2.with_suffix('.temp.raw')
        
        try:
            # Converti target in RAW
            if not self.qcow2_to_raw(target_qcow2, temp_raw):
                return False
            
            # Inietta area salvataggi
            area_start = int(metadata['save_area_start'], 16)
            
            with open(temp_raw, 'r+b') as f:
                f.seek(area_start)
                bytes_written = f.write(save_data)
                f.flush()
                os.fsync(f.fileno())
            
            print(f"✅ Scritti {bytes_written:,} bytes a 0x{area_start:08x}")
            
            # Riconverti in QCOW2
            temp_qcow2 = target_qcow2.with_suffix('.temp.qcow2')
            
            if self.raw_to_qcow2(temp_raw, temp_qcow2):
                # Sostituisci il file originale
                target_qcow2.unlink()
                temp_qcow2.rename(target_qcow2)
                
                print(f"✅ INIEZIONE COMPLETATA!")
                print(f"🔄 Backup disponibile: {backup_path.name}")
                return True
            else:
                print(f"❌ Errore nella riconversione")
                return False
        
        finally:
            # Pulisci file temporanei
            for temp_file in [temp_raw, temp_qcow2]:
                if temp_file.exists():
                    temp_file.unlink()
    
    def analyze_save_data(self, data):
        """Analizza i dati per identificare giochi."""
        games_found = []
        
        for game_id, game_info in self.games_db.items():
            # Cerca pattern ID del gioco
            pos = 0
            while True:
                pos = data.find(game_info['id_pattern'], pos)
                if pos == -1:
                    break
                
                # Verifica presenza di marker aggiuntivi
                markers_found = []
                search_area = data[max(0, pos-0x1000):pos+0x1000]
                
                for marker in game_info['save_markers']:
                    if marker in search_area:
                        markers_found.append(marker.decode('ascii', errors='ignore'))
                
                if markers_found:
                    games_found.append({
                        'id': game_id,
                        'name': game_info['name'],
                        'offset': pos,
                        'markers': markers_found
                    })
                
                pos += 1
        
        return games_found
    
    def compare_save_areas(self, file1, file2):
        """Confronta due aree di salvataggio."""
        print(f"🔍 CONFRONTO AREE SALVATAGGI")
        
        with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
            data1 = f1.read()
            data2 = f2.read()
        
        if len(data1) != len(data2):
            print(f"❌ Dimensioni diverse: {len(data1)} vs {len(data2)}")
            return False
        
        differences = sum(1 for a, b in zip(data1, data2) if a != b)
        
        if differences == 0:
            print(f"✅ File identici!")
            return True
        else:
            diff_percent = (differences / len(data1)) * 100
            print(f"❌ Differenze: {differences:,} byte ({diff_percent:.2f}%)")
            
            # Mostra prime differenze
            print(f"\n🔍 Prime 10 differenze:")
            count = 0
            for i, (a, b) in enumerate(zip(data1, data2)):
                if a != b and count < 10:
                    print(f"  0x{i:08x}: {a:02x} -> {b:02x}")
                    count += 1
            
            return False

def main():
    """Menu principale."""
    print("🎮 XBOX SAVE TOOL")
    print("="*50)
    
    tool = XboxSaveTool()
    
    if not tool.check_qemu_img():
        return
    
    while True:
        print(f"\n🎯 MENU PRINCIPALE")
        print("1. 📦 Estrai area salvataggi da QCOW2")
        print("2. 💉 Inietta area salvataggi in QCOW2")
        print("3. 🔍 Confronta due aree salvataggi")
        print("4. 🔄 Converti QCOW2 <-> RAW")
        print("0. ❌ Esci")
        
        choice = input("\nScelta: ").strip()
        
        if choice == "1":
            qcow2_file = input("File QCOW2 sorgente: ").strip()
            output_dir = input("Directory output (default: ./saves_backup): ").strip()
            if not output_dir:
                output_dir = "./saves_backup"
            
            result = tool.extract_save_area(qcow2_file, output_dir)
            if result:
                print(f"\n✅ Estrazione completata!")
        
        elif choice == "2":
            save_file = input("File area salvataggi (.bin): ").strip()
            metadata_file = input("File metadati (.json): ").strip()
            target_qcow2 = input("QCOW2 target: ").strip()
            
            if tool.inject_save_area(save_file, metadata_file, target_qcow2):
                print(f"\n✅ Iniezione completata!")
        
        elif choice == "3":
            file1 = input("Primo file (.bin): ").strip()
            file2 = input("Secondo file (.bin): ").strip()
            tool.compare_save_areas(file1, file2)
        
        elif choice == "4":
            print("🔄 Conversione:")
            print("1. QCOW2 -> RAW")
            print("2. RAW -> QCOW2")
            conv_choice = input("Scelta: ").strip()
            
            if conv_choice == "1":
                qcow2_file = input("File QCOW2: ").strip()
                raw_file = input("File RAW output: ").strip()
                tool.qcow2_to_raw(qcow2_file, raw_file)
            elif conv_choice == "2":
                raw_file = input("File RAW: ").strip()
                qcow2_file = input("File QCOW2 output: ").strip()
                tool.raw_to_qcow2(raw_file, qcow2_file)
        
        elif choice == "0":
            break
        
        else:
            print("❌ Scelta non valida")

if __name__ == "__main__":
    main()