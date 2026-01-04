#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RIPRISTINO AREE FILESYSTEM - Ripristina aree critiche del filesystem FATX
"""

import os

def restore_filesystem_areas():
    """Ripristina le aree critiche del filesystem dall'HDD sano."""
    print("🔧 RIPRISTINO AREE FILESYSTEM")
    print("="*60)
    
    sano_path = r"D:\xemu\bk\xbox_hdd2.qcow2"
    corrotto_path = r"D:\xemu\xbox_hdd.qcow2"
    
    print(f"📁 Sorgente (SOLO LETTURA): {sano_path}")
    print(f"📁 Destinazione: {corrotto_path}")
    
    # Aree critiche del filesystem FATX da ripristinare
    critical_areas = [
        # Area salvataggi completa
        (0x00440000, 0x00030000, "Save_Area_Complete"),
        
        # Tabelle di allocazione FATX
        (0x00080000, 0x00010000, "Partition_Table"),
        (0x00160000, 0x00010000, "FATX_Partition_1"),
        (0x001f0000, 0x00010000, "FATX_Partition_2"), 
        (0x00280000, 0x00010000, "FATX_Partition_3"),
        
        # Directory entries e metadata
        (0x00300000, 0x00020000, "Directory_Metadata"),
        (0x00320000, 0x00020000, "File_Allocation_Tables"),
        
        # Aree aggiuntive che potrebbero contenere filesystem metadata
        (0x00070000, 0x00010000, "Pre_Partition_Area"),
        (0x00340000, 0x00020000, "Extended_Metadata"),
    ]
    
    restored_areas = 0
    
    try:
        with open(sano_path, 'rb') as sano, open(corrotto_path, 'r+b') as corrotto:
            print(f"\n🔧 Ripristino aree critiche:")
            
            for start, size, name in critical_areas:
                # Leggi dall'HDD sano
                sano.seek(start)
                sano_data = sano.read(size)
                
                if len(sano_data) == size:
                    # Scrivi nell'HDD corrotto
                    corrotto.seek(start)
                    corrotto.write(sano_data)
                    
                    restored_areas += 1
                    print(f"  ✅ {name}: {size:,} bytes ripristinati")
                else:
                    print(f"  ❌ {name}: Errore lettura ({len(sano_data)}/{size} bytes)")
            
            corrotto.flush()
            os.fsync(corrotto.fileno())
        
        print(f"\n📊 RIPRISTINO COMPLETATO:")
        print(f"  - Aree ripristinate: {restored_areas}/{len(critical_areas)}")
        
        return restored_areas > 0
    
    except Exception as e:
        print(f"❌ Errore durante ripristino: {e}")
        return False

def verify_restoration():
    """Verifica che il ripristino sia andato a buon fine."""
    print(f"\n🔍 VERIFICA RIPRISTINO")
    
    sano_path = r"D:\xemu\bk\xbox_hdd.qcow2"
    corrotto_path = r"D:\xemu\xbox_hdd.qcow2"
    
    # Verifica pattern di salvataggio
    patterns = {
        b'4c410015': 'Mercenaries_ID',
        b'JAC01': 'Save_JAC01',
        b'UDATA': 'UDATA_marker',
        b'TDATA': 'TDATA_marker'
    }
    
    with open(corrotto_path, 'rb') as f:
        f.seek(0x00440000)
        save_area = f.read(0x00030000)
        
        verified_patterns = 0
        for pattern, name in patterns.items():
            if pattern in save_area:
                pos = save_area.find(pattern)
                abs_pos = 0x00440000 + pos
                print(f"  ✅ {name}: Trovato a 0x{abs_pos:08x}")
                verified_patterns += 1
            else:
                print(f"  ❌ {name}: NON TROVATO")
    
    print(f"📊 Pattern verificati: {verified_patterns}/{len(patterns)}")
    return verified_patterns == len(patterns)

def main():
    print("🎮 RIPRISTINO FILESYSTEM XBOX")
    print("="*60)
    
    # Ripristina aree critiche
    success = restore_filesystem_areas()
    
    if success:
        # Verifica ripristino
        verified = verify_restoration()
        
        if verified:
            print("\n✅ RIPRISTINO COMPLETATO E VERIFICATO!")
            print("🎮 Ora testa xemu per vedere se i salvataggi sono tornati!")
        else:
            print("\n⚠️  Ripristino completato ma verifica fallita")
    else:
        print("\n❌ Ripristino fallito")

if __name__ == "__main__":
    main()