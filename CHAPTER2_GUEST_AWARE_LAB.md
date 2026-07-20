# Chapter 2 — Guest-aware QCOW2/FATX lab (QEMU-free)

This document describes the first production-grade write path for this project:
real QCOW2 L1/L2 mapping, XBSV v6/v7 backups, and overwrite-only restore in
pure Python — **without QEMU**.

It is **not** part of the older `AI_REFERENCE_SESSION*` notes. Those cover the
legacy `single_game_merger.py` era, where host file seeks were often treated as
guest offsets. Do not mix the two eras.

| Field | Value |
|--------|--------|
| Report date | 18 July 2026 |
| Lab entry point | `START_XEMU_TEST.bat` → `xemu_test_lab.py` |
| Current code | `xemu_lab/` |
| Legacy oracle (do **not** use for writes) | `single_game_merger.py` |
| QEMU / qemu-img | Intentionally excluded |

> **Note for readers:** Paths such as `D:\xemu\bk` and `D:\xemu\xbox_hdd.qcow2`
> refer to the author’s local lab layout. This repository is a research lab, not
> a drop-in installer. End-user workflows live in
> [SaveState](https://github.com/Matteo842/SaveState).

---

## 1. Why a new chapter

For months, restores often “worked” because guest offsets were written as if
they were offsets inside the `.qcow2` file. On lucky layouts that coincided with
reality. It was not a correct block device.

Project constraints that shaped this chapter:

- Linux compatibility — no dependency on Windows `qemu.exe`
- `qemu-img convert` had previously rebuilt HDDs with wrong sizes
- Building xemu’s modified QEMU tooling from source (Ubuntu) failed / was incomplete
- Writes were allowed only in Python, on a guest→host mapping already validated read-only

---

## 2. What was built

### Read path (read-only gate)

- `xemu_lab/qcow2.py` — `QCOW2BlockDevice` (read-only): L1/L2, zero/unallocated,
  rejects backing files, encryption, and incompatible features
- `xemu_lab/fatx.py` — fixed Xbox partitions, FATX chains, `E:\UDATA` / `E:\TDATA`
- `xemu_lab/compare.py` — guest-aware diff by region/cluster
- `xemu_lab/catalog.py` — registry via `hdd_backups.json`; uncatalogued files are
  not given invented meanings

### Write path (after the gate)

- `QCOW2WritableBlockDevice.write_at` — **overwrite only** of QCOW2 clusters that
  are already allocated, non-zero, and uncompressed. No allocate-on-write, no
  L2/refcount updates in this chapter’s initial write mode
- `xemu_lab/backup.py` — **XBSV v6/v7** (guest offsets only; v7 adds full QCOW2
  cluster envelopes) + JSON sidecars; human-readable filenames
- `xemu_lab/restore.py` — apply directory → FAT → data (v7: envelopes when
  allocate is enabled), fsync, read-back + FATX Title ID check
- `xemu_lab/safety.py` — require xemu closed; forbid writes under the golden
  backup tree; atomic copy + hash; rollback = recopy golden
- `xemu_lab/titles.py` — display names from the merger `GAME_NAMES` map +
  guest-aware UDATA scan

`single_game_merger.py` was **not** modified and is **not** the write engine.

---

## 3. Forensic gate (before any writes)

| Check | Result | Notes |
|--------|--------|------|
| B1/B2 mapping + 64-byte delta | PASS | CONFIG: 1 byte; E clusters 5/9/11 → 2/2/59 differing bytes |
| H1/H2 guest-aware delta | PASS | Total 428,287,103; Y 427,278,322; E 1,008,759; other 22 |
| B1/B2 in-game | OK | Not corrupted; they remain forensic fixtures, not absolute restore goldens |

---

## 4. Restore validation in xemu (18 July 2026)

Convention used in the lab: backups are taken from goldens under `D:\xemu\bk`
(always opened read-only). Restores write only to the active
`D:\xemu\xbox_hdd.qcow2` (live).

### Baseline / surgical tests

| # | Test | Result |
|---|------|--------|
| 1 | HDD1 Mercenaries cycle (copy + delete + restore) | PASS in-game |
| 2 | Backup/restore ToeJam from HDD2 | PASS |
| 3 | Delete Mercenaries, restore ToeJam only | PASS — Mercenaries stays absent (not a 1:1 HDD dump) |
| 4 | Mercenaries from HDD1 → live based on HDD5 (Merc deleted, other games present) | PASS — Merc OK; Halo / ToeJam / NFS intact |
| 5 | Halo H1 backup → live H2 | PASS — same checkpoint as H1 |
| 6 | Black B1 → live B2 | PASS — 1% |
| 7 | Black B2 → live B1 | PASS — 3% |

### Limit hit, then cleared (allocate / Chapter 3)

| # | Test | Result | Detail |
|---|------|--------|--------|
| 8a | Restore Black onto virgin HDD, overwrite-only | **Controlled FAIL** | compressed / unallocated QCOW2 clusters |
| 8b | Same scenario, **XBSV v7** + allocate | **PASS in-game** (18 Jul 2026) | `Black (18-07-26 11-30) v7`; envelopes=4; 1% save readable |

File-size observation (test 8b): right after the lab restore, the live file was
~1800 KB (smaller than B1 at 2048 KB). After booting xemu and checking the save,
the live file grew back to **2048 KB**. The lab had allocated the four envelopes
needed for the save; xemu, by reading/writing the disk, materialised the rest of
the host footprint that B1 already had. The saves were already correct **before**
that growth.

Allocate / v7 technical report: [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md).

---

## 5. What this proves / what it does not

**Proves**

- Restore is not a blind golden→live copy: other Title IDs on the live disk stay
  as they were
- Cross-golden restore works when the needed QCOW2 clusters are already allocated
  (and uncompressed) on the target
- Halo (hundreds of clusters) and Black checkpoints share the same engine as
  Mercenaries / ToeJam
- With XBSV v7 + allocate: Black restore onto a virgin/sparse HDD **works in-game**
  (not only lab read-back)

**Does not prove** (as of this chapter’s original scope)

- FATX remap onto clusters already used by other Title IDs — resolved in
  [CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md)
- That `verified=True` alone is enough without an in-xemu check

---

## 6. Follow-on phases

- QCOW2 allocate: [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md)
- FATX remap 6.1: [CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md)
  (human PASS 19 Jul 2026)

---

## 7. Files for this chapter

```
xemu_test_lab.py
START_XEMU_TEST.bat
xemu_lab/
  qcow2.py      # read + writable + opt-in allocate
  fatx.py
  compare.py
  catalog.py
  backup.py     # XBSV v6/v7
  restore.py
  safety.py
  titles.py
tests/test_qcow2_fatx.py
surgical_backups_v6/   # backup output (gitignored)
CHAPTER2_GUEST_AWARE_LAB.md   # this report
CHAPTER3_QCOW2_ALLOCATE.md    # phase 6.0 allocate-on-write
CHAPTER4_FATX_REMAP.md        # phase 6.1 FATX remap
```

Do not treat `AI_REFERENCE_SESSION1.md` … `SESSION8.md` (archived) as the
operational spec for the current engine — those describe the v5 / physical-offset era.

---

## 8. Lab operating rules (still valid)

1. Goldens under the lab backup tree → read-only
2. Writes only on the configured active HDD
3. Close xemu before copy/restore
4. B1/B2 are useful forensic fixtures; the first “product-like” write target was
   HDD1, then multi-game / Halo / Black stress
5. No `qemu-img` in the supported path
