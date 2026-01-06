#!/usr/bin/env python3
"""
COPIA ESATTA BYTE DIVERSI H1 -> TARGET
Copia SOLO i byte che sono diversi tra H1 e H2
"""

import struct
import os

HDD_SOURCE = r"D:\xemu\bk\xbox_hddh1.qcow2"  # Checkpoint 1 (backup)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"        # HDD attivo (copia di h2)

print("="*70)
print("COPIA ESATTA BYTE DIVERSI")
print("="*70)

# Carica entrambi per confronto
print("\nCaricamento source (H1)...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
print(f"H1 Size: {len(source):,} bytes")

print("Caricamento target (copia H2)...")
with open(HDD_TARGET, 'rb') as f:
    target = f.read()
print(f"Target Size: {len(target):,} bytes")

# Trova TUTTI i byte diversi
print("\nTrovando byte diversi...")
diff_positions = []
min_len = min(len(source), len(target))
for i in range(min_len):
    if source[i] != target[i]:
        diff_positions.append(i)

print(f"Byte diversi: {len(diff_positions):,}")

if len(diff_positions) == 0:
    print("Nessuna differenza! I file sono già identici.")
    exit(0)

# Mostra range delle differenze
print(f"Range: 0x{min(diff_positions):08x} - 0x{max(diff_positions):08x}")

# Raggruppa per posizione (ottimizzazione)
# Invece di scrivere byte per byte, raggruppiamo in blocchi contigui
blocks = []
current_start = diff_positions[0]
current_end = diff_positions[0]

for pos in diff_positions[1:]:
    if pos == current_end + 1:
        # Continua blocco corrente
        current_end = pos
    else:
        # Salva blocco precedente e inizia nuovo
        blocks.append((current_start, current_end))
        current_start = pos
        current_end = pos

# Non dimenticare l'ultimo blocco
blocks.append((current_start, current_end))

print(f"Blocchi contigui: {len(blocks)}")
for start, end in blocks[:10]:
    print(f"  0x{start:08x} - 0x{end:08x} ({end - start + 1} bytes)")
if len(blocks) > 10:
    print(f"  ... e altri {len(blocks) - 10} blocchi")

# Calcola byte totali
total_bytes = sum(end - start + 1 for start, end in blocks)
print(f"\nByte totali da scrivere: {total_bytes:,}")

# Conferma
confirm = input("\nProcedere con la copia? (y/n): ").strip().lower()
if confirm != 'y':
    print("Annullato.")
    exit(0)

# Copia!
print("\nScrittura su target...")
with open(HDD_TARGET, 'r+b') as f:
    for start, end in blocks:
        f.seek(start)
        f.write(source[start:end + 1])
    
    f.flush()
    os.fsync(f.fileno())

print("\n" + "="*70)
print("COPIA COMPLETATA!")
print("="*70)
print(f"Scritti {total_bytes:,} bytes in {len(blocks)} blocchi")
print("Ora testa con xemu!")
