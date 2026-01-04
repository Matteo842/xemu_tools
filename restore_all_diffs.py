#!/usr/bin/env python3
"""
RESTORE COMPLETO DIFFERENZE - Copia tutte le differenze dal source al target
Questo è un test per verificare che copiando TUTTO funziona
"""

import os

HDD_SOURCE = r"D:\xemu\bk\xbox_hdd3.qcow2"
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"

print("=" * 70)
print("RESTORE COMPLETO - Copia TUTTE le differenze")
print("=" * 70)

print(f"\nSource: {os.path.basename(HDD_SOURCE)}")
print(f"Target: {os.path.basename(HDD_TARGET)}")

# Leggi
print("\nCaricamento...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
with open(HDD_TARGET, 'rb') as f:
    target = bytearray(f.read())

print(f"Size: {len(source):,} bytes")

# Trova differenze
print("\nCerca differenze...")
diffs = []
for i in range(min(len(source), len(target))):
    if source[i] != target[i]:
        diffs.append(i)

print(f"Differenze trovate: {len(diffs):,} bytes")

if len(diffs) == 0:
    print("I file sono identici!")
    exit()

# Chiedi conferma
print("\n" + "=" * 70)
print("ATTENZIONE: Questo script copierà TUTTE le differenze!")
print("=" * 70)
resp = input("Procedere? (s/n): ")

if resp.lower() != 's':
    print("Annullato")
    exit()

# Copia le differenze
print("\nCopia differenze...")
for pos in diffs:
    target[pos] = source[pos]

# Scrivi
print("Scrittura...")
with open(HDD_TARGET, 'wb') as f:
    f.write(target)

print("\nFatto! Ora verifica con xemu.")
