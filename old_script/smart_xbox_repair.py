#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMART XBOX REPAIR - Sistema intelligente per riparare solo le parti necessarie
Evita di copiare tutto l'HDD, ripara solo filesystem e aree critiche
"""

import os
import struct
import hashlib
from pathlib import Path
from datetime import datetime

class SmartXboxRepair:
    """Riparatore intelligente per HDD Xbox."""
    
    def __init__(self):
        self.working_hdd = r"D:\xemu\bk\xbox_hdd2.qcow2"  # HDD funzionante
        self.target_hdd = r"D:\xemu\xbox_hdd.qcow2"       # HDD da riparare
        
        # Aree critiche Xbox FATX
        self.critical_areas = {
            'qcow2_header': (0x00000000, 0x00001000),      # Header QCOW2
            'partition_table': (0x00080000, 0x00010000),    # Tabella partizioni
            'fatx_boot': (0x00160000, 0x00010000),          # Boot FATX
            'fatx_system': (0x001f0000, 0x00010000),        # Sistema FATX
            'fatx_cache': (0x00280000, 0x00010000),         # Cache FATX
            'save_area_main': (0x00430000, 0x00040000),     # Area salvataggi principale
            'save_area_extended': (0x00470000, 0x11500000), # Area salvataggi estesa
        }
    
    def analyze_differences(self):
        """Analizza differenze tra HDD funzionante e corrotto."""
        print("🔍 ANALISI DIFFERENZE HDD")
        print("="*50)
        
        differences = {}
        
        with open(self.working_hdd, 'rb') as working, open(self.target_hdd, 'rb') as target:
            for area_name, (offset, size) in self.critical_areas.items():
                print(f"📋 Analisi: {area_name}")
                
                # Leggi da entrambi
                working.seek(offset)
                working_data = working.read(size)
                
                target.seek(offset)
                target_data = target.read(size)
                
                # Confronta
                if working_data == target_data:
                    print(f"  ✅ Identico")
                    differences[area_name] = {'status': 'identical', 'diff_bytes': 0}
                else:
                    diff_bytes = sum(1 for a, b in zip(working_data, target_data) if a != b)
                    diff_percent = (diff_bytes / len(working_data)) * 100
                    print(f"  ❌ Diverso: {diff_bytes:,} bytes ({diff_percent:.1f}%)")
                    
                    differences[area_name] = {
                        'status': 'different',
                        'diff_bytes': diff_bytes,
                        'diff_percent': diff_percent,
                        'offset': offset,
                        'size': size
                    }
        
        return differences
    
    def repair_critical_areas(self, differences):
        """Ripara solo le aree critiche che sono diverse."""
        print(f"\n🔧 RIPARAZIONE AREE CRITICHE")
        print("="*50)
        
        # Backup
        backup_path = Path(self.target_hdd).with_suffix('.qcow2.backup')
        if not backup_path.exists():
            import shutil
            shutil.copy2(self.target_hdd, backup_path)
            print(f"🔄 Backup: {backup_path.name}")
        
        repaired_areas = 0
        
        with open(self.working_hdd, 'rb') as working, open(self.target_hdd, 'r+b') as target:
            for area_name, diff_info in differences.items():
                if diff_info['status'] == 'different':
                    offset = diff_info['offset']
                    size = diff_info['size']
                    
                    print(f"🔧 Riparazione: {area_name}")
                    print(f"   Offset: 0x{offset:08x}")
                    print(f"   Size: {size:,} bytes")
                    
                    # Copia area dall'HDD funzionante
                    working.seek(offset)
                    area_data = working.read(size)
                    
                    target.seek(offset)
                    target.write(area_data)
                    target.flush()
                    
                    repaired_areas += 1
                    print(f"   ✅ Riparato")
        
        print(f"\n📊 Riparate {repaired_areas} aree critiche")
        return repaired_areas > 0
    
    def smart_save_repair(self, game_patterns=None):
        """Riparazione intelligente focalizzata sui salvataggi."""
        if game_patterns is None:
            game_patterns = [b'4c410015', b'UDATA', b'TDATA', b'SaveMeta.xbx']
        
        print(f"\n🎮 RIPARAZIONE INTELLIGENTE SALVATAGGI")
        print("="*50)
        
        # Trova aree dei salvataggi nell'HDD funzionante
        save_areas = self._find_save_areas(self.working_hdd, game_patterns)
        
        if not save_areas:
            print("❌ Nessuna area salvataggi trovata")
            return False
        
        print(f"📍 Trovate {len(save_areas)} aree salvataggi")
        
        # Determina area unificata minima
        min_offset = min(area['start'] for area in save_areas)
        max_offset = max(area['end'] for area in save_areas)
        
        # Allinea a boundaries sicuri
        unified_start = (min_offset // 0x10000) * 0x10000  # Allinea a 64KB
        unified_size = ((max_offset - unified_start + 0x10000 - 1) // 0x10000) * 0x10000
        
        print(f"📦 Area unificata: 0x{unified_start:08x} - 0x{unified_start + unified_size:08x}")
        print(f"📏 Dimensione: {unified_size:,} bytes ({unified_size / 1024 / 1024:.1f}MB)")
        
        # Backup
        backup_path = Path(self.target_hdd).with_suffix('.qcow2.backup')
        if not backup_path.exists():
            import shutil
            shutil.copy2(self.target_hdd, backup_path)
            print(f"🔄 Backup: {backup_path.name}")
        
        # Copia area unificata
        with open(self.working_hdd, 'rb') as working, open(self.target_hdd, 'r+b') as target:
            working.seek(unified_start)
            save_data = working.read(unified_size)
            
            target.seek(unified_start)
            bytes_written = target.write(save_data)
            target.flush()
            os.fsync(target.fileno())
        
        print(f"✅ Copiati {bytes_written:,} bytes")
        return True
    
    def _find_save_areas(self, hdd_path, patterns):
        """Trova aree dei salvataggi nell'HDD."""
        areas = []
        
        with open(hdd_path, 'rb') as f:
            file_size = os.path.getsize(hdd_path)
            chunk_size = 1024 * 1024  # 1MB
            
            for offset in range(0, file_size, chunk_size):
                f.seek(offset)
                chunk = f.read(chunk_size)
                
                for pattern in patterns:
                    pos = chunk.find(pattern)
                    if pos != -1:
                        absolute_pos = offset + pos
                        
                        # Definisci area intorno al pattern
                        area_start = max(0, absolute_pos - 0x8000)  # -32KB
                        area_end = absolute_pos + 0x20000           # +128KB
                        
                        areas.append({
                            'pattern': pattern,
                            'start': area_start,
                            'end': area_end,
                            'center': absolute_pos
                        })
        
        return areas
    
    def quick_repair(self):
        """Riparazione rapida - solo aree salvataggi."""
        print("⚡ RIPARAZIONE RAPIDA")
        print("="*30)
        
        return self.smart_save_repair()
    
    def full_repair(self):
        """Riparazione completa - analizza tutto."""
        print("🔧 RIPARAZIONE COMPLETA")
        print("="*30)
        
        # Analizza differenze
        differences = self.analyze_differences()
        
        # Ripara aree critiche
        success = self.repair_critical_areas(differences)
        
        if success:
            print("✅ Riparazione completa terminata")
        else:
            print("⚠️ Nessuna riparazione necessaria")
        
        return success
    
    def verify_repair(self):
        """Verifica che la riparazione sia andata a buon fine."""
        print(f"\n🧪 VERIFICA RIPARAZIONE")
        print("="*30)
        
        patterns = [b'4c410015', b'UDATA', b'TDATA', b'SaveMeta.xbx']
        
        with open(self.target_hdd, 'rb') as f:
            # Cerca nell'area salvataggi
            f.seek(0x430000)
            save_area = f.read(0x100000)  # 1MB
            
            found_patterns = 0
            for pattern in patterns:
                if pattern in save_area:
                    pos = save_area.find(pattern)
                    abs_pos = 0x430000 + pos
                    print(f"  ✅ {pattern.decode('ascii', errors='ignore')}: 0x{abs_pos:08x}")
                    found_patterns += 1
                else:
                    print(f"  ❌ {pattern.decode('ascii', errors='ignore')}: NON TROVATO")
        
        success_rate = found_patterns / len(patterns)
        print(f"\n📊 Pattern verificati: {found_patterns}/{len(patterns)} ({success_rate:.1%})")
        
        if success_rate >= 0.75:
            print("✅ Riparazione probabilmente riuscita")
            return True
        else:
            print("❌ Riparazione probabilmente fallita")
            return False

def main():
    """Menu principale."""
    print("🔧 SMART XBOX REPAIR")
    print("="*40)
    
    repair = SmartXboxRepair()
    
    while True:
        print(f"\n🎯 MENU RIPARAZIONE:")
        print("1. ⚡ Riparazione rapida (solo salvataggi)")
        print("2. 🔧 Riparazione completa (tutte le aree)")
        print("3. 🔍 Analizza differenze")
        print("4. 🧪 Verifica riparazione")
        print("0. ❌ Esci")
        
        choice = input("Scelta: ").strip()
        
        if choice == "1":
            print("\n⚡ Avvio riparazione rapida...")
            if repair.quick_repair():
                print("✅ Riparazione rapida completata!")
                if repair.verify_repair():
                    print("🎮 Ora testa xemu!")
            else:
                print("❌ Riparazione rapida fallita")
        
        elif choice == "2":
            print("\n🔧 Avvio riparazione completa...")
            if repair.full_repair():
                print("✅ Riparazione completa terminata!")
                if repair.verify_repair():
                    print("🎮 Ora testa xemu!")
            else:
                print("❌ Riparazione completa fallita")
        
        elif choice == "3":
            differences = repair.analyze_differences()
            
            print(f"\n📊 RIEPILOGO DIFFERENZE:")
            different_areas = [name for name, info in differences.items() if info['status'] == 'different']
            
            if different_areas:
                print(f"❌ Aree diverse: {len(different_areas)}")
                for area in different_areas:
                    info = differences[area]
                    print(f"  - {area}: {info['diff_percent']:.1f}% diverso")
            else:
                print("✅ Tutte le aree critiche sono identiche")
        
        elif choice == "4":
            repair.verify_repair()
        
        elif choice == "0":
            break

if __name__ == "__main__":
    main()