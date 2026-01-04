# 🎮 Xbox Save Surgical Restore Tool

## 🏆 Project Status: PRODUCTION READY (v5.1)

**Surgical backup and restore for Xbox game saves on xemu emulator** - A sophisticated tool that enables per-game backup and restore operations without affecting other games on the same virtual HDD.

[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)]()

---

## 🎯 Quick Summary

This project solves a complex challenge: **surgically restoring individual Xbox game saves** from a monolithic virtual HDD image. While Xbox xemu uses a single 8GB QCOW2 file containing ALL game saves, this tool can:

- ✅ **Backup** a single game's save data (~17KB-3MB depending on game)
- ✅ **Restore** that save without touching other games
- ✅ **Preserve** other games' data integrity during restore operations
- ✅ **Handle** various game save structures (standard, FAT chain, sibling slots)

---

## 📊 Test Results

### Verified Working Games (January 2026)

| Game | Title ID | Restore Method | Status |
|------|----------|----------------|--------|
| **Mercenaries** | 4c410015 | Dynamic v5 | ✅ Perfect |
| **Halo 2** | 4d530064 | FAT Range v5 | ✅ Perfect |
| **NFS Underground 2** | 4541005a | Dynamic v5 + Cluster Fix | ✅ Perfect |
| **ToeJam & Earl III** | 5345000f | Custom Areas | ⚠️ Requires hardcoded approach |

### Surgical Restore Test (Final Verification)

Starting from an HDD with **all saves deleted**:

1. **Restored Mercenaries only** → Mercenaries loads ✅
2. **Checked Halo 2** → "Create new profile" ✅ (no false data)
3. **Checked ToeJam** → "No save available" ✅ (no corruption)
4. **Checked NFS** → "Create new profile?" ✅ (clean state)

**Result: 100% surgical precision** - Only the target game's save was restored.

---

## 🔧 The Technical Challenge

### Why This Was Difficult

The Xbox FATX filesystem presents unique challenges:

```
┌─────────────────────────────────────────────────────────────┐
│                    QCOW2 Virtual HDD                        │
├─────────────────────────────────────────────────────────────┤
│  FAT16 Table (0x161000)  │  FAT32 Table (0x311000)          │
├─────────────────────────────────────────────────────────────┤
│  Directory Entries (0x443000+)                              │
│  ├── TDATA (game assets)                                    │
│  └── UDATA (save data)                                      │
│       ├── 4c410015/ (Mercenaries)                           │
│       ├── 4d530064/ (Halo 2)                                │
│       └── 5345000f/ (ToeJam)                                │
├─────────────────────────────────────────────────────────────┤
│  Data Clusters (16KB each, interleaved across games)        │
└─────────────────────────────────────────────────────────────┘
```

**Problems discovered during development:**

1. **Dual FAT Tables** - Both FAT16 and FAT32 must be synchronized
2. **Collateral Clusters** - Deleting a save modifies clusters outside its chain
3. **Variable Save Structures** - Each game organizes saves differently:
   - Standard: Subdirectories within game folder
   - Direct Data: Raw data in game folder (no directory entries)
   - Sibling Slots: Save slots as siblings in UDATA (not children)
   - Offset Entries: Directory entries in cluster N+1 instead of N

---

## ⚙️ Architecture

### Version Evolution

| Version | Approach | Limitations |
|---------|----------|-------------|
| v2 | Hardcoded metadata areas | Game-specific, not scalable |
| v3 | Dynamic FAT calculation | Failed due to incorrect assumptions |
| v4 | Dynamic cluster analysis | Worked for some games, missed collateral clusters |
| **v5** | **FAT Range + Dynamic** | **Production solution** |
| v5.1 | Sibling slots + Cluster offset fix | Extended compatibility |

### v5 FAT Range Strategy

Instead of backing up individual FAT entries, v5 backs up a **contiguous range** of the FAT table:

```python
# Calculate FAT range with safety margin
min_cluster = min(game_clusters)
max_cluster = max(game_clusters)
fat_range_start = max(0, min_cluster - 100)
fat_range_end = max_cluster + 100

# Save entire FAT block
fat16_range = read_fat16_block(fat_range_start, fat_range_end)
fat32_range = read_fat32_block(fat_range_start, fat_range_end)
```

This captures all "collateral" changes that occur when games are deleted.

---

## 📁 Project Structure

```
xemu_tools/
├── single_game_merger.py      # Main script (v5.1)
├── diff_complete.py           # HDD comparison utility
├── xbox_title_id_map.json     # Game name database
├── surgical_backups/          # Backup storage
│   ├── {titleid}_fatrange_{timestamp}.bin
│   └── {titleid}_fatrange_{timestamp}.json
├── AI_REFERENCE.md            # Technical documentation
├── AI_REFERENCE_SESSION2.md   # Session 2 discoveries
├── AI_REFERENCE_SESSION3.md   # Session 3 (v5 implementation)
└── README.md                  # This file
```

---

## 🚀 Usage

### Quick Start

```bash
python single_game_merger.py
```

### Menu Options

```
1. List available games
2. Backup FAT RANGE v5 (RECOMMENDED)
3. Backup dynamic v4 (legacy)
4. Restore (auto-detect version)
5. List backups
0. Exit
```

### Configuration

Edit paths at the top of `single_game_merger.py`:

```python
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd_backup.qcow2"  # Source (read-only)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"            # Target (modified)
BACKUP_DIR = r"d:\GitHub\xemu_tools\surgical_backups"
```

---

## 🔬 Technical Deep Dive

### Key Constants

```python
FAT16_OFFSET = 0x00161000    # Primary FAT table
FAT32_OFFSET = 0x00311000    # Secondary FAT table  
DATA_START = 0x00443000      # Cluster data begins here
CLUSTER_SIZE = 16384         # 16KB per cluster
ENTRY_SIZE = 64              # Directory entry size
```

### Cluster Calculation

```python
def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)

def offset_to_cluster(offset):
    return (offset - DATA_START) // CLUSTER_SIZE + 2
```

### Backup Format (XBSV v5)

```
┌──────────────────────────────────────┐
│ Magic: "XBSV" (4 bytes)              │
│ Version: 5 (4 bytes)                 │
│ Game ID: 8 bytes                     │
│ FAT Range: start, end (8 bytes)      │
├──────────────────────────────────────┤
│ Directory Entries Block              │
│ FAT16 Range Block                    │
│ FAT32 Range Block                    │
│ Data Clusters Block                  │
└──────────────────────────────────────┘
```

---

## 🔍 Discovery Process

### How We Found the Solution

**Phase 1: Initial Analysis**
- Compared HDD dumps before/after game deletion
- Identified FAT16, FAT32, and directory entry locations
- Mapped game clusters using FAT chain traversal

**Phase 2: v4 Dynamic Approach**
- Automated FAT chain following
- Worked for Mercenaries, failed for Halo 2
- Discovered "collateral clusters" problem

**Phase 3: v5 FAT Range**
- Switched to range-based FAT backup
- Solved Halo 2 problem completely
- Tested with NFS Underground 2 (different structure)

**Phase 4: Extended Compatibility (v5.1)**
- Added brute-force cluster scanning (cluster 3-15)
- Implemented sibling save slot detection
- Added cluster+1 fallback for offset entries

---

## ⚠️ Known Limitations

1. **ToeJam & Earl III** - Requires custom hardcoded approach (extremely non-standard structure)
2. **New Games** - May require testing to verify compatibility
3. **Large FAT Ranges** - Multi-game HDDs create larger backup files (~3MB vs ~17KB)

---

## 🔗 Integration with SaveState

This tool is designed to integrate with [SaveState](https://github.com/...), a universal game save manager:

- SaveState handles UI and profile management
- xemu_tools provides the surgical backup/restore engine
- Communication via command-line or library import

---

## 📈 Development Timeline

| Date | Milestone |
|------|-----------|
| Aug 2025 | Project started, initial FATX analysis |
| Sep 2025 | v2 hardcoded approach working |
| Dec 2025 | v4 dynamic approach, partial success |
| Jan 3, 2026 | v5 FAT Range solves Halo 2 |
| Jan 4, 2026 | v5.1 extended compatibility, NFS working |
| Jan 4, 2026 | **Production ready, surgical restore verified** |

---

## 🤝 Contributing

This project demonstrates:
- Low-level filesystem analysis
- Binary file manipulation
- Reverse engineering techniques
- Iterative problem-solving

Contributions welcome for:
- Additional game compatibility testing
- Performance optimization
- GUI development
- Documentation improvements

---

## 📄 License

MIT License - See LICENSE file for details.

---

## 🙏 Acknowledgments

- xemu team for the Xbox emulator
- Xbox homebrew community for FATX documentation
- Extensive testing across multiple game titles

---

*Built with precision engineering and extensive testing. Every byte matters.*
