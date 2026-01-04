#!/usr/bin/env python3
"""Analizza offsets reali vs metadati backup."""

import json
import os

# Metadati del backup
metadata_file = r"d:\GitHub\xemu_tools\game_saves\4c410015_save_20250816_170428.json"
hdd_file = r"D:\xemu\xbox_hdd.qcow2"

print("=" * 60)
print("ANALISI OFFSETS")
print("=" * 60)

# Leggi metadati
with open(metadata_file, 'r') as f:
    meta = json.load(f)

print("\nMETADATI BACKUP:")
print(f"  Game ID: {meta['game_id']}")
print(f"  Game Name: {meta['game_name']}")
print(f"  Area Offset: {meta['area_offset']}")
print(f"  Area Size: {meta['area_size']:,} bytes")

# Trova offset REALI nell'HDD attuale
print(f"\nLettura HDD: {hdd_file}...")
print(f"Dimensione: {os.path.getsize(hdd_file):,} bytes")

with open(hdd_file, 'rb') as f:
    # Leggi i primi 50MB dove sono i pattern
    content = f.read(50 * 1024 * 1024)

patterns = [b'4c410015', b'UDATA', b'TDATA', b'SaveMeta', b'JAC01', b'FATX']
print("\nPATTERN NELL'HDD ATTUALE:")
for p in patterns:
    pos = content.find(p)
    if pos != -1:
        print(f"  {p.decode('utf-8', errors='replace')}: 0x{pos:08x}")
    else:
        print(f"  {p.decode('utf-8', errors='replace')}: NON TROVATO")

# Calcola differenza
offset_backup = int(meta['area_offset'], 16)
offset_real = content.find(b'4c410015')

print(f"\nCONFRONTO:")
print(f"  Offset nel backup metadata: 0x{offset_backup:08x}")
print(f"  Offset 4c410015 reale:      0x{offset_real:08x}")
print(f"  Differenza:                 0x{abs(offset_real - offset_backup):08x} ({abs(offset_real - offset_backup):,} bytes)")

if offset_real != offset_backup:
    print("\n⚠️  GLI OFFSET NON COINCIDONO!")
    print("Questo potrebbe essere il problema: l'iniezione scrive all'offset sbagliato.")
else:
    print("\n✅ Gli offset coincidono.")
