#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XBOX HDD MANAGER - Sistema definitivo per gestire HDD Xbox
Accetta che serve copia completa ma la rende veloce e automatica
"""

import os
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

class XboxHDDManager:
    """Manager definitivo per HDD Xbox."""
    
    def __init__(self):
        # HDD paths
        self.working_hdd = Path(r"D:\xemu\bk\xbox_hdd2.qcow2")  # Funzionante (entrambi giochi)
        self.mercenaries_hdd = Path(r"D:\xemu\bk\xbox_hdd1.qcow2")  # Solo Mercenaries
        self.target_hdd = Path(r"D:\xemu\xbox_hdd.qcow2")  # HDD corrente
        
        # Backup directory
        self.backup_dir = Path("./hdd_backups")
        self.backup_dir.mkdir(exist_ok=True)
    
    def create_backup(self, label="manual"):
        """Crea backup dell'HDD corrente."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"xbox_hdd_backup_{label}_{timestamp}.qcow2"
        backup_path = self.backup_dir / backup_name
        
        print(f"🔄 Creazione backup: {backup_name}")
        
        try:
            shutil.copy2(self.target_hdd, backup_path)
            
            # Calcola hash per verifica
            with open(backup_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()[:16]
            
            print(f"✅ Backup creato: {backup_path.name}")
            print(f"📋 Hash: {file_hash}")
            
            return backup_path
        
        except Exception as e:
            print(f"❌ Errore backup: {e}")
            return None
    
    def restore_from_source(self, source_type="both_games"):
        """Ripristina da HDD sorgente."""
        sources = {
            "both_games": self.working_hdd,
            "mercenaries_only": self.mercenaries_hdd,
            "working": self.working_hdd
        }
        
        source_hdd = sources.get(source_type, self.working_hdd)
        
        if not source_hdd.exists():
            print(f"❌ HDD sorgente non trovato: {source_hdd}")
            return False
        
        print(f"🔄 RIPRISTINO DA: {source_hdd.name}")
        print(f"📍 Target: {self.target_hdd.name}")
        
        # Backup automatico prima del ripristino
        backup_path = self.create_backup(f"before_restore_{source_type}")
        
        try:
            # Copia completa
            shutil.copy2(source_hdd, self.target_hdd)
            
            print(f"✅ Ripristino completato!")
            print(f"🔄 Backup disponibile: {backup_path.name if backup_path else 'N/A'}")
            
            return True
        
        except Exception as e:
            print(f"❌ Errore ripristino: {e}")
            return False
    
    def quick_test_games(self):
        """Test rapido per vedere quali giochi sono presenti."""
        print(f"🧪 TEST RAPIDO GIOCHI")
        print("="*30)
        
        if not self.target_hdd.exists():
            print(f"❌ HDD target non trovato")
            return {}
        
        patterns = {
            'mercenaries': b'4c410015',
            'toejam': b'SaveMeta.xbx',
            'udata': b'UDATA',
            'tdata': b'TDATA'
        }
        
        found_games = {}
        
        try:
            with open(self.target_hdd, 'rb') as f:
                # Leggi primi 50MB (dove sono i salvataggi)
                f.seek(0)
                data = f.read(50 * 1024 * 1024)
                
                for game, pattern in patterns.items():
                    positions = []
                    pos = 0
                    while True:
                        pos = data.find(pattern, pos)
                        if pos == -1:
                            break
                        positions.append(pos)
                        pos += 1
                    
                    if positions:
                        found_games[game] = {
                            'pattern': pattern.decode('ascii', errors='ignore'),
                            'positions': positions[:3],  # Prime 3 posizioni
                            'count': len(positions)
                        }
                        print(f"  ✅ {game}: {len(positions)} occorrenze")
                    else:
                        print(f"  ❌ {game}: NON TROVATO")
        
        except Exception as e:
            print(f"❌ Errore test: {e}")
        
        return found_games
    
    def list_backups(self):
        """Lista backup disponibili."""
        print(f"📋 BACKUP DISPONIBILI")
        print("="*30)
        
        backups = list(self.backup_dir.glob("*.qcow2"))
        backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not backups:
            print("❌ Nessun backup trovato")
            return []
        
        for i, backup in enumerate(backups):
            stat = backup.stat()
            size_mb = stat.st_size / 1024 / 1024
            mtime = datetime.fromtimestamp(stat.st_mtime)
            
            print(f"  [{i+1}] {backup.name}")
            print(f"      Dimensione: {size_mb:.1f}MB")
            print(f"      Data: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
        
        return backups
    
    def restore_from_backup(self, backup_index=None):
        """Ripristina da backup."""
        backups = self.list_backups()
        
        if not backups:
            return False
        
        if backup_index is None:
            try:
                backup_index = int(input("Scegli backup (numero): ")) - 1
            except (ValueError, IndexError):
                print("❌ Selezione non valida")
                return False
        
        if backup_index < 0 or backup_index >= len(backups):
            print("❌ Indice backup non valido")
            return False
        
        backup_path = backups[backup_index]
        
        print(f"🔄 Ripristino da: {backup_path.name}")
        
        try:
            shutil.copy2(backup_path, self.target_hdd)
            print(f"✅ Ripristino da backup completato!")
            return True
        
        except Exception as e:
            print(f"❌ Errore ripristino backup: {e}")
            return False
    
    def workflow_test_game(self, game_type="both_games"):
        """Workflow completo per testare un gioco."""
        print(f"🎮 WORKFLOW TEST GIOCO")
        print("="*40)
        
        # 1. Backup stato corrente
        print("📋 Step 1: Backup stato corrente")
        backup_path = self.create_backup(f"before_test_{game_type}")
        
        # 2. Ripristina da sorgente
        print(f"\n📋 Step 2: Ripristino da {game_type}")
        if not self.restore_from_source(game_type):
            print("❌ Ripristino fallito")
            return False
        
        # 3. Test rapido
        print(f"\n📋 Step 3: Test presenza giochi")
        found_games = self.quick_test_games()
        
        # 4. Istruzioni per l'utente
        print(f"\n📋 Step 4: Test manuale")
        print("🎮 Ora testa xemu:")
        print("   1. Avvia xemu")
        print("   2. Controlla i giochi")
        print("   3. Torna qui per il prossimo test")
        
        return True

def main():
    """Menu principale."""
    print("🎮 XBOX HDD MANAGER")
    print("Sistema definitivo per gestire HDD Xbox")
    print("="*50)
    
    manager = XboxHDDManager()
    
    while True:
        print(f"\n🎯 MENU PRINCIPALE:")
        print("1. 🔄 Ripristina HDD (entrambi i giochi)")
        print("2. 🎮 Ripristina HDD (solo Mercenaries)")
        print("3. 🧪 Test rapido giochi presenti")
        print("4. 💾 Crea backup manuale")
        print("5. 📋 Lista backup")
        print("6. ⏪ Ripristina da backup")
        print("7. 🚀 Workflow test completo")
        print("0. ❌ Esci")
        
        choice = input("Scelta: ").strip()
        
        if choice == "1":
            if manager.restore_from_source("both_games"):
                print("✅ Ripristino completato! Testa xemu.")
        
        elif choice == "2":
            if manager.restore_from_source("mercenaries_only"):
                print("✅ Ripristino completato! Testa xemu.")
        
        elif choice == "3":
            manager.quick_test_games()
        
        elif choice == "4":
            label = input("Etichetta backup (opzionale): ").strip() or "manual"
            manager.create_backup(label)
        
        elif choice == "5":
            manager.list_backups()
        
        elif choice == "6":
            manager.restore_from_backup()
        
        elif choice == "7":
            print("🚀 Workflow test:")
            print("1. Entrambi i giochi")
            print("2. Solo Mercenaries")
            
            test_choice = input("Scelta: ").strip()
            
            if test_choice == "1":
                manager.workflow_test_game("both_games")
            elif test_choice == "2":
                manager.workflow_test_game("mercenaries_only")
        
        elif choice == "0":
            break
        
        else:
            print("❌ Scelta non valida")

if __name__ == "__main__":
    main()