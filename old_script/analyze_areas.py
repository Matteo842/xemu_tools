#!/usr/bin/env python3
"""Analisi differenze per area funzionale."""

import struct

hdd_with = r"D:\xemu\bk\xbox_hdd2.qcow2"
hdd_without = r"D:\xemu\xbox_hdd.qcow2"

print("Caricamento...")
with open(hdd_with, 'rb') as f:
    data_with = f.read()
with open(hdd_without, 'rb') as f:
    data_without = f.read()

# Aree note del filesystem Xbox
areas = [
    (0x00020000, 0x10000, "QCOW2_Refcount"),
    (0x00050000, 0x10000, "QCOW2_L2"),
    (0x00150000, 0x10000, "Pre_FAT"),
    (0x00160000, 0x10000, "FAT_Table_1"),
    (0x00170000, 0x10000, "Dir_Metadata"),
    (0x001e0000, 0x10000, "FAT_Table_2"),
    (0x00310000, 0x10000, "Extended_Meta"),
    (0x00440000, 0x10000, "Root_Dir"),      # TDATA, UDATA
    (0x00450000, 0x10000, "Game_Dir_1"),    # 4c410015, 5345000f entries
    (0x00460000, 0x20000, "Save_Files"),    # SaveMeta, JAC01, etc
]

print("\n" + "=" * 70)
print("ANALISI DIFFERENZE PER AREA")
print("=" * 70)

for start, size, name in areas:
    area_with = data_with[start:start+size]
    area_without = data_without[start:start+size]
    
    if area_with == area_without:
        print(f"{name:20s} (0x{start:08x}): IDENTICA")
    else:
        diff_count = sum(1 for a, b in zip(area_with, area_without) if a != b)
        print(f"{name:20s} (0x{start:08x}): {diff_count:>5} bytes diversi")
        
        # Mostra prime differenze
        shown = 0
        for i, (a, b) in enumerate(zip(area_with, area_without)):
            if a != b and shown < 3:
                abs_pos = start + i
                context = data_with[abs_pos:abs_pos+16]
                ascii_ctx = ''.join(chr(c) if 32 <= c < 127 else '.' for c in context)
                print(f"    0x{abs_pos:08x}: 0x{a:02x}->0x{b:02x}  \"{ascii_ctx}\"")
                shown += 1

print("\n" + "=" * 70)
print("CONCLUSIONE")
print("=" * 70)
print("""
Le differenze sono principalmente nelle TABELLE CONDIVISE (FAT, metadata).
Per fare restore di un singolo gioco senza toccare l'altro, devo:

1. NON sovrascrivere tutta la tabella FAT
2. Fare un MERGE: aggiornare SOLO le entry relative al gioco da ripristinare
3. Lo stesso per directory metadata e altri metadati

Questo richiede di PARSARE le tabelle e modificare chirurgicamente.
""")
