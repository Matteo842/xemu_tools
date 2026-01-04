# 🎮 Xbox Save Surgical Restore Tool

## 🏆 Project Status: WORKING! (v5 - FAT Range)

**Single-game backup and restore for Xbox saves on xemu emulator** - A tool that can backup and restore individual game saves without affecting other games on the same virtual HDD.

**Latest Update:** v5 with FAT Range - Now works with ALL tested games including Halo 2!

---

## 📋 Table of Contents

1. [The Problem](#-the-problem)
2. [The Solution](#-the-solution)
3. [How It Works](#-how-it-works)
4. [Technical Discoveries](#-technical-discoveries)
5. [File Structure](#-file-structure)
6. [Usage](#-usage)
7. [Critical Information for Future Development](#-critical-information-for-future-development)
8. [Known Limitations](#-known-limitations)
9. [Integration with SaveState](#-integration-with-savestate)
10. [Development History](#-development-history)

---

## 🔴 The Problem

When working with Xbox emulator (xemu) save files:

1. **xemu uses a single QCOW2 file** (`xbox_hdd.qcow2`) that contains ALL game saves
2. **Traditional backup methods** backup the entire HDD (8GB) or overwrite shared areas
3. **Overwriting shared areas corrupts other games** - restoring one game would destroy saves of other games
4. **No existing tool** could surgically restore just ONE game's save data

### Why This Was Hard

The Xbox FATX filesystem has:
- **Multiple FAT tables** (FAT16 at 0x161000, FAT32 at 0x311000)
- **Shared directory structures** (UDATA, TDATA folders)
- **Interleaved data** (games can use non-contiguous clusters)
- **Critical metadata** that must be restored alongside data
- **Collateral clusters** that get modified when deleting saves (discovered in v5!)

---

## ✅ The Solution

We developed a **surgical backup/restore system** that:

1. **Identifies** exactly which clusters belong to a specific game
2. **Extracts** only those clusters + a FAT RANGE with safety margin
3. **Restores** ONLY those areas, leaving other games untouched

### Proven Results (v5 - January 2026)

| Test Case | Result |
|-----------|--------|
| Restore Mercenaries with ToeJam deleted | ✅ Mercenaries works, ToeJam stays deleted |
| Restore Mercenaries with ToeJam present | ✅ Both games work |
| **Restore Halo 2 with other games deleted** | ✅ **Halo 2 works, others stay deleted** |
| Data integrity after restore | ✅ Saves load and play correctly |

---

## ⚙️ How It Works

### Backup Process

```
1. Read HDD source file (QCOW2)
2. Find game's directory entry by Title ID (e.g., "4c410015")
3. Follow FAT chain to identify all clusters used by the game
4. Extract:
   - Directory entry (64 bytes)
   - FAT16 entries (2 bytes each)
   - Data clusters (16KB each)
   - Extra areas (where title ID appears)
   - Critical metadata areas (hardcoded for now)
5. Save to binary file with XBSV format
```

### Restore Process

```
1. Read backup file and verify hash
2. For each component:
   - Write directory entry to original offset
   - Write FAT16 entries to FAT table
   - Write data clusters to calculated offsets
   - Write extra areas
   - Write critical metadata (FAT32 entries, save entries)
3. Flush and sync to ensure data is written
```

---

## 🔬 Technical Discoveries

### FATX Filesystem Structure (for this specific HDD layout)

| Area | Offset | Size | Description |
|------|--------|------|-------------|
| QCOW2 Header | 0x000000 | Variable | QCOW2 file format header |
| FAT16 Table | 0x161000 | 64KB | Primary FAT table (2 bytes per cluster) |
| FAT32 Table | 0x311000 | 128KB+ | Secondary FAT table (4 bytes per cluster) |
| Directory Start | 0x443000 | - | DATA_START - where cluster data begins |
| UDATA Directory | 0x447000 | - | User save data directory entries |

### Key Constants

```python
FAT_TABLE_OFFSET = 0x00161000   # FAT16 Table
FAT32_TABLE_OFFSET = 0x00311000 # FAT32 Table (CRITICAL!)
CLUSTER_SIZE = 16384            # 16KB per cluster
DATA_START = 0x00443000         # Where cluster data begins
GAME_DIR_OFFSET = 0x00447000    # Game directory entries
ENTRY_SIZE = 64                 # Each directory entry
```

### Cluster to Offset Formula

```python
def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)
```

### FAT32 Entry Offset Formula

```python
def fat32_entry_offset(cluster):
    return FAT32_TABLE_OFFSET + (cluster * 4)
```

### Critical Metadata Areas (Game-Specific)

These were discovered by comparing HDDs with and without specific games:

**Mercenaries (4c410015):**
- `0x0031102C` - 112 bytes (FAT32/allocation entries)
- `0x00463040` - 64 bytes (Save directory entry)

**ToeJam & Earl III (5345000f):**
- `0x003110B4` - 32 bytes (FAT32/allocation entries)

### FAT Chain Examples

**Mercenaries:**
- First cluster: 4
- Chain: 4 → 5 → 6 → 3225 → 3226 → ... → 6110 (END)
- Total: 2886 clusters (~46 MB)

**ToeJam & Earl III:**
- First cluster: 39
- Chain: 39 → 40 → 41 → ... → 146 (END)
- Total: 108 clusters (~1.7 MB)

---

## 📁 File Structure

### Core Files

| File | Purpose |
|------|---------|
| `single_game_merger.py` | **MAIN SCRIPT** - Backup and restore single games |
| `restore_filesystem_areas.py` | Full restore (all 13 critical areas) - always works |
| `xbox_title_id_map.json` | Title ID to game name mapping database |
| `xbox_hdd_reader_fixed.py` | HDD scanning and game detection |

### Analysis Scripts (Used for Research)

| File | Purpose |
|------|---------|
| `analyze_qcow2_fatx.py` | Analyze QCOW2/FATX structure |
| `analyze_fat_chains.py` | Trace FAT chains for games |
| `analyze_diff_details.py` | Compare two HDDs byte-by-byte |
| `verify_data_start.py` | Verify DATA_START offset |
| `analyze_metadata_structure.py` | Analyze FAT32 table structure |

### Backup Storage

| Directory | Contents |
|-----------|----------|
| `surgical_backups/` | Surgical backup files (.bin + .json) |

---

## 🚀 Usage

### Prerequisites

```bash
# Python 3.x required
# No external dependencies needed (pure Python)
```

### Configuration

Edit paths in `single_game_merger.py`:

```python
HDD_SOURCE = r"D:\xemu\bk\xbox_hdd2.qcow2"  # Backup (READ ONLY)
HDD_TARGET = r"D:\xemu\xbox_hdd.qcow2"       # Target to modify
BACKUP_DIR = r"d:\GitHub\xemu_tools\surgical_backups"
```

### Creating a Backup

```python
from single_game_merger import backup_single_game

# Backup Mercenaries
backup_single_game("4c410015")

# Backup ToeJam & Earl III
backup_single_game("5345000f")
```

### Restoring a Backup

```python
from single_game_merger import restore_single_game

backup_file = r"surgical_backups\4c410015_surgical_20260102_060557.bin"
metadata_file = r"surgical_backups\4c410015_surgical_20260102_060557.json"

restore_single_game(backup_file, metadata_file)
```

### Interactive Mode

```bash
python single_game_merger.py
```

---

## ⚠️ Critical Information for Future Development

### What MUST Be Preserved

1. **Backup Format Version 2** uses `metadata_areas` with hardcoded offsets - THIS WORKS
2. **Version 3** attempted dynamic FAT32 calculation - DID NOT WORK (wrong concept)
3. The **metadata_areas** are NOT simple FAT32 entries of the game's cluster chain
4. The metadata appears to be allocation data for SAVE FILES inside the game folder

### Why Dynamic Calculation Failed

The FAT chain for "4c410015" gives clusters: 4, 5, 6, 3225...

Expected FAT32 offsets:
- Cluster 4 → 0x311010
- Cluster 5 → 0x311014
- etc.

BUT the actual differences when Mercenaries was deleted were at:
- 0x31102C (cluster 11)
- 0x311030 (cluster 12)
- etc.

**Conclusion:** The clusters 11-38 are used by SAVE FILES inside the Mercenaries folder, NOT the folder itself. The folder uses clusters 4-6, 3225+, but the SAVES inside use different clusters.

### To Make It Truly Dynamic

We would need to:
1. Parse the game's directory at cluster 4
2. Find all subdirectories (save slots)
3. For each subdirectory, get its cluster chain
4. Calculate metadata areas for ALL those clusters

### What Works Now

The **hardcoded approach (V2)** works perfectly for the specific games we tested. To add new games:

1. Have both games on HDD
2. Delete the new game's save
3. Compare with original using `analyze_diff_details.py`
4. Note which bytes changed in `Directory_Metadata` and `Save_Area_Complete`
5. Add those offsets to the GAMES config in `single_game_merger.py`

---

## 🔒 Known Limitations

1. **Hardcoded offsets** - Each game needs its metadata_areas discovered manually
2. **HDD-specific** - Offsets may differ on HDDs with different game install order
3. **QCOW2 only** - Designed for QCOW2 format (xemu default)
4. **Two games tested** - Mercenaries and ToeJam & Earl III confirmed working

---

## 🔗 Integration with SaveState

This tool is designed to integrate with the SaveState backup manager:

1. **SaveState detects xemu** and finds Xbox games using `xbox_hdd_reader_fixed.py`
2. **User selects a game** to backup/restore
3. **SaveState calls** `single_game_merger.py` functions
4. **Surgical backup/restore** preserves other games

### Files in emulator_utils/xemu_tools/

These may need to be updated to use the new surgical approach instead of the area-based approach.

---

## 📜 Development History

### The Journey (January 2026)

1. **Initial Problem:** User wanted to backup/restore individual Xbox game saves
2. **First Attempts:** Used `restore_filesystem_areas.py` which restored ALL 13 critical areas - worked but affected all games
3. **Analysis Phase:** Deep-dived into FATX structure using custom analysis scripts
4. **Discovery:** Found the FAT16 table at 0x161000 and FAT32 table at 0x311000
5. **Key Insight:** Identified that games use non-overlapping clusters (Mercenaries: 4-6, 3225+; ToeJam: 39-146)
6. **First Success:** Implemented surgical restore that wrote directory entry + FAT entries + data clusters
7. **Still Broken:** Game saves wouldn't load - missing critical metadata
8. **Breakthrough:** Compared HDD with/without each game to find the EXACT bytes that change
9. **Final Fix:** Added `metadata_areas` for each game - 112 bytes at 0x31102C (FAT32) and 64 bytes at 0x463040 (save entry)
10. **Victory:** Full surgical backup/restore working!

### Key Commits

- Initial FATX analysis and structure discovery
- FAT chain following implementation
- Surgical backup/restore V1 (incomplete)
- Metadata areas discovery
- V2 format with hardcoded metadata (WORKING!)
- V3 dynamic attempt (failed - wrong approach)
- V2 compatibility fix

---

## 🙏 Acknowledgments

This project was developed through extensive reverse engineering of the Xbox FATX filesystem, with no existing documentation for the specific QCOW2 layout used by xemu.

Special thanks to:
- The xemu emulator project
- SaveState backup manager project
- Hours of binary diff analysis at 5 AM 😴

---

## 📄 License

This project is part of the SaveState ecosystem. See main SaveState repository for license information.

---

## 🚧 TODO for Future Development

- [ ] Automate metadata area discovery for new games
- [ ] Parse save subdirectories to calculate areas dynamically
- [ ] Add more games to the database
- [ ] Create GUI integration with SaveState
- [ ] Test on different HDD configurations
- [ ] Add support for RAW HDD images (in addition to QCOW2)

---

**Made with ☕ and determination**

*"It's not about having the right answer, it's about having the patience to find it."*
