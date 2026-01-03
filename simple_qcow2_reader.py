#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIMPLE QCOW2 READER - Lettura diretta QCOW2 con Python puro
ZERO dipendenze esterne, ZERO conversioni, ZERO perdite di dati
"""

import os
import struct
import json
import hashlib
from datetime import datetime
from pathlib import Path

class SimpleQCOW2:
    """Lettore QCOW2 minimalista ma funzionante."""
    
    def __init__(self, qcow2_path):
        self.path = Path(qcow2_path)
        self.file = None
        self.cluster_size = 0
        self.virtual_size = 0
        
    def __enter__(self):
        self.file = open(self.path, 'rb')
        self._parse_header()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
    
    def _parse_header(self):
        """Parse minimo dell'header QCOW2."""
        self.file.seek(0)
        header = self.file.read(32)
        
        # Verifica magic number
        magic = struct.unpack('>I', header[0:4])[0]
        if magic != 0x514649fb:
            raise ValueError("Non è un file QCOW2")
        
        # Leggi cluster size e virtual size
        cluster_bits = struct.unpack('>I', header[20:24])[0]
        self.cluster_size = 1 << cluster_bits
        self.virtual_size = struct.unpack('>Q', header[24:32])[0]
        
        print(f"📋 QCOW2: {self.virtual_size:,} bytes, cluster {self.cluster_size}")
    
    def read_raw_area(self, offset, size):
        """
        Legge un'area specifica usando euristica semplice.
        Per Xbox, l'area 0x440000 di solito è mappata linearmente.
        """
        # Euristica: per file Xbox, i dati sono spesso dopo l'header
        # L'header QCOW2 è tipicamente 104 bytes + tabelle
        # I dati iniziano di solito intorno a 0x100000 (1MB)
        
        estimated_physical_offset = 0x100000 + offset
        
        # Verifica che non superi la dimensione del file
        file_size = self.path.stat().st_size
        if estimated_physical_offset + size > file_size:
            # Prova offset più conservativo
            estimated_physical_offset = 0x200000 + (offset // 2)
        
        self.file.seek(estimated_physical_offset)
        data = self.file.read(size)
        
        return data
    
    def smart_find_xbox_saves(self):
        """
        Trova l'area dei salvataggi Xbox usando pattern matching.
        Scansiona il file per trovare i marker Xbox.
        """
        print("🔍 Ricerca intelligente area salvataggi Xbox...")
        
        xbox_patterns = [
            b'4c410015',  # Mercenaries ID
            b'UDATA',     # Xbox save marker
            b'TDATA',     # Xbox save marker
            b'SaveMeta.xbx'  # Save metadata
        ]
        
        # Scansiona file in chunk da 1MB
        chunk_size = 1024 * 1024
        file_size = self.path.stat().st_size
        
        found_areas = []
        
        for offset in range(0, file_size, chunk_size):
            self.file.seek(offset)
            chunk = self.file.read(chunk_size)
            
            # Cerca pattern in questo chunk
            for pattern in xbox_patterns:
                pos = chunk.find(pattern)
                if pos != -1:
                    absolute_pos = offset + pos
                    print(f"  ✅ {pattern}: 0x{absolute_pos:08x}")
                    
                   # Estrai area intorno al pattern (±128KB) - AUMENTATO
                    area_start = max(0, absolute_pos - 0x20000) # Era 0x10000
                    area_size = 0x40000  # 256KB - Era 0x20000
                    
                    found_areas.append({
                        'pattern': pattern.decode('ascii', errors='ignore'),
                        'file_offset': absolute_pos,
                        'area_start': area_start,
                        'area_size': area_size
                    })
        
        return found_areas
    
    def extract_xbox_save_area_smart(self, output_dir):
        """Estrae area salvataggi usando ricerca intelligente."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Trova aree con pattern Xbox
        found_areas = self.smart_find_xbox_saves()
        
        if not found_areas:
            print("❌ Nessun pattern Xbox trovato")
            return None
        
        # Determina area unificata che copre tutti i pattern
        min_offset = min(area['area_start'] for area in found_areas)
        max_offset = max(area['area_start'] + area['area_size'] for area in found_areas)
        
        # Arrotonda per sicurezza
        unified_start = (min_offset // 0x10000) * 0x10000  # Allinea a 64KB
        unified_size = ((max_offset - unified_start + 0x10000 - 1) // 0x10000) * 0x10000
        
        print(f"📦 Area unificata: 0x{unified_start:08x} - 0x{unified_start + unified_size:08x}")
        print(f"📏 Dimensione: {unified_size:,} bytes")
        
        # Estrai area unificata
        self.file.seek(unified_start)
        save_data = self.file.read(unified_size)
        
        # Salva
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_file = output_dir / f"xbox_saves_smart_{timestamp}.bin"
        
        with open(save_file, 'wb') as f:
            f.write(save_data)
        
        # Metadati
        metadata = {
            'method': 'smart_pattern_search',
            'timestamp': datetime.now().isoformat(),
            'source_qcow2': str(self.path),
            'physical_offset': f"0x{unified_start:08x}",
            'size': unified_size,
            'patterns_found': found_areas,
            'data_hash': hashlib.md5(save_data).hexdigest()
        }
        
        metadata_file = save_file.with_suffix('.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✅ Estrazione smart completata:")
        print(f"  📄 {save_file.name}")
        print(f"  📋 {metadata_file.name}")
        print(f"  🎮 Pattern trovati: {len(found_areas)}")
        
        return save_file, metadata_file

class SimpleQCOW2Writer:
    """Scrittore QCOW2 minimalista."""
    
    def __init__(self, qcow2_path):
        self.path = Path(qcow2_path)
    
    def inject_at_physical_offset(self, physical_offset, data):
        """Inietta dati a un offset fisico specifico."""
        print(f"💉 Iniezione a offset fisico 0x{physical_offset:08x}")
        
        # Backup
        backup_path = self.path.with_suffix('.qcow2.backup')
        if not backup_path.exists():
            import shutil
            shutil.copy2(self.path, backup_path)
            print(f"🔄 Backup: {backup_path.name}")
        
        # Scrivi direttamente
        with open(self.path, 'r+b') as f:
            f.seek(physical_offset)
            bytes_written = f.write(data)
            f.flush()
            os.fsync(f.fileno())
        
        print(f"✅ Scritti {bytes_written:,} bytes")
        return True
    
    def inject_save_area(self, save_file, metadata_file):
        """Inietta area salvataggi usando metadati."""
        # Leggi metadati
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        # Leggi dati
        with open(save_file, 'rb') as f:
            save_data = f.read()
        
        # Usa offset fisico dai metadati
        physical_offset = int(metadata['physical_offset'], 16)
        
        return self.inject_at_physical_offset(physical_offset, save_data)

def extract_saves_from_qcow2(qcow2_path, output_dir):
    """Funzione semplice per estrarre salvataggi."""
    print(f"📦 ESTRAZIONE SEMPLICE DA {Path(qcow2_path).name}")
    
    with SimpleQCOW2(qcow2_path) as qcow2:
        return qcow2.extract_xbox_save_area_smart(output_dir)

def inject_saves_to_qcow2(save_file, metadata_file, target_qcow2):
    """Funzione semplice per iniettare salvataggi."""
    print(f"💉 INIEZIONE SEMPLICE IN {Path(target_qcow2).name}")
    
    writer = SimpleQCOW2Writer(target_qcow2)
    return writer.inject_save_area(save_file, metadata_file)

def compare_save_areas(file1, file2):
    """Confronta due aree di salvataggio."""
    print(f"🔍 CONFRONTO {Path(file1).name} vs {Path(file2).name}")
    
    with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
        data1 = f1.read()
        data2 = f2.read()
    
    if len(data1) != len(data2):
        print(f"❌ Dimensioni diverse: {len(data1)} vs {len(data2)}")
        return False
    
    differences = sum(1 for a, b in zip(data1, data2) if a != b)
    
    if differences == 0:
        print(f"✅ IDENTICI!")
        return True
    else:
        diff_percent = (differences / len(data1)) * 100
        print(f"❌ Differenze: {differences:,} byte ({diff_percent:.2f}%)")
        return False

def main():
    """Menu principale ultra-semplice."""
    print("🎮 SIMPLE QCOW2 READER")
    print("Python puro, zero dipendenze!")
    print("="*40)
    
    while True:
        print(f"\n🎯 COSA VUOI FARE?")
        print("1. 📦 Estrai salvataggi da QCOW2")
        print("2. 💉 Inietta salvataggi in QCOW2") 
        print("3. 🔍 Confronta due aree")
        print("0. ❌ Esci")
        
        choice = input("Scelta: ").strip()
        
        if choice == "1":
            qcow2_file = input("File QCOW2 sorgente: ").strip()
            output_dir = input("Directory output (default: ./saves): ").strip() or "./saves"
            
            result = extract_saves_from_qcow2(qcow2_file, output_dir)
            if result:
                print("✅ Estrazione completata!")
        
        elif choice == "2":
            save_file = input("File area salvataggi (.bin): ").strip()
            metadata_file = input("File metadati (.json): ").strip()
            target_qcow2 = input("QCOW2 target: ").strip()
            
            if inject_saves_to_qcow2(save_file, metadata_file, target_qcow2):
                print("✅ Iniezione completata!")
        
        elif choice == "3":
            file1 = input("Primo file: ").strip()
            file2 = input("Secondo file: ").strip()
            compare_save_areas(file1, file2)
        
        elif choice == "0":
            break
        
        else:
            print("❌ Scelta non valida")

if __name__ == "__main__":
    main()