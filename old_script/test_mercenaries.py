#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST MERCENARIES - Test rapido estrazione/iniezione Mercenaries
"""

from xbox_game_extractor import XboxGameExtractor
from pathlib import Path

def test_mercenaries_extraction():
    """Test estrazione solo Mercenaries."""
    print("🧪 TEST ESTRAZIONE MERCENARIES")
    print("="*40)
    
    # File sorgente (HDD funzionante)
    source_qcow2 = r"D:\xemu\bk\xbox_hdd2.qcow2"
    
    if not Path(source_qcow2).exists():
        print(f"❌ File sorgente non trovato: {source_qcow2}")
        return None
    
    # Estrai solo Mercenaries
    extractor = XboxGameExtractor()
    result = extractor.extract_game(source_qcow2, "mercenaries", "./mercenaries_test")
    
    if result:
        area_file, metadata_file = result
        print(f"\n✅ MERCENARIES ESTRATTO:")
        print(f"  📄 Area: {area_file}")
        print(f"  📋 Metadati: {metadata_file}")
        return area_file, metadata_file
    else:
        print(f"❌ Estrazione Mercenaries fallita")
        return None

def test_mercenaries_injection(area_file, metadata_file):
    """Test iniezione solo Mercenaries."""
    print(f"\n🧪 TEST INIEZIONE MERCENARIES")
    print("="*40)
    
    # File target
    target_qcow2 = r"D:\xemu\xbox_hdd.qcow2"
    
    if not Path(target_qcow2).exists():
        print(f"❌ File target non trovato: {target_qcow2}")
        return False
    
    print(f"⚠️  ATTENZIONE: Modificherò {Path(target_qcow2).name}")
    print(f"Iniettando solo i dati di Mercenaries...")
    
    confirm = input("Procedere? (s/N): ").strip().lower()
    if confirm != 's':
        print("❌ Test annullato")
        return False
    
    # Inietta
    extractor = XboxGameExtractor()
    success = extractor.inject_game(area_file, metadata_file, target_qcow2)
    
    if success:
        print(f"✅ MERCENARIES INIETTATO!")
        print(f"Ora testa xemu per vedere se Mercenaries funziona")
        return True
    else:
        print(f"❌ Iniezione Mercenaries fallita")
        return False

def compare_mercenaries_areas():
    """Confronta aree Mercenaries tra HDD diversi."""
    print(f"\n🧪 CONFRONTO AREE MERCENARIES")
    print("="*40)
    
    extractor = XboxGameExtractor()
    
    # Estrai da HDD funzionante
    print("📦 Estrazione da HDD funzionante...")
    result1 = extractor.extract_game(r"D:\xemu\bk\xbox_hdd2.qcow2", "mercenaries", "./compare_test/hdd2")
    
    # Estrai da HDD corrente
    print("📦 Estrazione da HDD corrente...")
    result2 = extractor.extract_game(r"D:\xemu\xbox_hdd.qcow2", "mercenaries", "./compare_test/current")
    
    if result1 and result2:
        area1, _ = result1
        area2, _ = result2
        
        # Confronta
        with open(area1, 'rb') as f1, open(area2, 'rb') as f2:
            data1 = f1.read()
            data2 = f2.read()
        
        if data1 == data2:
            print("✅ Aree Mercenaries IDENTICHE!")
        else:
            differences = sum(1 for a, b in zip(data1, data2) if a != b)
            diff_percent = (differences / len(data1)) * 100
            print(f"❌ Aree diverse: {differences:,} byte ({diff_percent:.2f}%)")

def main():
    """Test completo Mercenaries."""
    print("🎮 TEST COMPLETO MERCENARIES")
    print("="*50)
    
    # Test 1: Estrazione
    result = test_mercenaries_extraction()
    
    if result:
        area_file, metadata_file = result
        
        # Test 2: Confronto (opzionale)
        print(f"\n❓ Vuoi confrontare le aree Mercenaries?")
        if input("(s/N): ").strip().lower() == 's':
            compare_mercenaries_areas()
        
        # Test 3: Iniezione (opzionale)
        print(f"\n❓ Vuoi testare l'iniezione?")
        if input("ATTENZIONE: Modificherà il file target! (s/N): ").strip().lower() == 's':
            test_mercenaries_injection(area_file, metadata_file)
    
    print(f"\n🎯 TEST MERCENARIES COMPLETATO!")

if __name__ == "__main__":
    main()