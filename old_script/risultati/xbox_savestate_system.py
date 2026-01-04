#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XBOX SAVESTATE SYSTEM - Sistema completo di backup/ripristino per SaveState
"""

import os
import json
import hashlib
import zipfile
from datetime import datetime

class XboxSaveStateManager:
    """Gestore completo dei salvataggi Xbox per SaveState."""
    
    def __init__(self, hdd_path):
        self.hdd_path = hdd_path
        
        # Aree critiche per il funzionamento dei salvataggi Xbox
        self.critical_areas = [
            # Area principale salvataggi
            (0x00440000, 0x00030000, "save_area_main", "Area principale salvataggi"),
            
            # Tabelle FATX critiche (FONDAMENTALI per evitare "damaged")
            (0x00080000, 0x00010000, "partition_table", "Tabella partizioni"),
            (0x00160000, 0x00010000, "fatx_partition_1", "Partizione FATX 1"),
            (0x001f0000, 0x00010000, "fatx_partition_2", "Partizione FATX 2"), 
            (0x00280000, 0x00010000, "fatx_partition_3", "Partizione FATX 3"),
            
            # Metadati directory e allocazione file
            (0x00300000, 0x00020000, "directory_metadata", "Metadati directory"),
            (0x00320000, 0x00020000, "file_allocation", "Tabelle allocazione file"),
            
            # Aree estese che potrebbero contenere salvataggi
            (0x00470000, 0x00010000, "save_area_extended", "Area salvataggi estesa"),
        ]
    
    def extract_save_data(self, output_dir):
        """Estrae tutti i dati necessari per il backup."""
        print("📦 ESTRAZIONE DATI SALVATAGGIO XBOX")
        print("=" * 60)
        
        if not os.path.exists(self.hdd_path):
            print(f"❌ HDD non trovato: {self.hdd_path}")
            return False
        
        # Crea directory di output
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(output_dir, f"xbox_backup_{timestamp}")
        os.makedirs(backup_dir, exist_ok=True)
        
        print(f"📁 Directory backup: {backup_dir}")
        
        extracted_files = []
        metadata = {
            "extraction_date": datetime.now().isoformat(),
            "source_hdd": self.hdd_path,
            "hdd_size": os.path.getsize(self.hdd_path),
            "areas": []
        }
        
        with open(self.hdd_path, 'rb') as hdd:
            for offset, size, name, description in self.critical_areas:
                print(f"\n📋 Estrazione {description}...")
                
                # Leggi area
                hdd.seek(offset)
                area_data = hdd.read(size)
                
                if len(area_data) == size:
                    # Salva in file
                    area_file = os.path.join(backup_dir, f"{name}.bin")
                    with open(area_file, 'wb') as f:
                        f.write(area_data)
                    
                    # Calcola hash per verifica integrità
                    area_hash = hashlib.sha256(area_data).hexdigest()
                    
                    # Verifica se contiene dati significativi
                    non_zero_bytes = sum(1 for b in area_data if b != 0)
                    data_density = (non_zero_bytes / len(area_data)) * 100
                    
                    extracted_files.append(area_file)
                    metadata["areas"].append({
                        "name": name,
                        "description": description,
                        "offset": f"0x{offset:08x}",
                        "size": size,
                        "hash": area_hash,
                        "data_density": f"{data_density:.1f}%",
                        "file": f"{name}.bin"
                    })
                    
                    print(f"  ✅ {description}: {size:,} bytes ({data_density:.1f}% dati)")
                else:
                    print(f"  ❌ {description}: Errore lettura")
        
        # Salva metadati
        metadata_file = os.path.join(backup_dir, "backup_metadata.json")
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Crea archivio ZIP
        zip_file = os.path.join(output_dir, f"xbox_savestate_{timestamp}.zip")
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(backup_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, backup_dir)
                    zipf.write(file_path, arcname)
        
        print(f"\n📊 ESTRAZIONE COMPLETATA:")
        print(f"  📁 Directory: {backup_dir}")
        print(f"  📦 Archivio: {zip_file}")
        print(f"  📄 Aree estratte: {len(extracted_files)}")
        print(f"  💾 Dimensione totale: {sum(area['size'] for area in metadata['areas']):,} bytes")
        
        return {
            "backup_dir": backup_dir,
            "zip_file": zip_file,
            "metadata": metadata
        }
    
    def restore_save_data(self, backup_source):
        """Ripristina i dati da backup (directory o ZIP)."""
        print("🔧 RIPRISTINO DATI SALVATAGGIO XBOX")
        print("=" * 60)
        
        # Determina se è directory o ZIP
        if os.path.isdir(backup_source):
            backup_dir = backup_source
        elif backup_source.endswith('.zip'):
            # Estrai ZIP temporaneamente
            import tempfile
            backup_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(backup_source, 'r') as zipf:
                zipf.extractall(backup_dir)
            print(f"📦 Estratto ZIP in: {backup_dir}")
        else:
            print(f"❌ Formato backup non riconosciuto: {backup_source}")
            return False
        
        # Leggi metadati
        metadata_file = os.path.join(backup_dir, "backup_metadata.json")
        if not os.path.exists(metadata_file):
            print(f"❌ Metadati backup non trovati: {metadata_file}")
            return False
        
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        print(f"📋 Backup del: {metadata['extraction_date']}")
        print(f"📁 HDD target: {self.hdd_path}")
        
        # Backup HDD corrente
        backup_hdd = f"{self.hdd_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        import shutil
        shutil.copy2(self.hdd_path, backup_hdd)
        print(f"🔄 Backup HDD corrente: {os.path.basename(backup_hdd)}")
        
        # Ripristina ogni area
        restored_areas = 0
        
        try:
            with open(self.hdd_path, 'r+b') as hdd:
                for area_info in metadata["areas"]:
                    area_file = os.path.join(backup_dir, area_info["file"])
                    
                    if os.path.exists(area_file):
                        print(f"\n🔧 Ripristino {area_info['description']}...")
                        
                        # Leggi dati backup
                        with open(area_file, 'rb') as f:
                            area_data = f.read()
                        
                        # Verifica hash per integrità
                        current_hash = hashlib.sha256(area_data).hexdigest()
                        if current_hash == area_info["hash"]:
                            # Scrivi nell'HDD
                            offset = int(area_info["offset"], 16)
                            hdd.seek(offset)
                            hdd.write(area_data)
                            
                            restored_areas += 1
                            print(f"  ✅ {area_info['description']}: {len(area_data):,} bytes ripristinati")
                        else:
                            print(f"  ❌ {area_info['description']}: Hash non corrispondente (file corrotto?)")
                    else:
                        print(f"  ❌ {area_info['description']}: File non trovato")
                
                # Forza scrittura
                hdd.flush()
                os.fsync(hdd.fileno())
        
        except Exception as e:
            print(f"\n❌ Errore durante ripristino: {e}")
            # Ripristina backup in caso di errore
            shutil.copy2(backup_hdd, self.hdd_path)
            print(f"🔄 HDD ripristinato da backup")
            return False
        
        print(f"\n📊 RIPRISTINO COMPLETATO:")
        print(f"  ✅ Aree ripristinate: {restored_areas}/{len(metadata['areas'])}")
        
        return restored_areas == len(metadata["areas"])
    
    def verify_save_integrity(self):
        """Verifica l'integrità dei salvataggi dopo il ripristino."""
        print(f"\n🔍 VERIFICA INTEGRITÀ SALVATAGGI")
        
        # Pattern Xbox da verificare
        patterns = {
            b'4c410015': 'Mercenaries_ID',
            b'JAC01': 'Save_JAC01',
            b'UDATA': 'Universal_Data',
            b'TDATA': 'Title_Data',
            b'FATX': 'FATX_Signature'
        }
        
        found_patterns = 0
        
        with open(self.hdd_path, 'rb') as f:
            # Verifica area salvataggi
            f.seek(0x00440000)
            save_area = f.read(0x00080000)  # 512KB
            
            for pattern, name in patterns.items():
                if pattern in save_area:
                    pos = save_area.find(pattern)
                    abs_pos = 0x00440000 + pos
                    print(f"  ✅ {name}: Trovato a 0x{abs_pos:08x}")
                    found_patterns += 1
                else:
                    print(f"  ❌ {name}: NON TROVATO")
        
            # Verifica tabelle FATX
            f.seek(0x00160000)
            fatx_data = f.read(16)
            if b'FATX' in fatx_data:
                print(f"  ✅ FATX_Signature: Tabelle filesystem OK")
                found_patterns += 1
            else:
                print(f"  ❌ FATX_Signature: Tabelle filesystem danneggiate")
        
        success = found_patterns >= 3  # Almeno 3 pattern trovati
        
        if success:
            print(f"\n✅ INTEGRITÀ VERIFICATA!")
            print(f"I salvataggi dovrebbero funzionare correttamente in xemu.")
        else:
            print(f"\n⚠️  INTEGRITÀ DUBBIOSA!")
            print(f"Potrebbero esserci problemi con i salvataggi.")
        
        return success

def main():
    """Esempio di utilizzo del sistema SaveState Xbox."""
    print("🎮 XBOX SAVESTATE SYSTEM")
    print("=" * 60)
    
    hdd_path = r"D:\xemu\xbox_hdd.qcow2"  # HDD da riparare
    output_dir = r"D:\xbox_savestate_backups"
    
    # Crea directory output se non esiste
    os.makedirs(output_dir, exist_ok=True)
    
    manager = XboxSaveStateManager(hdd_path)
    
    print("Scegli operazione:")
    print("1. Estrai backup salvataggi")
    print("2. Ripristina da backup")
    print("3. Verifica integrità")
    
    # Per ora facciamo ripristino automatico
    choice = "2"
    
    if choice == "1":
        result = manager.extract_save_data(output_dir)
        if result:
            print(f"\n🎯 BACKUP CREATO CON SUCCESSO!")
            print(f"Usa questo file per ripristinare: {result['zip_file']}")
    
    elif choice == "2":
        # Trova ultimo backup
        backups = [f for f in os.listdir(output_dir) if f.endswith('.zip')]
        if backups:
            latest_backup = os.path.join(output_dir, sorted(backups)[-1])
            success = manager.restore_save_data(latest_backup)
            if success:
                manager.verify_save_integrity()
        else:
            print("❌ Nessun backup trovato")
    
    elif choice == "3":
        manager.verify_save_integrity()

if __name__ == "__main__":
    main()