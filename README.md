# 🎮 Xbox Save Surgical Restore Tool

## Current status: READ-ONLY SAFETY GATE

The old v5/v5.5 workflow remains valuable as an empirically tested legacy
oracle, but it interprets physical QCOW2 container offsets as guest disk
offsets. Its restore path must not be used on the active HDD.

[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Read--Only%20Gate-orange.svg)]()

---

## Safe entry point

Run `START_XEMU_TEST.bat`, which opens the single numerical menu implemented by
`xemu_test_lab.py`.

The current build can:

- inspect QCOW2 v3 images through their real L1/L2 mapping;
- parse the fixed Xbox partitions and FATX structures in guest coordinates;
- compare images guest-aware;
- inventory the scenarios from `hdd_backups.json`;
- run the Black B1/B2 and Halo H1/H2 forensic checks.

Backup, restore, golden-to-active copy, and every other write operation are
visible but intentionally blocked. `D:\xemu\bk` and
`D:\xemu\xbox_hdd.qcow2` are never opened for writing.

### Read-only gate result (17 July 2026)

- Black B1/B2: PASS, 64 different guest bytes: CONFIG 1 byte; FATX E data
  clusters 5/9/11 contain 2/2/59 bytes.
- Halo H1/H2: PASS, 428,287,103 different guest bytes: Y cache 427,278,322;
  E data 1,008,759; all other regions 22.
- These checks validate address translation and classification. They do not
  prove that B1 or B2 is gameplay-safe.
- The write gate remains closed. The first future restore test will use HDD 1
  on a verified active copy, never B1/B2 as a trusted golden source.

The remainder of this README records the historical v5-era behavior and manual
test evidence. Its old physical-offset explanations are not the specification
for the new implementation.

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
| **v5** | **FAT Range + Dynamic** | **Empirically successful legacy; host-offset model** |
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

```bat
START_XEMU_TEST.bat
```

### Menu Options

```
1. Ciclo test completo                 [BLOCCATO]
2. Solo backup save                    [BLOCCATO]
3. Solo restore save                   [BLOCCATO]
4. Ripristina HDD attivo da golden     [BLOCCATO]
5. Analizza/confronta HDD
6. Catalogo HDD e risultati
0. Exit
```

### Configuration

Paths and scenario descriptions are read from `hdd_backups.json`; the active
path is also checked against xemu's `xemu.toml`. Do not launch
`single_game_merger.py` for restore: it is retained only as the v5.5 legacy
oracle until a safe write backend exists.

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
| Jan 4, 2026 | **Manual surgical restore checkpoint (legacy v5-era workflow)** |

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
