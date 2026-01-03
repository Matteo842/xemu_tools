#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST QCOW2 DIRECT - Test rapido del nuovo sistema
"""

import os
from pathlib import Path
from simple_qcow2_reader import SimpleQCOW2, extract_saves_from_qcow2, inject_saves_to_qcow2

def test_extraction():
    """Test estrazione rapida."""
    print("🧪 TEST ESTRAZIONE DIRETTA")
    print("="*40)
    
    # File di test
    qcow2_sano = r"D:\xemu\bk\xbox_hdd2.qcow2"  # Quello che funziona
    
    if not Path(qcow2_sano).exists():
        print(f"❌ File non trovato: {qcow2_sano}")
        return False
    
    # Estrai con metodo diretto
    result = extract_saves_from_qcow2(qcow2_sano, "./test_extraction")
    
    if result:
        save_file, metadata_file = result
        print(f"✅ Test estrazione OK!")
        print(f"  📄 {save_file}")
        print(f"  📋 {metadata_file}")
        return save_file, metadata_file
    else:
        print(f"❌ Test estrazione FALLITO")
        return None

def test_injection(save_file, metadata_file):
    """Test iniezione rapida."""
    print("\n🧪 TEST INIEZIONE DIRETTA")
    print("="*40)
    
    # File target
    qcow2_target = r"D:\xemu\xbox_hdd.qcow2"
    
    if not Path(qcow2_target).exists():
        print(f"❌ File target non trovato: {qcow2_target}")
        return False
    
    # Conferma
    print(f"⚠️  ATTENZIONE: Modificherò {Path(qcow2_target).name}")
    confirm = input("Procedere? (s/N): ").strip().lower()
    
    if confirm != 's':
        print("❌ Test annullato")
        return False
    
    # Inietta
    success = inject_saves_to_qcow2(save_file, metadata_file, qcow2_target)
    
    if success:
        print(f"✅ Test iniezione OK!")
        return True
    else:
        print(f"❌ Test iniezione FALLITO")
        return False

def test_pattern_detection():
    """Test rilevamento pattern."""
    print("\n🧪 TEST RILEVAMENTO PATTERN")
    print("="*40)
    
    qcow2_files = [
        r"D:\xemu\bk\xbox_hdd1.qcow2",  # Solo Mercenaries
        r"D:\xemu\bk\xbox_hdd2.qcow2",  # Funzionante
        r"D:\xemu\xbox_hdd.qcow2"       # Nostro
    ]
    
    for qcow2_file in qcow2_files:
        if not Path(qcow2_file).exists():
            continue
        
        print(f"\n📋 Analisi: {Path(qcow2_file).name}")
        
        try:
            with SimpleQCOW2(qcow2_file) as qcow2:
                areas = qcow2.smart_find_xbox_saves()
                
                if areas:
                    print(f"  ✅ Trovati {len(areas)} pattern:")
                    for area in areas:
                        print(f"    - {area['pattern']}: 0x{area['file_offset']:08x}")
                else:
                    print(f"  ❌ Nessun pattern trovato")
        
        except Exception as e:
            print(f"  ❌ Errore: {e}")

def quick_comparison_test():
    """Test confronto rapido."""
    print("\n🧪 TEST CONFRONTO RAPIDO")
    print("="*40)
    
    # Estrai da entrambi i file e confronta
    files_to_compare = [
        r"D:\xemu\bk\xbox_hdd2.qcow2",  # Funzionante
        r"D:\xemu\xbox_hdd.qcow2"       # Nostro
    ]
    
    extracted_files = []
    
    for i, qcow2_file in enumerate(files_to_compare):
        if not Path(qcow2_file).exists():
            continue
        
        print(f"\n📦 Estrazione {i+1}: {Path(qcow2_file).name}")
        result = extract_saves_from_qcow2(qcow2_file, f"./comparison_test_{i+1}")
        
        if result:
            extracted_files.append(result[0])  # Solo il file .bin
    
    # Confronta se abbiamo almeno 2 file
    if len(extracted_files) >= 2:
        print(f"\n🔍 Confronto diretto:")
        from simple_qcow2_reader import compare_save_areas
        compare_save_areas(extracted_files[0], extracted_files[1])
    else:
        print(f"❌ Non abbastanza file per confronto")

def main():
    """Test completo del sistema."""
    print("🧪 TEST COMPLETO SISTEMA QCOW2 DIRETTO")
    print("="*60)
    
    # Test 1: Rilevamento pattern
    test_pattern_detection()
    
    # Test 2: Estrazione
    extraction_result = test_extraction()
    
    if extraction_result:
        save_file, metadata_file = extraction_result
        
        # Test 3: Iniezione (opzionale)
        print(f"\n❓ Vuoi testare anche l'iniezione?")
        test_inject = input("ATTENZIONE: Modificherà il file target! (s/N): ").strip().lower()
        
        if test_inject == 's':
            test_injection(save_file, metadata_file)
    
    # Test 4: Confronto rapido
    quick_comparison_test()
    
    print(f"\n🎯 TEST COMPLETATI!")
    print(f"Se tutto è andato bene, ora hai un sistema funzionante!")

if __name__ == "__main__":
    main()