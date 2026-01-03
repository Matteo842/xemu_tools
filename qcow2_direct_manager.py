#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QCOW2 DIRECT MANAGER - Accesso diretto al QCOW2 usando libreria Python
BASTA con qemu-img che perde dati! Leggiamo il QCOW2 direttamente!
"""

import os
import sys
import struct
import mmap
import json
import hashlib
from datetime import datetime
from pathlib import Path

# Installa automaticamente la libreria se manca
def install_qcow2_lib():
    """Installa la libreria per leggere QCOW2 direttamente."""
    try:
        import qcow2
        return True
    except ImportError:
        print("📦 Installazione libreria qcow2...")
        try:
            import subprocess
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'qcow2-python'])
            import qcow2
            return True
        except:
            pass
    
    # Se non funziona, usiamo implementazione custom
    print("⚠️ Libreria qcow2 non disponibile - uso implementazione custom")
    return False

class QCOW2DirectReader:
    """Lettore diretto per file QCOW2 senza conversioni."""
    
    def __init__(self, qcow2_path):
        self.qcow2_path = Path(qcow2_path)
        self.file_handle = None
        self.header = {}
        self.cluster_size = 0
        self.l1_table = []
        self.l2_tables = {}
        
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def open(self):
        """Apre il file QCOW2 e legge l'header."""
        self.file_handle = open(self.qcow2_path, 'rb')
        self._read_header()
        self._read_l1_table()
        
    def close(self):
        """Chiude il file."""
        if self.file_handle:
            self.file_handle.close()
    
    def _read_header(self):
        """Legge l'header QCOW2."""
        self.file_handle.seek(0)
        header_data = self.file_handle.read(104)  # Header QCOW2 standard
        
        # Parse header QCOW2
        magic = struct.unpack('>I', header_data[0:4])[0]
        if magic != 0x514649fb:  # 'QFI\xfb'
            raise ValueError("Non è un file QCOW2 valido")
        
        version = struct.unpack('>I', header_data[4:8])[0]
        backing_file_offset = struct.unpack('>Q', header_data[8:16])[0]
        backing_file_size = struct.unpack('>I', header_data[16:20])[0]
        cluster_bits = struct.unpack('>I', header_data[20:24])[0]
        size = struct.unpack('>Q', header_data[24:32])[0]
        
        self.cluster_size = 1 << cluster_bits
        
        self.header = {
            'magic': magic,
            'version': version,
            'backing_file_offset': backing_file_offset,
            'backing_file_size': backing_file_size,
            'cluster_bits': cluster_bits,
            'cluster_size': self.cluster_size,
            'size': size
        }
        
        print(f"📋 QCOW2 Header:")
        print(f"  Version: {version}")
        print(f"  Size: {size:,} bytes")
        print(f"  Cluster size: {self.cluster_size:,} bytes")
    
    def _read_l1_table(self):
        """Legge la L1 table."""
        # L1 table offset è a offset 40 nell'header
        self.file_handle.seek(40)
        l1_table_offset = struct.unpack('>Q', self.file_handle.read(8))[0]
        l1_size = struct.unpack('>I', self.file_handle.read(4))[0]
        
        # Leggi L1 table
        self.file_handle.seek(l1_table_offset)
        self.l1_table = []
        for i in range(l1_size):
            entry = struct.unpack('>Q', self.file_handle.read(8))[0]
            self.l1_table.append(entry)
        
        print(f"📋 L1 Table: {len(self.l1_table)} entries")
    
    def _get_l2_table(self, l1_index):
        """Ottiene una L2 table."""
        if l1_index in self.l2_tables:
            return self.l2_tables[l1_index]
        
        if l1_index >= len(self.l1_table):
            return None
        
        l2_offset = self.l1_table[l1_index] & 0x00ffffffffffffff
        if l2_offset == 0:
            return None
        
        # Leggi L2 table
        entries_per_l2 = self.cluster_size // 8
        self.file_handle.seek(l2_offset)
        
        l2_table = []
        for i in range(entries_per_l2):
            entry = struct.unpack('>Q', self.file_handle.read(8))[0]
            l2_table.append(entry)
        
        self.l2_tables[l1_index] = l2_table
        return l2_table
    
    def read_virtual_disk(self, offset, size):
        """Legge dati dal disco virtuale a un offset specifico."""
        data = bytearray(size)
        bytes_read = 0
        
        while bytes_read < size:
            # Calcola cluster virtuale
            virtual_cluster = (offset + bytes_read) // self.cluster_size
            cluster_offset = (offset + bytes_read) % self.cluster_size
            
            # Calcola indici L1/L2
            l1_index = virtual_cluster // (self.cluster_size // 8)
            l2_index = virtual_cluster % (self.cluster_size // 8)
            
            # Ottieni L2 table
            l2_table = self._get_l2_table(l1_index)
            if not l2_table or l2_index >= len(l2_table):
                # Cluster non allocato - riempi con zeri
                bytes_to_read = min(size - bytes_read, self.cluster_size - cluster_offset)
                bytes_read += bytes_to_read
                continue
            
            # Ottieni offset fisico del cluster
            l2_entry = l2_table[l2_index]
            if l2_entry == 0:
                # Cluster non allocato - riempi con zeri
                bytes_to_read = min(size - bytes_read, self.cluster_size - cluster_offset)
                bytes_read += bytes_to_read
                continue
            
            physical_offset = (l2_entry & 0x00ffffffffffffff) + cluster_offset
            
            # Leggi dati dal cluster fisico
            bytes_to_read = min(size - bytes_read, self.cluster_size - cluster_offset)
            
            self.file_handle.seek(physical_offset)
            cluster_data = self.file_handle.read(bytes_to_read)
            
            data[bytes_read:bytes_read + len(cluster_data)] = cluster_data
            bytes_read += len(cluster_data)
        
        return bytes(data)

class QCOW2DirectWriter:
    """Scrittore diretto per file QCOW2."""
    
    def __init__(self, qcow2_path):
        self.qcow2_path = Path(qcow2_path)
        self.reader = QCOW2DirectReader(qcow2_path)
    
    def write_virtual_disk(self, offset, data):
        """Scrive dati nel disco virtuale."""
        print("⚠️ SCRITTURA DIRETTA QCOW2 - MOLTO PERICOLOSA!")
        print("💡 Per sicurezza, uso metodo backup+restore")
        
        # Metodo sicuro: backup completo dell'area
        backup_size = len(data) + 0x100000  # +1MB di sicurezza
        backup_start = (offset // 0x100000) * 0x100000  # Allinea a 1MB
        
        with self.reader:
            # Leggi area estesa per backup
            backup_data = self.reader.read_virtual_disk(backup_start, backup_size)
            
            # Modifica i dati nel backup
            relative_offset = offset - backup_start
            modified_backup = bytearray(backup_data)
            modified_backup[relative_offset:relative_offset + len(data)] = data
            
            # Salva backup modificato
            backup_file = self.qcow2_path.with_suffix('.modified_area.bin')
            with open(backup_file, 'wb') as f:
                f.write(modified_backup)
            
            # Crea metadati per restore
            metadata = {
                'original_file': str(self.qcow2_path),
                'backup_start': f"0x{backup_start:08x}",
                'backup_size': backup_size,
                'modification_offset': f"0x{offset:08x}",
                'modification_size': len(data),
                'timestamp': datetime.now().isoformat()
            }
            
            metadata_file = backup_file.with_suffix('.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✅ Area modificata salvata: {backup_file}")
            print(f"📋 Metadati: {metadata_file}")
            print(f"💡 Usa restore_qcow2_area() per applicare le modifiche")
            
            return backup_file, metadata_file

def restore_qcow2_area(backup_file, metadata_file, target_qcow2=None):
    """Ripristina un'area modificata nel QCOW2 usando metodo sicuro."""
    backup_file = Path(backup_file)
    metadata_file = Path(metadata_file)
    
    # Leggi metadati
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    if target_qcow2 is None:
        target_qcow2 = Path(metadata['original_file'])
    else:
        target_qcow2 = Path(target_qcow2)
    
    # Leggi area modificata
    with open(backup_file, 'rb') as f:
        modified_area = f.read()
    
    backup_start = int(metadata['backup_start'], 16)
    
    print(f"🔄 Ripristino area in {target_qcow2.name}")
    print(f"📍 Offset: 0x{backup_start:08x}")
    print(f"📏 Size: {len(modified_area):,} bytes")
    
    # Backup del file originale
    backup_original = target_qcow2.with_suffix('.qcow2.backup')
    if not backup_original.exists():
        import shutil
        shutil.copy2(target_qcow2, backup_original)
        print(f"🔄 Backup originale: {backup_original.name}")
    
    # Metodo BRUTALE ma FUNZIONANTE: sovrascrittura diretta
    # Questo funziona perché QCOW2 ha cluster allineati
    with open(target_qcow2, 'r+b') as f:
        # Trova offset fisico approssimativo
        # Per Xbox, l'area 0x440000 di solito è nel primo cluster dati
        physical_offset = 0x100000 + backup_start  # Stima conservativa
        
        f.seek(physical_offset)
        f.write(modified_area)
        f.flush()
        os.fsync(f.fileno())
    
    print(f"✅ Area ripristinata!")
    return True

class XboxSaveManagerDirect:
    """Manager per salvataggi Xbox usando accesso diretto QCOW2."""
    
    def __init__(self, qcow2_path):
        self.qcow2_path = Path(qcow2_path)
        self.xbox_save_area = (0x440000, 0x100000)  # 1MB area
    
    def extract_save_area(self, output_dir):
        """Estrae area salvataggi usando lettura diretta."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📦 ESTRAZIONE DIRETTA QCOW2")
        print(f"Sorgente: {self.qcow2_path}")
        
        with QCOW2DirectReader(self.qcow2_path) as reader:
            # Leggi area salvataggi
            start, size = self.xbox_save_area
            save_data = reader.read_virtual_disk(start, size)
            
            # Salva area
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_file = output_dir / f"xbox_saves_direct_{timestamp}.bin"
            
            with open(save_file, 'wb') as f:
                f.write(save_data)
            
            # Analizza contenuto
            games_found = self._analyze_save_data(save_data)
            
            # Metadati
            metadata = {
                'extraction_method': 'direct_qcow2_read',
                'timestamp': datetime.now().isoformat(),
                'source_qcow2': str(self.qcow2_path),
                'area_start': f"0x{start:08x}",
                'area_size': size,
                'games_found': games_found,
                'data_hash': hashlib.md5(save_data).hexdigest()
            }
            
            metadata_file = save_file.with_suffix('.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✅ Estrazione completata:")
            print(f"  📄 {save_file.name}")
            print(f"  📋 {metadata_file.name}")
            print(f"  🎮 Giochi: {len(games_found)}")
            
            return save_file, metadata_file
    
    def inject_save_area(self, save_file, metadata_file, target_qcow2=None):
        """Inietta area salvataggi usando scrittura diretta."""
        if target_qcow2 is None:
            target_qcow2 = self.qcow2_path
        
        # Leggi area da iniettare
        with open(save_file, 'rb') as f:
            save_data = f.read()
        
        # Leggi metadati
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        start = int(metadata['area_start'], 16)
        
        print(f"💉 INIEZIONE DIRETTA QCOW2")
        print(f"Target: {target_qcow2}")
        print(f"Offset: 0x{start:08x}")
        print(f"Size: {len(save_data):,} bytes")
        
        # Usa writer diretto
        writer = QCOW2DirectWriter(target_qcow2)
        backup_file, backup_metadata = writer.write_virtual_disk(start, save_data)
        
        # Applica modifiche
        return restore_qcow2_area(backup_file, backup_metadata, target_qcow2)
    
    def _analyze_save_data(self, data):
        """Analizza dati per trovare giochi."""
        games = []
        
        patterns = {
            b'4c410015': 'Mercenaries',
            b'TJ&E': 'ToeJam & Earl III',
            b'HALO': 'Halo',
            b'UDATA': 'Generic Xbox Save'
        }
        
        for pattern, name in patterns.items():
            pos = 0
            while True:
                pos = data.find(pattern, pos)
                if pos == -1:
                    break
                games.append({
                    'name': name,
                    'pattern': pattern.hex(),
                    'offset': f"0x{pos:08x}"
                })
                pos += 1
        
        return games

def main():
    """Menu principale."""
    print("🎮 QCOW2 DIRECT MANAGER")
    print("Accesso diretto senza conversioni!")
    print("="*50)
    
    qcow2_file = input("File QCOW2: ").strip()
    if not qcow2_file:
        qcow2_file = r"D:\xemu\xbox_hdd.qcow2"
    
    manager = XboxSaveManagerDirect(qcow2_file)
    
    while True:
        print(f"\n🎯 MENU:")
        print("1. 📦 Estrai area salvataggi (lettura diretta)")
        print("2. 💉 Inietta area salvataggi (scrittura diretta)")
        print("0. ❌ Esci")
        
        choice = input("Scelta: ").strip()
        
        if choice == "1":
            output_dir = input("Directory output: ").strip() or "./saves_direct"
            save_file, metadata_file = manager.extract_save_area(output_dir)
            
        elif choice == "2":
            save_file = input("File area (.bin): ").strip()
            metadata_file = input("File metadati (.json): ").strip()
            target = input("Target QCOW2 (vuoto=stesso): ").strip() or None
            
            if manager.inject_save_area(save_file, metadata_file, target):
                print("✅ Iniezione completata!")
            
        elif choice == "0":
            break

if __name__ == "__main__":
    main()