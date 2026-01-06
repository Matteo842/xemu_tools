#!/usr/bin/env python3
"""
ANALISI COMPLETA SAVE HALO 2
Trova TUTTO ciò che serve per il backup del checkpoint
"""

import struct

HDD_H1 = r"D:\xemu\bk\xbox_hddh1.qcow2"  # Checkpoint 1
HDD_H2 = r"D:\xemu\bk\xbox_hddh2.qcow2"  # Checkpoint 2

# Offset per HDD xemu standard
FAT_OFFSET = 0x001A1000
DATA_START = 0x001B3000
CLUSTER_SIZE = 16384

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 1) * CLUSTER_SIZE)

def get_fat_chain(data, first_cluster, max_length=1000):
    """Costruisce la catena FAT"""
    if first_cluster == 0 or first_cluster >= 0xFFF0:
        return []
    
    chain = [first_cluster]
    current = first_cluster
    seen = set([first_cluster])
    
    for _ in range(max_length):
        fat_off = FAT_OFFSET + (current * 2)
        if fat_off + 2 > len(data):
            break
        next_cluster = struct.unpack('<H', data[fat_off:fat_off + 2])[0]
        
        if next_cluster >= 0xFFF8 or next_cluster == 0x0000:
            break
        if next_cluster in seen:
            break
        
        chain.append(next_cluster)
        seen.add(next_cluster)
        current = next_cluster
    
    return chain

def find_save_files(data, hdd_name):
    """Trova tutti i file del save di Halo 2"""
    print(f"\n{'='*60}")
    print(f"ANALISI: {hdd_name}")
    print(f"{'='*60}")
    print(f"Size: {len(data):,} bytes")
    
    results = {}
    
    # Cerca file importanti per nome
    files_to_find = [
        b'auxilary.bin',    # Contiene i checkpoint!
        b'profile',         # Profilo giocatore
        b'SaveMeta.xbx',    # Metadata save
    ]
    
    for pattern in files_to_find:
        print(f"\nCerco '{pattern.decode()}'...")
        pos = 0
        while True:
            pos = data.find(pattern, pos)
            if pos == -1:
                break
            
            # Verifica directory entry
            entry_start = pos - 2
            if entry_start >= 0:
                fn_len = data[entry_start]
                if fn_len == len(pattern):
                    attrs = data[entry_start + 1]
                    first_cluster = struct.unpack('<I', data[entry_start + 44:entry_start + 48])[0]
                    file_size = struct.unpack('<I', data[entry_start + 48:entry_start + 52])[0]
                    
                    # In quale cluster è questa entry?
                    if entry_start >= DATA_START:
                        entry_cluster = (entry_start - DATA_START) // CLUSTER_SIZE + 1
                    else:
                        entry_cluster = -1
                    
                    # Segui la FAT chain
                    fat_chain = get_fat_chain(data, first_cluster)
                    
                    name = pattern.decode()
                    print(f"  TROVATO: {name}")
                    print(f"    Entry @ offset 0x{entry_start:08x} (cluster {entry_cluster})")
                    print(f"    Dati @ cluster {first_cluster}, size {file_size:,} bytes")
                    print(f"    FAT chain: {len(fat_chain)} cluster ({first_cluster} -> {fat_chain[-1] if fat_chain else 'N/A'})")
                    
                    results[name] = {
                        'entry_offset': entry_start,
                        'entry_cluster': entry_cluster,
                        'first_cluster': first_cluster,
                        'file_size': file_size,
                        'fat_chain': fat_chain,
                    }
            pos += 1
    
    return results

def compare_saves(h1_data, h2_data, h1_results, h2_results):
    """Confronta i save tra H1 e H2"""
    print(f"\n{'='*60}")
    print("CONFRONTO H1 vs H2")
    print(f"{'='*60}")
    
    for name in h1_results:
        if name not in h2_results:
            print(f"\n{name}: presente solo in H1!")
            continue
        
        h1 = h1_results[name]
        h2 = h2_results[name]
        
        print(f"\n{name}:")
        print(f"  H1: cluster {h1['first_cluster']}, size {h1['file_size']:,}, chain={len(h1['fat_chain'])} cluster")
        print(f"  H2: cluster {h2['first_cluster']}, size {h2['file_size']:,}, chain={len(h2['fat_chain'])} cluster")
        
        # Confronta i dati
        if h1['fat_chain'] and h2['fat_chain']:
            h1_first_offset = cluster_to_offset(h1['first_cluster'])
            h2_first_offset = cluster_to_offset(h2['first_cluster'])
            
            # Leggi primi 1KB per confronto
            h1_sample = h1_data[h1_first_offset:h1_first_offset + 1024]
            h2_sample = h2_data[h2_first_offset:h2_first_offset + 1024]
            
            if h1_sample == h2_sample:
                print(f"  Primi 1KB: IDENTICI")
            else:
                # Conta byte diversi
                diff_count = sum(1 for a, b in zip(h1_sample, h2_sample) if a != b)
                print(f"  Primi 1KB: {diff_count} byte diversi")
        
        # Se è auxilary.bin, analizza in dettaglio
        if name == 'auxilary.bin':
            print(f"\n  ANALISI DETTAGLIATA auxilary.bin:")
            
            # Leggi tutti i dati
            h1_full_data = b''
            for cluster in h1['fat_chain']:
                off = cluster_to_offset(cluster)
                h1_full_data += h1_data[off:off + CLUSTER_SIZE]
            h1_full_data = h1_full_data[:h1['file_size']]
            
            h2_full_data = b''
            for cluster in h2['fat_chain']:
                off = cluster_to_offset(cluster)
                h2_full_data += h2_data[off:off + CLUSTER_SIZE]
            h2_full_data = h2_full_data[:h2['file_size']]
            
            # Confronta
            min_len = min(len(h1_full_data), len(h2_full_data))
            diff_bytes = sum(1 for i in range(min_len) if h1_full_data[i] != h2_full_data[i])
            
            print(f"    H1 size: {len(h1_full_data):,} bytes")
            print(f"    H2 size: {len(h2_full_data):,} bytes")
            print(f"    Byte diversi: {diff_bytes:,} ({100*diff_bytes/min_len:.2f}%)")

def main():
    print("Caricamento HDD...")
    
    with open(HDD_H1, 'rb') as f:
        h1_data = f.read()
    print(f"H1: {len(h1_data):,} bytes")
    
    with open(HDD_H2, 'rb') as f:
        h2_data = f.read()
    print(f"H2: {len(h2_data):,} bytes")
    
    # Analizza entrambi
    h1_results = find_save_files(h1_data, "H1 (Checkpoint 1)")
    h2_results = find_save_files(h2_data, "H2 (Checkpoint 2)")
    
    # Confronta
    compare_saves(h1_data, h2_data, h1_results, h2_results)
    
    # Riepilogo finale
    print(f"\n{'='*60}")
    print("RIEPILOGO - COSA SERVE PER IL BACKUP")
    print(f"{'='*60}")
    
    if 'auxilary.bin' in h1_results:
        aux = h1_results['auxilary.bin']
        print(f"\n1. Directory entry di auxilary.bin:")
        print(f"   Offset: 0x{aux['entry_offset']:08x}")
        print(f"   (cluster {aux['entry_cluster']})")
        
        print(f"\n2. Dati di auxilary.bin:")
        print(f"   Cluster: {aux['fat_chain'][0]} - {aux['fat_chain'][-1]}")
        print(f"   Totale: {len(aux['fat_chain'])} cluster = {len(aux['fat_chain']) * CLUSTER_SIZE:,} bytes")
        
        print(f"\n3. FAT entries:")
        print(f"   Range: cluster {min(aux['fat_chain'])} - {max(aux['fat_chain'])}")
    
    print("\nFatto!")

if __name__ == "__main__":
    main()
