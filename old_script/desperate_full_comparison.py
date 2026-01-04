#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFRONTO DISPERATO COMPLETO - Ultima analisi byte per byte di tutto l'HDD
"""

import os

def desperate_full_hdd_comparison():
    """Confronto completo byte per byte di tutto l'HDD."""
    print("🔍 CONFRONTO DISPERATO COMPLETO")
    print("=" * 60)
    print("Confronto byte per byte di TUTTO l'HDD per trovare")
    print("qualsiasi differenza che ci sia sfuggita...")
    
    hdd_working = r"D:\xemu\bk\xbox_hdd2.qcow2"  # Funzionante
    hdd_current = r"D:\xemu\xbox_hdd.qcow2"      # Nostro tentativo
    
    print(f"📁 HDD funzionante: {os.path.basename(hdd_working)}")
    print(f"📁 HDD corrente: {os.path.basename(hdd_current)}")
    
    # Confronto in chunk grandi per velocità
    chunk_size = 1024 * 1024  # 1MB
    total_differences = 0
    different_chunks = []
    
    with open(hdd_working, 'rb') as f1, open(hdd_current, 'rb') as f2:
        offset = 0
        chunk_num = 0
        
        print(f"\n🔍 Scansione completa in corso...")
        
        while True:
            chunk1 = f1.read(chunk_size)
            chunk2 = f2.read(chunk_size)
            
            if not chunk1:  # Fine file
                break
            
            if chunk1 != chunk2:
                # Conta differenze in questo chunk
                chunk_diffs = sum(1 for a, b in zip(chunk1, chunk2) if a != b)
                total_differences += chunk_diffs
                
                different_chunks.append({
                    'offset': offset,
                    'chunk_num': chunk_num,
                    'differences': chunk_diffs,
                    'size': len(chunk1)
                })
                
                print(f"  ❌ Chunk {chunk_num} (0x{offset:08x}): {chunk_diffs} byte diversi")
            
            offset += len(chunk1)
            chunk_num += 1
            
            # Progress ogni 100MB
            if chunk_num % 100 == 0:
                progress_mb = offset // (1024 * 1024)
                print(f"  📊 Progresso: {progress_mb}MB scansionati...")
    
    print(f"\n📊 RISULTATI FINALI:")
    print(f"  Chunk diversi: {len(different_chunks)}")
    print(f"  Differenze totali: {total_differences} byte")
    
    if total_differences == 0:
        print(f"\n🤯 FILE COMPLETAMENTE IDENTICI!")
        print(f"Il problema NON è nei dati - è altrove!")
        
        print(f"\n💡 POSSIBILI CAUSE:")
        print(f"1. 🐛 Bug in xemu con questo specifico gioco")
        print(f"2. 🔧 Cache corrotta di xemu")
        print(f"3. 📁 Problema di permessi/lock sul file")
        print(f"4. ⚙️  Configurazione xemu errata")
        print(f"5. 🎮 ToeJam & Earl III ha protezioni speciali")
        
        return True  # File identici
    
    else:
        print(f"\n❌ ANCORA {total_differences} DIFFERENZE!")
        
        # Mostra i chunk più problematici
        different_chunks.sort(key=lambda x: x['differences'], reverse=True)
        
        print(f"\n🔍 CHUNK PIÙ PROBLEMATICI:")
        for i, chunk in enumerate(different_chunks[:5]):
            offset = chunk['offset']
            diffs = chunk['differences']
            print(f"  [{i+1}] 0x{offset:08x}: {diffs} byte diversi")
        
        return False  # Ancora differenze

def suggest_final_solutions():
    """Suggerisce le soluzioni finali."""
    print(f"\n🎯 SOLUZIONI FINALI")
    print("-" * 50)
    
    print(f"Se i file sono identici ma ToeJam non funziona:")
    print(f"")
    print(f"1. 🔄 RIAVVIA XEMU COMPLETAMENTE")
    print(f"   - Chiudi xemu")
    print(f"   - Cancella cache/temp di xemu")
    print(f"   - Riavvia")
    print(f"")
    print(f"2. 🔧 PROVA COPIA DIRETTA")
    print(f"   copy \"D:\\xemu\\bk\\xbox_hdd2.qcow2\" \"D:\\xemu\\xbox_hdd.qcow2\"")
    print(f"")
    print(f"3. 📋 CONTROLLA LOG XEMU")
    print(f"   - Avvia xemu da console")
    print(f"   - Guarda se ci sono errori specifici")
    print(f"")
    print(f"4. 🎮 TESTA ALTRI GIOCHI")
    print(f"   - Prova con un terzo gioco")
    print(f"   - Vedi se il problema è specifico di ToeJam")
    print(f"")
    print(f"5. 💔 ACCETTA LA SCONFITTA")
    print(f"   - ToeJam & Earl III potrebbe essere 'speciale'")
    print(f"   - Concentrati su Mercenaries che funziona")
    print(f"   - Espandi gradualmente con altri giochi")

def main():
    print("🔍 ANALISI DISPERATA FINALE")
    print("=" * 60)
    print("Ultima chance: confronto completo di tutto l'HDD")
    
    # Confronto completo
    files_identical = desperate_full_hdd_comparison()
    
    # Suggerimenti finali
    suggest_final_solutions()
    
    if files_identical:
        print(f"\n🤯 CONCLUSIONE: I FILE SONO IDENTICI!")
        print(f"Il problema è in xemu, non nei dati.")
    else:
        print(f"\n😤 CONCLUSIONE: CI SONO ANCORA DIFFERENZE!")
        print(f"Dobbiamo trovarle e correggerle.")

if __name__ == "__main__":
    main()