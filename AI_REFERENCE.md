# 🔧 Technical Reference for AI Assistants

**This document is specifically designed for future AI chat sessions working on this project.**

---

## 🎯 Quick Context

**Project:** Xbox Save Surgical Restore for xemu emulator
**Status:** WORKING (Version 2 format)
**Main File:** `single_game_merger.py`

---

## ✅ What Works

The **Version 2 (V2) backup format** with **hardcoded metadata_areas** works perfectly:

```python
# In GAMES config:
"4c410015": {
    "name": "Mercenaries",
    "dir_entry_offset": 0x00447000,
    "first_cluster": 4,
    "metadata_areas": [
        (0x0031102c, 112, "Directory_Metadata_Mercenaries"),
        (0x00463040, 64, "SaveEntry_Mercenaries"),
    ],
}
```

---

## ❌ What Does NOT Work

**Version 3 (V3) dynamic FAT32 calculation** - The concept was wrong.

We tried to calculate FAT32 offsets from the game's cluster chain:
```python
# WRONG APPROACH:
fat32_offset = FAT32_TABLE_OFFSET + (cluster * 4)
```

This didn't work because:
- The game FOLDER uses clusters 4, 5, 6, 3225...
- But the SAVE FILES inside use clusters 11-38
- We were calculating offsets for the folder, not the saves

**Do NOT attempt dynamic calculation again without first parsing the directory structure to find save file clusters.**

---

## 🔑 Critical Memory Points

### 1. There Are TWO FAT Tables

| Table | Offset | Format | Purpose |
|-------|--------|--------|---------|
| FAT16 | 0x161000 | 2 bytes/entry | Primary allocation |
| FAT32 | 0x311000 | 4 bytes/entry | Secondary/extended allocation |

**BOTH must be restored for saves to work!**

### 2. The metadata_areas Are NOT What They Seem

The bytes at 0x31102C are NOT FAT32 entries for the game's main cluster chain.
They appear to be allocation data for the SAVE FILES inside the game folder.

### 3. Cluster to Offset Formula

```python
DATA_START = 0x00443000
CLUSTER_SIZE = 16384  # 16KB

def cluster_to_offset(cluster):
    return DATA_START + ((cluster - 2) * CLUSTER_SIZE)
```

### 4. Game Cluster Chains (Non-Overlapping!)

- **Mercenaries:** 4 → 5 → 6 → 3225 → ... → 6110 (2886 clusters)
- **ToeJam:** 39 → 40 → ... → 146 (108 clusters)

Games don't share clusters! This makes surgical restore possible.

---

## 📝 How to Add a New Game

1. **Have both games on HDD** (working backup)
2. **Delete ONLY the new game's save** in xemu
3. **Run comparison:**
   ```python
   # Use analyze_diff_details.py or similar
   # Compare SOURCE (both games) vs TARGET (one deleted)
   ```
4. **Note the differences** in:
   - `Directory_Metadata` (0x300000-0x320000)
   - `Save_Area_Complete` (0x440000-0x470000)
5. **Add to GAMES config:**
   ```python
   "new_game_id": {
       "name": "New Game Name",
       "dir_entry_offset": 0x00447XXX,  # From analysis
       "first_cluster": XX,              # From FAT chain
       "metadata_areas": [
           (0x0031XXXX, size, "Description"),
           # Add all areas that changed
       ],
   }
   ```

---

## 🗂️ Important File Locations

| Purpose | Path |
|---------|------|
| Main script | `single_game_merger.py` |
| Working backup | `D:\xemu\bk\xbox_hdd2.qcow2` |
| Target HDD | `D:\xemu\xbox_hdd.qcow2` |
| Surgical backups | `surgical_backups/` |
| Title ID database | `xbox_title_id_map.json` |

---

## 🔄 Backup Format (V2)

```
XBSV (magic, 4 bytes)
Version (uint32)
Directory Entry Length (uint32)
Directory Entry Data (variable)
FAT Entries Count (uint32)
FAT Entries [(cluster, value) * count]
Data Chunks Count (uint32)
Data Chunks [(cluster, offset, size, data) * count]
Extra Areas Count (uint32)
Extra Areas [(offset, size, data) * count]
Metadata Areas Count (uint32)  <-- V2 ONLY
Metadata Areas [(offset, size, data) * count]
```

---

## ⚠️ Common Mistakes to Avoid

1. **Don't truncate metadata_areas** - They need FULL data, not just 4 bytes
2. **Don't skip FAT32 table** - Restoring only FAT16 causes "damaged" errors
3. **Don't use V3 dynamic calculation** - It's based on wrong assumptions
4. **Always verify with both games** - Test that non-target game is untouched

---

## 🧪 Testing Procedure

1. Copy working backup to target: `xbox_hdd2.qcow2` → `xbox_hdd.qcow2`
2. Delete ONLY target game's save in xemu
3. Run restore command
4. Verify target game works
5. Verify OTHER game was NOT affected (should show "no saves" if it was deleted)

---

## 📊 Session Statistics

- **Analysis scripts created:** 10+
- **Backup format versions:** 3 (only V2 works correctly)
- **Hours spent:** Many (including 5 AM debugging sessions)
- **Final solution:** Hardcoded metadata_areas per game

---

## 💡 Future Improvement Ideas

1. **Parse directory structure** to find save file clusters automatically
2. **Build metadata_areas dynamically** based on save file analysis
3. **Create game profile database** with known working offsets
4. **GUI integration** with SaveState

---

## 🆘 If Restore Fails

1. Check if backup was created with V2 format
2. Verify metadata_areas are being written (check log for "Legacy metadata areas")
3. Ensure BOTH 112-byte and 64-byte areas are written for Mercenaries
4. Try restoring from original backup (`restore_filesystem_areas.py`) to reset

---

*Document created: January 3, 2026*
*Last working test: Mercenaries restore with ToeJam preservation*
