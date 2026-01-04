#!/usr/bin/env python3
"""
XEMU SAVE MANAGER - Sistema corretto per backup/restore singolo gioco Xbox

Questo script:
1. Trova giochi Xbox nell'HDD QCOW2 usando pattern matching
2. Estrae l'area di un singolo gioco (pochi KB, non tutto l'HDD!)
3. Può ripristinare SOLO quel gioco senza toccare gli altri
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path

# CONFIGURAZIONE
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # HDD sorgente (backup funzionante)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"       # HDD target (quello usato da xemu)
SAVES_DIR = r"d:\GitHub\xemu_tools\xemu_saves"  # Dove salvare i backup

# Database giochi Xbox (ID -> Nome)
XBOX_GAMES = {
    "4c410015": "Mercenaries",
    "5345000f": "ToeJam & Earl III",
    # Aggiungi altri giochi qui...
}


def find_games_in_hdd(hdd_path):
    """Trova tutti i giochi Xbox nell'HDD."""
    print(f"🔍 Scansione: {Path(hdd_path).name}")
    
    games_found = []
    
    with open(hdd_path, 'rb') as f:
        content = f.read()
    
    for game_id, game_name in XBOX_GAMES.items():
        game_id_bytes = game_id.encode('ascii')
        
        # Cerca tutte le occorrenze
        pos = 0
        occurrences = []
        while True:
            pos = content.find(game_id_bytes, pos)
            if pos == -1:
                break
            occurrences.append(pos)
            pos += 1
        
        if occurrences:
            # Prendi la prima occorrenza (di solito quella principale)
            main_offset = occurrences[0]
            
            games_found.append({
                'game_id': game_id,
                'game_name': game_name,
                'offset': main_offset,
                'occurrences': len(occurrences)
            })
            print(f"  ✅ {game_name} ({game_id}): trovato a 0x{main_offset:08x} ({len(occurrences)} occorrenze)")
    
    return games_found


def extract_game_save(hdd_path, game_id, output_dir=None):
    """Estrae il salvataggio di un singolo gioco."""
    if output_dir is None:
        output_dir = SAVES_DIR
    
    print(f"\n📦 ESTRAZIONE: {game_id}")
    
    game_name = XBOX_GAMES.get(game_id, "Unknown")
    
    with open(hdd_path, 'rb') as f:
        content = f.read()
    
    # Trova l'offset del gioco
    game_id_bytes = game_id.encode('ascii')
    id_offset = content.find(game_id_bytes)
    
    if id_offset == -1:
        print(f"❌ Gioco {game_id} non trovato")
        return None
    
    print(f"🎯 {game_name}: ID trovato a 0x{id_offset:08x}")
    
    # Calcola area da estrarre
    # L'area intorno all'ID del gioco - 64KB prima, 64KB dopo
    area_start = max(0, (id_offset // 0x10000) * 0x10000)  # Allinea a 64KB
    area_end = area_start + 0x30000  # 192KB totali
    area_size = area_end - area_start
    
    print(f"📍 Area: 0x{area_start:08x} - 0x{area_end:08x} ({area_size//1024}KB)")
    
    # Estrai area
    area_data = content[area_start:area_end]
    
    # Crea directory output
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Salva file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    save_file = output_dir / f"{game_id}_{timestamp}.bin"
    metadata_file = output_dir / f"{game_id}_{timestamp}.json"
    
    with open(save_file, 'wb') as f:
        f.write(area_data)
    
    # Metadati
    metadata = {
        'game_id': game_id,
        'game_name': game_name,
        'extraction_date': datetime.now().isoformat(),
        'source_hdd': str(hdd_path),
        'area_offset': area_start,  # Offset NUMERICO, non stringa!
        'area_size': area_size,
        'id_position': id_offset,
        'data_hash': hashlib.md5(area_data).hexdigest()
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"✅ Salvato: {save_file.name} ({len(area_data)//1024}KB)")
    
    return str(save_file), str(metadata_file)


def inject_game_save(save_file, metadata_file, target_hdd=None):
    """Inietta il salvataggio di un singolo gioco."""
    if target_hdd is None:
        target_hdd = HDD_TARGET
    
    print(f"\n💉 INIEZIONE")
    
    # Leggi metadati
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    # Leggi dati
    with open(save_file, 'rb') as f:
        save_data = f.read()
    
    # Gestisci offset (potrebbe essere stringa hex o numero)
    area_offset = metadata['area_offset']
    if isinstance(area_offset, str):
        area_offset = int(area_offset, 16)
    
    print(f"🎯 {metadata['game_name']} ({metadata['game_id']})")
    print(f"📍 Offset: 0x{area_offset:08x}")
    print(f"📏 Size: {len(save_data):,} bytes")
    print(f"📁 Target: {Path(target_hdd).name}")
    
    # Inietta
    try:
        with open(target_hdd, 'r+b') as f:
            f.seek(area_offset)
            bytes_written = f.write(save_data)
            f.flush()
            os.fsync(f.fileno())
        
        print(f"✅ Iniettati {bytes_written:,} bytes")
        return True
    
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False


def verify_game_in_hdd(hdd_path, game_id):
    """Verifica che un gioco esista nell'HDD."""
    with open(hdd_path, 'rb') as f:
        content = f.read()
    
    game_id_bytes = game_id.encode('ascii')
    pos = content.find(game_id_bytes)
    
    if pos != -1:
        print(f"✅ {game_id} trovato a 0x{pos:08x}")
        return True
    else:
        print(f"❌ {game_id} NON trovato")
        return False


def quick_restore(game_id):
    """Ripristina velocemente un gioco dal backup funzionante."""
    print(f"⚡ RIPRISTINO VELOCE: {game_id}")
    
    # Estrai dal backup funzionante
    result = extract_game_save(HDD_SOURCE, game_id)
    if not result:
        return False
    
    save_file, metadata_file = result
    
    # Inietta nell'HDD target
    return inject_game_save(save_file, metadata_file, HDD_TARGET)


def main():
    print("=" * 60)
    print("🎮 XEMU SAVE MANAGER")
    print("=" * 60)
    
    while True:
        print("\n📋 MENU:")
        print("1. 🔍 Trova giochi nell'HDD sorgente")
        print("2. 🔍 Trova giochi nell'HDD target")
        print("3. 📦 Estrai salvataggio gioco")
        print("4. 💉 Inietta salvataggio gioco")
        print("5. ⚡ Ripristino veloce (estrai+inietta)")
        print("6. 🔧 Ripristina TUTTO (vecchio metodo)")
        print("0. ❌ Esci")
        
        choice = input("\nScelta: ").strip()
        
        if choice == "1":
            find_games_in_hdd(HDD_SOURCE)
        
        elif choice == "2":
            find_games_in_hdd(HDD_TARGET)
        
        elif choice == "3":
            games = find_games_in_hdd(HDD_SOURCE)
            if games:
                game_id = input("ID gioco da estrarre: ").strip()
                extract_game_save(HDD_SOURCE, game_id)
        
        elif choice == "4":
            saves_dir = Path(SAVES_DIR)
            if saves_dir.exists():
                files = list(saves_dir.glob("*.bin"))
                if files:
                    print("Backup disponibili:")
                    for i, f in enumerate(files):
                        print(f"  {i+1}. {f.name}")
                    idx = int(input("Numero backup: ")) - 1
                    save_file = files[idx]
                    metadata_file = save_file.with_suffix('.json')
                    inject_game_save(str(save_file), str(metadata_file))
                else:
                    print("❌ Nessun backup trovato")
            else:
                print(f"❌ Directory non trovata: {saves_dir}")
        
        elif choice == "5":
            games = find_games_in_hdd(HDD_SOURCE)
            if games:
                game_id = input("ID gioco: ").strip()
                quick_restore(game_id)
        
        elif choice == "6":
            # Importa e usa il vecchio metodo
            from restore_filesystem_areas import restore_filesystem_areas
            restore_filesystem_areas()
        
        elif choice == "0":
            break


if __name__ == "__main__":
    main()
