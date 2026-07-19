#!/usr/bin/env python3
"""
DIFF COMPLETA - Trova TUTTE le differenze tra source e target
Output salvato su file per evitare overflow console
"""

HDD_SOURCE = r"D:\xemu\bk\xbox_hddf.qcow2"  # Forza CON profilo
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"  # Forza SENZA profilo (eliminato)
OUTPUT_FILE = r"D:\GitHub\xemu_tools\diff_output.txt"

# Area dati FATX per HDD piccoli (xemu nuovo)
DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

print("=" * 70)
print("DIFF COMPLETA HDD5 vs HDD6")
print("=" * 70)

print("\nCaricamento...")
with open(HDD_SOURCE, 'rb') as f:
    source = f.read()
with open(HDD_TARGET, 'rb') as f:
    target = f.read()

print(f"Source: {len(source):,} bytes")
print(f"Target: {len(target):,} bytes")

# Trova TUTTE le differenze
print("\nAnalisi differenze (potrebbe richiedere tempo)...")
all_diffs = []
for i in range(min(len(source), len(target))):
    if source[i] != target[i]:
        all_diffs.append(i)

print(f"\nTOTALE BYTES DIVERSI: {len(all_diffs):,}")

with open(OUTPUT_FILE, 'w') as out:
    out.write(f"DIFF HDD5 vs HDD6\n")
    out.write(f"Source: {HDD_SOURCE}\n")
    out.write(f"Target: {HDD_TARGET}\n")
    out.write(f"Bytes diversi: {len(all_diffs):,}\n\n")
    
    if len(all_diffs) == 0:
        out.write("I file sono IDENTICI!\n")
        print("I file sono IDENTICI!")
    else:
        # Separa differenze pre-data (header/FAT) e data area
        pre_data_diffs = [pos for pos in all_diffs if pos < DATA_START]
        data_diffs = [pos for pos in all_diffs if pos >= DATA_START]
        
        # Mostra differenze pre-data (header/FAT)
        if pre_data_diffs:
            out.write(f"=== DIFFERENZE PRE-DATA (Header/FAT) ===\n")
            out.write(f"Area: 0x00000000 - 0x{DATA_START:08x}\n")
            out.write(f"Bytes diversi: {len(pre_data_diffs)}\n\n")
            
            # Raggruppa per area
            areas = {}
            for pos in pre_data_diffs:
                area_name = "Unknown"
                if pos < 0x1000:
                    area_name = "Header"
                elif pos < 0x001A1000:
                    area_name = "Pre-FAT"
                elif pos < 0x001B3000:
                    area_name = "FAT Area"
                else:
                    area_name = "Post-FAT"
                
                if area_name not in areas:
                    areas[area_name] = []
                areas[area_name].append(pos)
            
            for area_name, positions in sorted(areas.items()):
                out.write(f"\n{area_name}: {len(positions)} bytes\n")
                for pos in positions[:10]:  # Primi 10
                    s = source[pos]
                    t = target[pos]
                    out.write(f"  0x{pos:08x}: src=0x{s:02x} tgt=0x{t:02x}\n")
                if len(positions) > 10:
                    out.write(f"  ... e altri {len(positions) - 10}\n")
            
            print(f"Differenze pre-data: {len(pre_data_diffs)} bytes")
        
        # Raggruppa per cluster (16KB)
        clusters_changed = {}
        for pos in data_diffs:
            cluster = (pos - DATA_START) // CLUSTER_SIZE + 1  # 1-indexed per HDD nuovi
            if cluster not in clusters_changed:
                clusters_changed[cluster] = []
            clusters_changed[cluster].append(pos)
        
        if clusters_changed:
            out.write(f"\n=== DIFFERENZE DATA AREA ===\n")
            out.write(f"CLUSTER MODIFICATI: {len(clusters_changed)}\n")
            out.write(f"Range: {min(clusters_changed.keys())} - {max(clusters_changed.keys())}\n\n")
            
            # Mostra dettagli per ogni cluster
            for cluster in sorted(clusters_changed.keys())[:100]:  # Primi 100 cluster
                diffs = clusters_changed[cluster]
                cluster_offset = DATA_START + (cluster - 1) * CLUSTER_SIZE
                
                out.write(f"\nCluster {cluster} (offset 0x{cluster_offset:08x}): {len(diffs)} bytes diversi\n")
                
                # Primi 5 byte diversi
                for pos in diffs[:5]:
                    s = source[pos]
                    t = target[pos]
                    out.write(f"  0x{pos:08x}: src=0x{s:02x} tgt=0x{t:02x}\n")
            
            if len(clusters_changed) > 100:
                out.write(f"\n... e altri {len(clusters_changed) - 100} cluster\n")
            
            print(f"Cluster modificati: {len(clusters_changed)}")
            print(f"Range: {min(clusters_changed.keys())} - {max(clusters_changed.keys())}")
        else:
            print("Nessun cluster data modificato (tutte le differenze sono in header/FAT)")
        
        print(f"\nOutput salvato in: {OUTPUT_FILE}")

