#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESTRAZIONE COMPLETA FINALE - Estrae tutto senza injection
"""

import os
import shutil
import zipfile
import hashlib
from datetime import datetime

def extract_complete_saves(hdd_path, output_dir):
    """Estrazione completa di tutti i salvataggi e partizioni."""
    print("🎯 ESTRAZIONE COMPLETA FINALE")
    print("="*60)
    
    if not os.path.exists(hdd_path):
        print(f"❌ HDD non trovato: {hdd_path}")
        return False
    
    # Crea directory di output con timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    final_output_dir = os.path.join(output_dir, f"complete_extraction_{timestamp}")
    os.makedirs(final_output_dir, exist_ok=True)
    
    print(f"📁 Output: {final_output_dir}")
    
    # STEP 1: Estrai area completa dei salvataggi (cluster principale)
    print(f"\n📋 STEP 1: AREA COMPLETA SALVATAGGI")
    
    # Dall'analisi precedente, i salvataggi sono tra 0x00443002 e 0x00463002
    save_area_start = 0x00440000  # Inizia un po' prima
    save_area_end = 0x00470000    # Finisce un po' dopo
    save_area_size = save_area_end - save_area_start
    
    with open(hdd_path, 'rb') as hdd:
        hdd.seek(save_area_start)
        save_area_data = hdd.read(save_area_size)
        
        save_area_file = os.path.join(final_output_dir, "complete_save_area.bin")
        with open(save_area_file, 'wb') as f:
            f.write(save_area_data)
        
        print(f"  ✅ Area salvataggi: {len(save_area_data):,} bytes")
        print(f"     Range: 0x{save_area_start:08x} - 0x{save_area_end:08x}")
    
    # STEP 2: Estrai ogni pattern individualmente
    print(f"\n📋 STEP 2: PATTERN INDIVIDUALI")
    
    patterns = [
        (0x00447002, "Mercenaries_ID_1", 1024),
        (0x0044b002, "Mercenaries_ID_2", 1024),
        (0x00443042, "UDATA_marker", 2048),
        (0x00443002, "TDATA_marker", 2048),
        (0x00463002, "SaveMeta_file", 2048)
    ]
    
    with open(hdd_path, 'rb') as hdd:
        for offset, name, size in patterns:
            # Estrai area intorno al pattern
            extract_start = offset - (size // 2)
            
            hdd.seek(extract_start)
            pattern_data = hdd.read(size)
            
            pattern_file = os.path.join(final_output_dir, f"{name}_0x{offset:08x}.bin")
            with open(pattern_file, 'wb') as f:
                f.write(pattern_data)
            
            # Verifica contenuto
            non_zero = sum(1 for b in pattern_data[:64] if b != 0)
            print(f"  ✅ {name}: {len(pattern_data)} bytes ({non_zero}/64 non-zero)")
    
    # STEP 3: Estrai settori critici del filesystem
    print(f"\n📋 STEP 3: SETTORI FILESYSTEM")
    
    # Settori importanti per Xbox FATX
    filesystem_sectors = [
        (0x00000000, 0x00010000, "QCOW2_Header"),
        (0x00080000, 0x00010000, "Partition_Table_Area"),
        (0x00160000, 0x00010000, "FATX_Partition_1"),
        (0x001f0000, 0x00010000, "FATX_Partition_2"),
        (0x00280000, 0x00010000, "FATX_Partition_3")
    ]
    
    with open(hdd_path, 'rb') as hdd:
        for start, size, name in filesystem_sectors:
            hdd.seek(start)
            sector_data = hdd.read(size)
            
            sector_file = os.path.join(final_output_dir, f"{name}_0x{start:08x}.bin")
            with open(sector_file, 'wb') as f:
                f.write(sector_data)
            
            # Calcola hash per identificazione
            sector_hash = hashlib.md5(sector_data).hexdigest()[:8]
            print(f"  ✅ {name}: {len(sector_data):,} bytes (hash: {sector_hash})")
    
    # STEP 4: Crea file di metadati
    print(f"\n📋 STEP 4: METADATI")
    
    metadata = {
        "extraction_date": datetime.now().isoformat(),
        "source_hdd": hdd_path,
        "hdd_size": os.path.getsize(hdd_path),
        "save_area": {
            "start": f"0x{save_area_start:08x}",
            "end": f"0x{save_area_end:08x}", 
            "size": save_area_size
        },
        "patterns": [
            {
                "name": name,
                "offset": f"0x{offset:08x}",
                "size": size
            }
            for offset, name, size in patterns
        ],
        "filesystem_sectors": [
            {
                "name": name,
                "start": f"0x{start:08x}",
                "size": size
            }
            for start, size, name in filesystem_sectors
        ]
    }
    
    import json
    metadata_file = os.path.join(final_output_dir, "extraction_metadata.json")
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"  ✅ Metadati salvati: extraction_metadata.json")
    
    # STEP 5: Crea script di injection per il futuro
    print(f"\n📋 STEP 5: SCRIPT INJECTION")
    
    injection_script = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script di injection generato automaticamente
Estrazione del {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

import os
import shutil

def inject_extracted_saves(target_hdd_path):
    """Inietta i salvataggi estratti nell'HDD target."""
    extraction_dir = r"{final_output_dir}"
    
    if not os.path.exists(target_hdd_path):
        print("❌ HDD target non trovato")
        return False
    
    # Backup
    backup_path = target_hdd_path + ".backup_injection"
    shutil.copy2(target_hdd_path, backup_path)
    print(f"🔄 Backup: {{backup_path}}")
    
    # Inietta area completa
    save_area_file = os.path.join(extraction_dir, "complete_save_area.bin")
    if os.path.exists(save_area_file):
        with open(save_area_file, 'rb') as f:
            save_data = f.read()
        
        with open(target_hdd_path, 'r+b') as hdd:
            hdd.seek({save_area_start})  # 0x{save_area_start:08x}
            hdd.write(save_data)
            hdd.flush()
        
        print(f"✅ Area salvataggi iniettata: {{len(save_data):,}} bytes")
        return True
    
    return False

if __name__ == "__main__":
    target_hdd = input("Percorso HDD target: ")
    inject_extracted_saves(target_hdd)
'''
    
    injection_script_file = os.path.join(final_output_dir, "inject_saves.py")
    with open(injection_script_file, 'w', encoding='utf-8') as f:
        f.write(injection_script)
    
    print(f"  ✅ Script injection: inject_saves.py")
    
    # STEP 6: Crea ZIP finale
    print(f"\n📋 STEP 6: ARCHIVIO FINALE")
    
    zip_file = os.path.join(output_dir, f"xbox_saves_complete_{timestamp}.zip")
    with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(final_output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, final_output_dir)
                zipf.write(file_path, arcname)
    
    zip_size = os.path.getsize(zip_file)
    print(f"  ✅ Archivio ZIP: {os.path.basename(zip_file)} ({zip_size:,} bytes)")
    
    # STEP 7: Riepilogo finale
    print(f"\n📊 ESTRAZIONE COMPLETATA")
    print(f"  📁 Directory: {final_output_dir}")
    print(f"  📦 Archivio: {zip_file}")
    print(f"  🔧 Script injection: {injection_script_file}")
    
    # Conta file estratti
    extracted_files = []
    for root, dirs, files in os.walk(final_output_dir):
        for file in files:
            if file.endswith('.bin'):
                extracted_files.append(file)
    
    print(f"  📄 File estratti: {len(extracted_files)}")
    
    return True

def main():
    hdd_path = r"D:\xemu\xbox_hdd.qcow2"
    output_dir = r"D:\xbox_final_backup"
    
    success = extract_complete_saves(hdd_path, output_dir)
    
    if success:
        print(f"\n✅ ESTRAZIONE COMPLETA TERMINATA!")
        print(f"Ora hai un backup completo di tutti i salvataggi e partizioni.")
        print(f"Puoi usare lo script generato per iniettare in futuro.")
    else:
        print(f"\n❌ Estrazione fallita")

if __name__ == "__main__":
    main()