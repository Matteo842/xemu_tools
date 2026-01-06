#!/usr/bin/env python3
"""
Analisi differenze tra B1 (1%) e B2 (3%) per Black
"""
import struct

B1 = r"D:\xemu\bk\xbox_hddb1.qcow2"  # 1% completion
B2 = r"D:\xemu\bk\xbox_hddb2.qcow2"  # 3% completion

# Offset noti per HDD piccoli
FAT_OFFSET = 0x001A1000
DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

print("=" * 70)
print("ANALISI DIFFERENZE BLACK: B1 (1%) vs B2 (3%)")
print("=" * 70)

with open(B1, 'rb') as f:
    b1_data = f.read()
with open(B2, 'rb') as f:
    b2_data = f.read()

print(f"\nB1 size: {len(b1_data):,} bytes")
print(f"B2 size: {len(b2_data):,} bytes")

# Trova tutte le differenze
diffs = []
for i in range(min(len(b1_data), len(b2_data))):
    if b1_data[i] != b2_data[i]:
        diffs.append(i)

print(f"\nTotale bytes diversi: {len(diffs)}")

if len(diffs) == 0:
    print("I file sono IDENTICI!")
    exit(0)

# Raggruppa per area
areas = {
    "Header (0x000000-0x001000)": [],
    "Pre-FATX (0x001000-0x1A0000)": [],
    "FATX Header (0x1A0000-0x1A1000)": [],
    "FAT Table (0x1A1000-0x1B3000)": [],
    "Data Area (0x1B3000+)": [],
}

for pos in diffs:
    if pos < 0x1000:
        areas["Header (0x000000-0x001000)"].append(pos)
    elif pos < 0x1A0000:
        areas["Pre-FATX (0x001000-0x1A0000)"].append(pos)
    elif pos < 0x1A1000:
        areas["FATX Header (0x1A0000-0x1A1000)"].append(pos)
    elif pos < 0x1B3000:
        areas["FAT Table (0x1A1000-0x1B3000)"].append(pos)
    else:
        areas["Data Area (0x1B3000+)"].append(pos)

print("\n" + "=" * 50)
print("DIFFERENZE PER AREA:")
print("=" * 50)

for area_name, positions in areas.items():
    if positions:
        print(f"\n{area_name}: {len(positions)} bytes")
        print("-" * 40)
        for pos in positions[:20]:  # Primi 20
            v1 = b1_data[pos]
            v2 = b2_data[pos]
            # Calcola cluster se in data area
            cluster_info = ""
            if pos >= DATA_START:
                cluster = (pos - DATA_START) // CLUSTER_SIZE + 1
                cluster_info = f" [cluster {cluster}]"
            print(f"  0x{pos:08x}: B1=0x{v1:02x} B2=0x{v2:02x}{cluster_info}")
        if len(positions) > 20:
            print(f"  ... e altri {len(positions) - 20}")

# Analisi specifica FAT entries
print("\n" + "=" * 50)
print("ANALISI FAT ENTRIES DIVERSE:")
print("=" * 50)

fat_diffs = areas["FAT Table (0x1A1000-0x1B3000)"]
if fat_diffs:
    # Raggruppa per cluster (ogni 2 bytes per FAT16)
    clusters_changed = set()
    for pos in fat_diffs:
        fat_entry_idx = (pos - FAT_OFFSET) // 2
        clusters_changed.add(fat_entry_idx)
    
    print(f"\nCluster FAT modificati: {sorted(clusters_changed)}")
    print(f"\nValori FAT per ogni cluster modificato:")
    for cluster in sorted(clusters_changed):
        fat16_offset = FAT_OFFSET + cluster * 2
        v1 = struct.unpack('<H', b1_data[fat16_offset:fat16_offset+2])[0]
        v2 = struct.unpack('<H', b2_data[fat16_offset:fat16_offset+2])[0]
        print(f"  Cluster {cluster}: B1=0x{v1:04x} ({v1}) → B2=0x{v2:04x} ({v2})")

# Analisi cluster dati
print("\n" + "=" * 50)
print("ANALISI CLUSTER DATI DIVERSI:")
print("=" * 50)

data_diffs = areas["Data Area (0x1B3000+)"]
if data_diffs:
    clusters_with_diffs = {}
    for pos in data_diffs:
        cluster = (pos - DATA_START) // CLUSTER_SIZE + 1
        if cluster not in clusters_with_diffs:
            clusters_with_diffs[cluster] = []
        clusters_with_diffs[cluster].append(pos)
    
    print(f"\nCluster con differenze: {len(clusters_with_diffs)}")
    for cluster, positions in sorted(clusters_with_diffs.items()):
        cluster_offset = DATA_START + (cluster - 1) * CLUSTER_SIZE
        print(f"\nCluster {cluster} (offset 0x{cluster_offset:08x}): {len(positions)} bytes diversi")
        
        # Mostra primi bytes del cluster per capire cosa contiene
        content_preview = b1_data[cluster_offset:cluster_offset+64]
        # Cerca di identificare il tipo di contenuto
        if content_preview[0] >= 1 and content_preview[0] <= 42:
            # Potrebbe essere directory entry
            fn_len = content_preview[0]
            try:
                filename = content_preview[2:2+fn_len].decode('ascii', errors='replace')
                print(f"  Contiene: Directory entry? filename='{filename}'")
            except:
                pass
        elif content_preview[:4] in [b'FATX', b'XBSV']:
            print(f"  Contiene: Header {content_preview[:4]}")
        else:
            # Mostra primi bytes
            hex_str = ' '.join(f'{b:02x}' for b in content_preview[:32])
            print(f"  Primi 32 bytes: {hex_str}")
else:
    print("\nNessuna differenza nell'area dati!")

print("\n" + "=" * 50)
print("FINE ANALISI")
print("=" * 50)
