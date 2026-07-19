#!/usr/bin/env python3
"""Analizza struttura HDD Halo 2"""
import struct

HDD = r"D:\xemu\bk\xbox_hddh1.qcow2"
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
FAT_OFFSET = 0x00161000

with open(HDD, 'rb') as f:
    data = f.read()

print(f"HDD Size: {len(data):,} bytes")

# Analizza cluster 11310 dove c'è SaveMeta.xbx
cluster = 11310
offset = DATA_START + (cluster - 2) * CLUSTER_SIZE
print(f"\n=== Cluster 11310 (offset 0x{offset:08x}) ===")

# Cerca directory entries
for i in range(CLUSTER_SIZE // 64):
    ent = data[offset + i*64:offset + i*64 + 64]
    fn_len = ent[0]
    if fn_len > 0 and fn_len < 43 and fn_len != 0xFF and fn_len != 0xE5:
        try:
            name = ent[2:2+fn_len].decode('ascii', errors='replace').rstrip()
            first_cluster = struct.unpack('<I', ent[44:48])[0]
            size = struct.unpack('<I', ent[48:52])[0]
            is_dir = ent[1] & 0x10
            t = "DIR" if is_dir else "FILE"
            print(f"  {t:4} {name:25} cluster={first_cluster:5} size={size:,}")
        except:
            pass

# Cerca auxilary.bin
print("\nCerco auxilary.bin...")
pos = 0
while True:
    pos = data.find(b'auxilary.bin', pos)
    if pos == -1:
        break
    cluster = (pos - DATA_START) // CLUSTER_SIZE + 2 if pos >= DATA_START else 'pre-data'
    entry_start = pos - 2
    fc = struct.unpack('<I', data[entry_start + 44:entry_start + 48])[0]
    sz = struct.unpack('<I', data[entry_start + 48:entry_start + 52])[0]
    print(f"  Offset 0x{pos:08x}, cluster {cluster}, first_cluster={fc}, size={sz:,}")
    pos += 1

# Cerca profile
print("\nCerco profile...")
pos = 0
while True:
    pos = data.find(b'\x07\x00profile', pos)  # 7 byte filename
    if pos == -1:
        break
    cluster = (pos - DATA_START) // CLUSTER_SIZE + 2 if pos >= DATA_START else 'pre-data'
    fc = struct.unpack('<I', data[pos + 44:pos + 48])[0]
    sz = struct.unpack('<I', data[pos + 48:pos + 52])[0]
    print(f"  Offset 0x{pos:08x}, cluster {cluster}, first_cluster={fc}, size={sz:,}")
    pos += 1
