#!/usr/bin/env python3
"""
🎮 Xbox HDD Backup Manager
Gestisce i backup degli HDD QCOW2 per xemu

Permette di sostituire rapidamente l'HDD attivo con uno dei backup.
Lo script rimane aperto per permettere selezioni multiple.
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime

# Percorso del file di configurazione (relativo allo script)
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "hdd_backups.json"


def load_config():
    """Carica la configurazione dei backup dal JSON"""
    if not CONFIG_FILE.exists():
        print(f"❌ File di configurazione non trovato: {CONFIG_FILE}")
        return None
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def display_menu(config):
    """Mostra il menu con i backup disponibili"""
    print("\n" + "=" * 60)
    print("🎮 Xbox HDD Backup Manager")
    print("=" * 60)
    print(f"📁 Backup folder: {config['backup_folder']}")
    print(f"🎯 Target HDD: {config['xemu_root']}\\{config['target_hdd']}")
    print("-" * 60)
    print("\n📋 Backup disponibili:\n")
    
    for backup in config['backups']:
        backup_id = backup['id']
        desc = backup['description']
        filename = backup['filename']
        
        # Verifica se il file esiste
        backup_path = Path(config['backup_folder']) / filename
        exists = "✅" if backup_path.exists() else "❌"
        
        # Formatta l'ID per allineamento
        id_display = f"[{backup_id}]".ljust(6)
        
        print(f"  {id_display} {exists} {desc}")
        print(f"          └── {filename}")
    
    print("-" * 60)
    print("\n  [q] Esci")
    print()


def restore_backup(config, backup_id):
    """Ripristina un backup specifico"""
    # Trova il backup corrispondente
    backup_info = None
    for backup in config['backups']:
        if backup['id'].lower() == backup_id.lower():
            backup_info = backup
            break
    
    if not backup_info:
        print(f"\n❌ Backup '{backup_id}' non trovato!")
        return False
    
    # Percorsi
    backup_folder = Path(config['backup_folder'])
    xemu_root = Path(config['xemu_root'])
    
    source_file = backup_folder / backup_info['filename']
    target_file = xemu_root / config['target_hdd']
    
    # Verifica che il file sorgente esista
    if not source_file.exists():
        print(f"\n❌ File backup non trovato: {source_file}")
        return False
    
    print(f"\n🔄 Ripristino backup...")
    print(f"   📤 Da:  {source_file}")
    print(f"   📥 A:   {target_file}")
    print(f"   📝 {backup_info['description']}")
    
    # Ottieni dimensione file
    file_size_mb = source_file.stat().st_size / (1024 * 1024)
    print(f"   📊 Dimensione: {file_size_mb:.1f} MB")
    
    try:
        # Copia il file
        start_time = datetime.now()
        shutil.copy2(source_file, target_file)
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"\n✅ Backup ripristinato con successo!")
        print(f"   ⏱️ Tempo: {elapsed:.1f} secondi")
        return True
        
    except PermissionError:
        print(f"\n❌ Errore: Il file target è in uso!")
        print("   💡 Chiudi xemu e riprova.")
        return False
    except Exception as e:
        print(f"\n❌ Errore durante la copia: {e}")
        return False


def main():
    """Loop principale"""
    print("\n" + "🎮" * 30)
    print("    Xbox HDD Backup Manager v1.0")
    print("🎮" * 30)
    
    # Carica configurazione
    config = load_config()
    if not config:
        input("\nPremi INVIO per uscire...")
        return
    
    while True:
        display_menu(config)
        
        choice = input("🎯 Seleziona backup (ID o 'q' per uscire): ").strip()
        
        if choice.lower() == 'q':
            print("\n👋 Arrivederci!")
            break
        
        if not choice:
            continue
        
        # Cerca il backup
        found = False
        for backup in config['backups']:
            if backup['id'].lower() == choice.lower():
                found = True
                break
        
        if found:
            # Conferma prima di procedere
            confirm = input(f"\n⚠️ Confermi il ripristino del backup '{choice}'? (s/n): ").strip().lower()
            if confirm == 's' or confirm == 'y':
                restore_backup(config, choice)
            else:
                print("❌ Operazione annullata.")
        else:
            print(f"\n❌ ID backup '{choice}' non valido!")
        
        input("\n⏎ Premi INVIO per continuare...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interruzione utente. Uscita...")
