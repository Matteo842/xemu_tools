#!/usr/bin/env python3
"""
RESTORE COMPLETO H1 -> TARGET
Copia TUTTO ciò che esiste in H1 (fino a cluster 61467)
"""

import os

HDD_SOURCE = r"D:\xemu\bk\xbox_hddh1.qcow2"
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"

print("="*70)
print("RESTORE COMPLETO H1")
print("="*70)

print("\nCaricamento source (H1)...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
print(f"H1 Size: {len(source):,} bytes")

print("Caricamento target...")
with open(HDD_TARGET, 'rb') as f:
    target = f.read()
print(f"Target Size: {len(target):,} bytes")

# Trova byte diversi fino alla fine di H1
print("\nTrovando byte diversi (tutto H1)...")
limit = len(source)  # Tutto H1!
print(f"Limite: {limit:,} bytes (tutto H1)")

diff_positions = []
for i in range(min(limit, len(target))):
    if source[i] != target[i]:
        diff_positions.append(i)

print(f"\nByte diversi: {len(diff_positions):,}")

if len(diff_positions) == 0:
    print("Nessuna differenza!")
    exit(0)

# Raggruppa
blocks = []
current_start = diff_positions[0]
current_end = diff_positions[0]
for pos in diff_positions[1:]:
    if pos == current_end + 1:
        current_end = pos
    else:
        blocks.append((current_start, current_end))
        current_start = pos
        current_end = pos
blocks.append((current_start, current_end))

total_bytes = sum(end - start + 1 for start, end in blocks)
print(f"Blocchi: {len(blocks)}")
print(f"Byte totali: {total_bytes:,}")

confirm = input("\nProcedere? (y/n): ").strip().lower()
if confirm != 'y':
    print("Annullato.")
    exit(0)

print("\nScrittura...")
with open(HDD_TARGET, 'r+b') as f:
    for start, end in blocks:
        f.seek(start)
        f.write(source[start:end + 1])
    f.flush()
    os.fsync(f.fileno())

print("\n" + "="*70)
print("COMPLETATO!")
print("="*70)
print(f"Scritti {total_bytes:,} bytes")
