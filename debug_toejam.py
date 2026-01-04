#!/usr/bin/env python3
"""Debug ToeJam structure - capire perché non funziona"""

import struct

HDD = r"D:\xemu\bk\xbox_hdd2.qcow2"
FAT_TABLE_OFFSET = 0x00161000
FAT32_TABLE_OFFSET = 0x00311000
CLUSTER_SIZE = 16384
DATA_START = 0x00443000

def cluster_to_offset(c):
    return DATA_START + ((c - 2) * CLUSTER_SIZE)

def read_fat16(data, cluster):
    offset = FAT_TABLE_OFFSET + (cluster * 2)
    if offset + 2 > len(data): return 0xFFFF
    return struct.unpack('<H', data[offset:offset + 2])[0]

def get_fat_chain(data, first, max_len=200):
    if first == 0 or first >= 0xFFF0: return []
    chain = [first]
    current = first
    for _ in range(max_len):
        next_c = read_fat16(data, current)
        if next_c >= 0xFFF8 or next_c == 0: break
        if next_c in chain: break
        chain.append(next_c)
        current = next_c
    return chain

def hex_dump(data, offset, length=256):
    for i in range(0, min(len(data), length), 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f"  0x{offset + i:08x}: {hex_part:<48} {ascii_part}")

print("=" * 70)
print("DEBUG TOEJAM STRUCTURE")
print("=" * 70)

with open(HDD, 'rb') as f:
    data = f.read()

print(f"File: {len(data):,} bytes")

# 1. Trova entry ToeJam in UDATA (cluster 4)
print("\n" + "=" * 70)
print("1. UDATA CLUSTER 4 - Directory entries")
print("=" * 70)

c4_offset = cluster_to_offset(4)
print(f"Cluster 4 offset: 0x{c4_offset:08x}")

# Scan entries
for i in range(10):
    entry_offset = c4_offset + (i * 64)
    entry = data[entry_offset:entry_offset + 64]
    fn_len = entry[0]
    
    if fn_len == 0xFF or fn_len == 0x00:
        continue
    
    attrs = entry[1]
    fn = entry[2:2+min(fn_len, 42)].decode('ascii', errors='replace')
    fc = struct.unpack('<I', entry[44:48])[0]
    fs = struct.unpack('<I', entry[48:52])[0]
    
    is_dir = "DIR" if attrs & 0x10 else "FILE"
    print(f"  Entry {i}: {is_dir} '{fn}' cluster={fc} size={fs}")

# 2. ToeJam entry details
print("\n" + "=" * 70)
print("2. TOEJAM ENTRY IN UDATA")
print("=" * 70)

# ToeJam should be at 0x44b040 based on earlier analysis
toejam_entry_offset = c4_offset + 64  # Second entry
toejam_entry = data[toejam_entry_offset:toejam_entry_offset + 64]
print(f"ToeJam entry @ 0x{toejam_entry_offset:08x}:")
hex_dump(toejam_entry, toejam_entry_offset, 64)

fn_len = toejam_entry[0]
attrs = toejam_entry[1]
fn = toejam_entry[2:2+fn_len].decode('ascii', errors='replace')
fc = struct.unpack('<I', toejam_entry[44:48])[0]
print(f"\n  Filename: '{fn}' (len={fn_len})")
print(f"  Attributes: 0x{attrs:02x} ({'DIR' if attrs & 0x10 else 'FILE'})")
print(f"  First cluster: {fc}")

# 3. ToeJam folder content (cluster pointed by entry)
print("\n" + "=" * 70)
print(f"3. TOEJAM FOLDER CONTENT (cluster {fc})")
print("=" * 70)

toejam_cluster_offset = cluster_to_offset(fc)
print(f"Cluster {fc} offset: 0x{toejam_cluster_offset:08x}")
print("\nPrimi 256 bytes del cluster:")
cluster_data = data[toejam_cluster_offset:toejam_cluster_offset + 256]
hex_dump(cluster_data, toejam_cluster_offset, 256)

# Check if this looks like directory entries
print("\n\nAnalisi: questo cluster contiene directory entries?")
first_byte = cluster_data[0]
if 1 <= first_byte <= 42:
    print(f"  Primo byte = {first_byte} -> potrebbe essere filename length")
    # Try to parse as entry
    fn = cluster_data[2:2+first_byte].decode('ascii', errors='replace')
    print(f"  Possible filename: '{fn}'")
else:
    print(f"  Primo byte = 0x{first_byte:02x} -> NON sembra una directory entry")
    print("  Questo cluster contiene DATI, non directory entries!")

# 4. FAT chain di ToeJam
print("\n" + "=" * 70)
print(f"4. FAT CHAIN DI TOEJAM (cluster {fc})")
print("=" * 70)

chain = get_fat_chain(data, fc)
print(f"Chain length: {len(chain)} clusters")
print(f"First 20: {chain[:20]}")
if len(chain) > 20:
    print(f"Last 20: {chain[-20:]}")

# 5. Cerca pattern ToeJam nell'HDD
print("\n" + "=" * 70)
print("5. CERCA 'ToeJam' O 'SaveMeta' NELL'HDD")
print("=" * 70)

# Search for SaveMeta.xbx pattern (common in Xbox saves)
search_patterns = [b"SaveMeta", b"TitleMeta", b"5345000f"]
for pattern in search_patterns:
    pos = 0
    found = []
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break
        found.append(pos)
        pos += 1
        if len(found) >= 10:
            break
    
    if found:
        print(f"\n  Pattern '{pattern.decode('ascii', errors='replace')}':")
        for offset in found[:5]:
            # Calculate which cluster
            if offset >= DATA_START:
                cluster = (offset - DATA_START) // CLUSTER_SIZE + 2
                offset_in_cluster = (offset - DATA_START) % CLUSTER_SIZE
                print(f"    0x{offset:08x} (cluster {cluster}, offset 0x{offset_in_cluster:04x})")
            else:
                print(f"    0x{offset:08x}")

# 6. Confronta con Mercenaries per vedere la differenza
print("\n" + "=" * 70)
print("6. CONFRONTO CON MERCENARIES")
print("=" * 70)

# Mercenaries cluster 5
merc_cluster_offset = cluster_to_offset(5)
print(f"\nMercenaries (cluster 5) @ 0x{merc_cluster_offset:08x}:")
merc_data = data[merc_cluster_offset:merc_cluster_offset + 256]
hex_dump(merc_data, merc_cluster_offset, 128)

print(f"\nToeJam (cluster {fc}) @ 0x{toejam_cluster_offset:08x}:")
hex_dump(cluster_data, toejam_cluster_offset, 128)

print("\n" + "=" * 70)
print("CONCLUSIONE")
print("=" * 70)
