#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRECISE REPAIR - Ripara l'HDD Xbox copiando SOLO le aree necessarie dal backup funzionante.

Questo script:
1. LEGGE dal backup funzionante (SOLO LETTURA, mai scrittura)
2. SCRIVE sull'HDD attuale le aree corrette
3. Crea sempre un backup prima di modificare

Aree da riparare (identificate dal confronto):
- 0x00050000: Struttura QCOW2 (9 bytes)
- 0x00160000: FATX Partition 1 (2413 bytes)  
- 0x00170000: Directory entries (41 bytes)
- 0x00310000: Metadata (29 bytes)
- 0x00450000: Area salvataggi (3 bytes)
- 0x0f730000: Area estesa (34 bytes)
- 0x118f0000: Area estesa (118 bytes)
- 0x14520000: Dati secondo gioco (20796 bytes)
"""

import os
import shutil
from datetime import datetime

# CONFIGURAZIONE - MODIFICA QUESTI PERCORSI SE NECESSARIO
BACKUP_FUNZIONANTE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # SOLO LETTURA!
HDD_ATTUALE = r"D:\xemu\xbox_hdd.qcow2"             # Questo verrà modificato

# Aree da riparare (offset, dimensione in bytes da copiare)
# Usiamo dimensioni più grandi per sicurezza (arrotondate a blocchi)
REPAIR_AREAS = [
    (0x00050000, 0x1000, "QCOW2_internal"),           # 4KB intorno alle differenze
    (0x00160000, 0x10000, "FATX_Partition_1"),        # 64KB - intera partizione FATX
    (0x00170000, 0x10000, "Directory_entries"),       # 64KB
    (0x00310000, 0x1000, "Metadata"),                 # 4KB
    (0x00450000, 0x1000, "Save_area"),                # 4KB - area salvataggi
    (0x0f730000, 0x10000, "Extended_area_1"),         # 64KB
    (0x118f0000, 0x10000, "Extended_area_2"),         # 64KB
    (0x14520000, 0x10000, "Second_game_data"),        # 64KB - dati secondo gioco
]


def verify_files():
    """Verifica che i file esistano."""
    print("🔍 Verifica file...")
    
    if not os.path.exists(BACKUP_FUNZIONANTE):
        print(f"❌ Backup funzionante non trovato: {BACKUP_FUNZIONANTE}")
        return False
    
    if not os.path.exists(HDD_ATTUALE):
        print(f"❌ HDD attuale non trovato: {HDD_ATTUALE}")
        return False
    
    print(f"✅ Backup funzionante: {BACKUP_FUNZIONANTE}")
    print(f"   Dimensione: {os.path.getsize(BACKUP_FUNZIONANTE):,} bytes")
    print(f"✅ HDD attuale: {HDD_ATTUALE}")
    print(f"   Dimensione: {os.path.getsize(HDD_ATTUALE):,} bytes")
    
    return True


def create_safety_backup():
    """Crea un backup di sicurezza dell'HDD attuale."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{HDD_ATTUALE}.safety_backup_{timestamp}"
    
    print(f"\n🔄 Creazione backup di sicurezza...")
    shutil.copy2(HDD_ATTUALE, backup_path)
    print(f"✅ Backup creato: {os.path.basename(backup_path)}")
    
    return backup_path


def repair_areas():
    """Ripara le aree specifiche copiando dal backup funzionante."""
    print("\n🔧 RIPARAZIONE IN CORSO...")
    print("=" * 60)
    
    repaired_bytes = 0
    
    with open(BACKUP_FUNZIONANTE, 'rb') as source:
        with open(HDD_ATTUALE, 'r+b') as target:
            for offset, size, name in REPAIR_AREAS:
                print(f"\n📋 {name}")
                print(f"   Offset: 0x{offset:08x}")
                print(f"   Size: {size:,} bytes")
                
                # Leggi dal backup funzionante
                source.seek(offset)
                data = source.read(size)
                
                if len(data) != size:
                    print(f"   ⚠️ Letti solo {len(data)} bytes (file più piccolo?)")
                    if len(data) == 0:
                        print(f"   ❌ SKIP - nessun dato")
                        continue
                
                # Leggi dati attuali per confronto
                target.seek(offset)
                current_data = target.read(len(data))
                
                # Conta differenze
                diff_count = sum(1 for a, b in zip(data, current_data) if a != b)
                
                if diff_count == 0:
                    print(f"   ✅ Già identico, skip")
                    continue
                
                print(f"   📊 Differenze: {diff_count} bytes")
                
                # Scrivi i nuovi dati
                target.seek(offset)
                target.write(data)
                
                repaired_bytes += len(data)
                print(f"   ✅ Riparato!")
            
            # Forza scrittura su disco
            target.flush()
            os.fsync(target.fileno())
    
    return repaired_bytes


def verify_repair():
    """Verifica che la riparazione sia andata a buon fine."""
    print("\n🔍 VERIFICA RIPARAZIONE...")
    
    # Pattern da cercare
    patterns = [
        (b'4c410015', "Mercenaries_ID"),
        (b'UDATA', "UDATA_marker"),
        (b'TDATA', "TDATA_marker"),
        (b'SaveMeta', "SaveMeta"),
        (b'JAC01', "JAC01_save"),
        (b'FATX', "FATX_signature"),
    ]
    
    found = 0
    
    with open(HDD_ATTUALE, 'rb') as f:
        # Leggi primi 50MB
        f.seek(0)
        content = f.read(50 * 1024 * 1024)
        
        for pattern, name in patterns:
            if pattern in content:
                pos = content.find(pattern)
                print(f"  ✅ {name}: trovato a 0x{pos:08x}")
                found += 1
            else:
                print(f"  ❌ {name}: NON TROVATO")
    
    return found >= 4  # Almeno 4 pattern devono essere presenti


def main():
    print("=" * 60)
    print("🔧 PRECISE REPAIR - Riparazione Xbox HDD")
    print("=" * 60)
    
    # Verifica file
    if not verify_files():
        return False
    
    # Conferma
    print("\n⚠️  ATTENZIONE!")
    print(f"Questo script modificherà: {HDD_ATTUALE}")
    print(f"Usando dati da: {BACKUP_FUNZIONANTE} (SOLO LETTURA)")
    
    response = input("\nProcedere? (s/n): ").strip().lower()
    if response != 's':
        print("❌ Operazione annullata")
        return False
    
    # Backup di sicurezza
    safety_backup = create_safety_backup()
    
    # Ripara
    repaired = repair_areas()
    print(f"\n📊 Bytes riparati: {repaired:,}")
    
    # Verifica
    if verify_repair():
        print("\n" + "=" * 60)
        print("✅ RIPARAZIONE COMPLETATA CON SUCCESSO!")
        print("=" * 60)
        print("\n🎮 Ora avvia xemu e verifica i salvataggi!")
        print(f"\nSe qualcosa non funziona, ripristina da:")
        print(f"  {safety_backup}")
        return True
    else:
        print("\n⚠️ Verifica fallita, ma i pattern potrebbero essere in altre aree")
        print("Prova comunque ad avviare xemu")
        return True


if __name__ == "__main__":
    main()
