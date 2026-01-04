#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFRONTO HDD - Confronta HDD sano vs corrotto
"""

import os
import hashlib

def compare_hdd_areas(sano_path, corrotto_path):
    """Confronta aree specifiche tra HDD sano e corrotto."""
    print("🔍 CONFRONTO HDD SANO VS CORROTTO")
    print("="*60)
    
    print(f"📁 HDD SANO (SOLO LETTURA): {sano_path}")
    print(f"📁 HDD CORROTTO: {corrotto_path}")
    
    if not os.path.exists(sano_path):
        print(f"❌ HDD sano non trovato: {sano_path}")
        return False
    
    if not os.path.exists(corrotto_path):
        print(f"❌ HDD corrotto non trovato: {corrotto_path}")
        return False
    
    # Aree critiche da confrontare
    critical_areas = [
        (0x00000000, 0x00010000, "QCOW2_Header"),
        (0x00440000, 0x00030000, "Save_Area_Complete"),
        (0x00447000, 0x00001000, "Mercenaries_ID_Area"),
        (0x00443000, 0x00001000, "UDATA_TDATA_Area"),
        (0x00463000, 0x00001000, "SaveMeta_Area"),
        (0x00080000, 0x00010000, "Partition_Table"),
        (0x00160000, 0x00010000, "FATX_Partition_1"),
    ]
    
    differences = []
    
    with open(sano_path, 'rb') as sano, open(corrotto_path, 'rb') as corrotto:
        print(f"\n📊 CONFRONTO AREE CRITICHE:")
        
        for start, size, name in critical_areas:
            # Leggi da HDD sano
            sano.seek(start)
            sano_data = sano.read(size)
            
            # Leggi da HDD corrotto
            corrotto.seek(start)
            corrotto_data = corrotto.read(size)
            
            # Confronta
            if sano_data == corrotto_data:
                print(f"  ✅ {name}: IDENTICO")
            else:
                print(f"  ❌ {name}: DIVERSO")
                
                # Calcola hash per identificare differenze
                sano_hash = hashlib.md5(sano_data).hexdigest()[:8]
                corrotto_hash = hashlib.md5(corrotto_data).hexdigest()[:8]
                
                print(f"      Sano: {sano_hash} | Corrotto: {corrotto_hash}")
                
                # Conta bytes diversi
                diff_bytes = sum(1 for a, b in zip(sano_data, corrotto_data) if a != b)
                diff_percent = (diff_bytes / len(sano_data)) * 100
                
                print(f"      Differenze: {diff_bytes}/{len(sano_data)} bytes ({diff_percent:.1f}%)")
                
                differences.append({
                    'name': name,
                    'start': start,
                    'size': size,
                    'diff_bytes': diff_bytes,
                    'diff_percent': diff_percent
                })
    
    # Analisi dettagliata delle differenze più importanti
    if differences:
        print(f"\n🔍 ANALISI DETTAGLIATA DIFFERENZE:")
        
        for diff in differences:
            if diff['diff_percent'] > 1:  # Solo differenze significative
                print(f"\n📋 {diff['name']}:")
                print(f"  Offset: 0x{diff['start']:08x}")
                print(f"  Differenze: {diff['diff_percent']:.1f}%")
                
                # Mostra primi bytes diversi
                with open(sano_path, 'rb') as sano, open(corrotto_path, 'rb') as corrotto:
                    sano.seek(diff['start'])
                    corrotto.seek(diff['start'])
                    
                    sano_sample = sano.read(64)
                    corrotto_sample = corrotto.read(64)
                    
                    print(f"  Sano (primi 64 bytes):")
                    print(f"    {sano_sample.hex()[:32]}...")
                    print(f"  Corrotto (primi 64 bytes):")
                    print(f"    {corrotto_sample.hex()[:32]}...")
    
    return len(differences)

def find_save_patterns(hdd_path, label):
    """Trova pattern di salvataggio in un HDD."""
    print(f"\n🔍 PATTERN SALVATAGGI - {label}")
    
    patterns = {
        b'4c410015': 'Mercenaries_ID',
        b'JAC01': 'Save_JAC01',
        b'UDATA': 'UDATA_marker',
        b'TDATA': 'TDATA_marker',
        b'SaveMeta.xbx': 'SaveMeta_file'
    }
    
    found_patterns = {}
    
    with open(hdd_path, 'rb') as f:
        # Cerca nell'area dei salvataggi
        f.seek(0x00440000)
        save_area = f.read(0x00030000)  # 192KB
        
        for pattern, name in patterns.items():
            pos = save_area.find(pattern)
            if pos != -1:
                abs_pos = 0x00440000 + pos
                found_patterns[name] = abs_pos
                print(f"  ✅ {name}: 0x{abs_pos:08x}")
            else:
                print(f"  ❌ {name}: NON TROVATO")
    
    return found_patterns

def main():
    # Percorsi - usa il file che finisce con 1 (solo Mercenaries)
    sano_path = r"D:\xemu\bk\xbox_hdd1.qcow2"
    corrotto_path = r"D:\xemu\xbox_hdd.qcow2"
    
    print("🔬 ANALISI COMPARATIVA HDD")
    print("="*60)
    
    # Confronta aree critiche
    diff_count = compare_hdd_areas(sano_path, corrotto_path)
    
    # Trova pattern in entrambi
    sano_patterns = find_save_patterns(sano_path, "HDD SANO")
    corrotto_patterns = find_save_patterns(corrotto_path, "HDD CORROTTO")
    
    # Confronta pattern
    print(f"\n📊 CONFRONTO PATTERN:")
    all_patterns = set(sano_patterns.keys()) | set(corrotto_patterns.keys())
    
    for pattern in all_patterns:
        sano_pos = sano_patterns.get(pattern, "NON TROVATO")
        corrotto_pos = corrotto_patterns.get(pattern, "NON TROVATO")
        
        if sano_pos == corrotto_pos:
            print(f"  ✅ {pattern}: STESSO OFFSET ({sano_pos})")
        else:
            print(f"  ❌ {pattern}: DIVERSO")
            print(f"      Sano: {sano_pos}")
            print(f"      Corrotto: {corrotto_pos}")
    
    # Conclusioni
    print(f"\n🎯 CONCLUSIONI:")
    if diff_count == 0:
        print("  ✅ HDD identici - problema non nell'area dei salvataggi")
    else:
        print(f"  ⚠️  Trovate {diff_count} aree diverse")
        print("  🔧 Usa le informazioni sopra per correggere le differenze")

if __name__ == "__main__":
    main()