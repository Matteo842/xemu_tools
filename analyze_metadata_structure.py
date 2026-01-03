#!/usr/bin/env python3
"""
ANALISI STRUTTURA METADATA 0x311000
Questa area sembra contenere puntatori a cluster per ogni gioco.
"""

import struct

SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"

print("=" * 70)
print("ANALISI STRUTTURA METADATA 0x311000")
print("=" * 70)

with open(SOURCE, 'rb') as f:
    # Leggi l'intera area
    f.seek(0x311000)
    data = f.read(0x200)  # 512 bytes

print("\nStruttura a 0x311000 (come array di 4-byte integers):\n")

for i in range(0, len(data), 4):
    val = struct.unpack('<I', data[i:i+4])[0]
    offset = 0x311000 + i
    
    if val != 0:
        # Interpreta il valore
        if val == 0xFFFFFFFF:
            desc = "END/FREE marker"
        elif val < 10000:
            desc = f"Cluster number {val}"
        else:
            desc = f"Valore: 0x{val:08x}"
        
        print(f"  0x{offset:08x}: {val:5d} ({desc})")

print("\n" + "=" * 70)
print("CORRELAZIONE CON FAT CHAIN")
print("=" * 70)

# Mercenaries: cluster 4, 5, 6, poi 3225+
# ToeJam: cluster 39-146

# Vediamo se ci sono pattern
f = open(SOURCE, 'rb')
f.seek(0x311000)
data = f.read(0x200)
f.close()

# Cerca sequenze che potrebbero essere cluster numbers
print("\nSequenze trovate:")

i = 0
sequences = []
current_seq = []
while i < len(data):
    val = struct.unpack('<I', data[i:i+4])[0]
    
    if val != 0 and val != 0xFFFFFFFF and val < 10000:
        current_seq.append(val)
    else:
        if len(current_seq) > 1:
            sequences.append(current_seq)
        current_seq = []
    i += 4

if current_seq:
    sequences.append(current_seq)

for seq in sequences:
    print(f"  {seq[:20]}{'...' if len(seq) > 20 else ''} ({len(seq)} valori)")

# Vediamo se matchano i cluster dei giochi
print("\n" + "=" * 70)
print("IPOTESI")
print("=" * 70)
print("""
Se i valori sono cluster numbers:
- Mercenaries usa cluster 4, 5, 6, 3225-6110
- ToeJam usa cluster 39-146

Guardando la tabella, sembra che ogni entry di 4 bytes punti a un cluster.
L'offset nella tabella potrebbe essere calcolato come:
  table_offset = 0x311000 + (cluster_number * 4)

O potrebbe essere una tabella sequenziale dove ogni entry rappresenta
un cluster allocato a un certo "blocco" o "file".

Per il restore, dobbiamo:
1. Capire quali entry appartengono a quale gioco
2. Ripristinare quelle entry specifiche
""")
