# Chapter 4 — FATX remap (phase 6.1)

Continues from [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md)
(QCOW2 allocate) and [CHAPTER2_GUEST_AWARE_LAB.md](CHAPTER2_GUEST_AWARE_LAB.md)
(overwrite-only).

This chapter is the piece that makes surgical restore **universal on populated
multi-game disks**: when the backup’s FATX cluster numbers are already used by
other titles, the engine reallocates free clusters and rewrites directory /
FAT metadata accordingly.

It is **not** part of the older `AI_REFERENCE_SESSION*` notes (legacy v5 /
physical-offset era).

| Field | Value |
|--------|--------|
| Report date | 19 July 2026 |
| Scope | Universal restore onto multi-game HDDs (FATX clusters already in use) |
| Backup format | **XBSV v7** unchanged (one backup method) |
| Code | `xemu_lab/remap.py` + free-cluster APIs in `fatx.py` + auto path in `restore.py` |
| QEMU / qemu-img | Excluded |
| Lab entry | `START_XEMU_TEST.bat` → restore |

> Paths such as `D:\xemu\…` are lab-specific. The production surface for players
> is [SaveState](https://github.com/Matteo842/SaveState).

---

## 1. Why a new chapter

Phase 6.0 already solved restore onto **virgin/sparse** disks (QCOW2 allocate +
envelopes). The remaining historical gap: on an **already populated** HDD, the
FATX cluster numbers in the backup (e.g. Black from B1: clusters 5–11) are often
occupied by other Title IDs. Same-guest overwrite there means corruption.

Phase 6.1 is **logical FATX reallocation**: same backup payload, new free
clusters on the target, dirent/FAT rewritten. That is what makes the engine a
truly universal surgical savestate backend — not only something that works on
lucky layouts.

---

## 2. Behaviour (one backup, two restore paths)

The backup stays XBSV v7. Only restore decides:

| Condition | Path | What it does |
|-----------|------|----------------|
| Backup clusters are free, or already belong to the same Title ID on the live disk | **same-guest** | As in Chapters 2/3 (surgical writes ± QCOW2 envelopes) |
| Clusters owned by others / title absent with collision | **remap** | Allocate free clusters, patch `first_cluster`, write new FAT chains, place data at new guest offsets; QCOW2 allocate/RMW at those new offsets |

**Preflight:** if more free clusters are needed than available → error, zero writes.

**Lab menu:** lists UDATA games on the live disk; if the backup’s Title ID is
absent, it asks for explicit confirmation before proceeding (remap runs
automatically when needed).

---

## 3. Architecture (short)

```
XBSV v7  →  decide_restore_path(live FATX)
              ├─ same-guest → pending surgical writes (+ envelopes if allocate)
              └─ remap      → build_remap_plan → pending at new offsets
                                              → apply via QCOW2WritableBlockDevice
```

Modules:

- [`xemu_lab/fatx.py`](xemu_lab/fatx.py) — `find_free_clusters`, `find_directory_slot`,
  `collect_title_clusters`, FAT helpers
- [`xemu_lab/remap.py`](xemu_lab/remap.py) — path decision + `old→new` plan
- [`xemu_lab/restore.py`](xemu_lab/restore.py) — auto path selection; reports
  `mode` / `clusters_remapped`

---

## 4. Human PASS (19 July 2026)

Procedure:

1. Copy golden **HDD5** → `xbox_hdd.qcow2` (Mercenaries + ToeJam + Halo 2 + NFS)
2. Restore **`Black (18-07-26 11-30) v7`** (Title ID absent on the live disk)
3. Lab: `mode=remap`, `remapped=7`, `verified=True`, `envelopes=0`

| Title | After remap | In xemu |
|--------|-------------|---------|
| Black (new) | present | 1% save OK |
| Halo 2 | intact | profile + save OK |
| ToeJam & Earl III | intact | loads OK |
| Mercenaries | intact | OK |
| NFS Underground 2 | intact | OK |

**Interpretation:** this is not a 1:1 dump of the Black source HDD. It is a
**surgical graft** of a single Title ID onto an already-valid multi-game disk.
Sibling saves were not disturbed at gameplay level.

---

## 5. What this proves / remaining limits

**Proves**

- QEMU-free FATX remap on a retail-like multi-game HDD
- Coexistence of same-guest (ToeJam/Merc regression already covered) and remap
  (Black onto HDD5)
- One backup format (v7) for both virgin and multi-game targets

**Known limits (non-blocking for basic savestate use)**

- Remap is UDATA-centric (same as default backup); rich TDATA is not the focus
- When remapping over a Title that already exists, old clusters may be left
  orphaned (no aggressive free-chain reclaim in v1)
- Full UDATA directory (no free slot) → clear error; no automatic directory-chain
  growth in v1
- `verified=True` + `list_games` do not replace an in-xemu verdict — that verdict
  exists for this milestone

---

## 6. Where this sits after ~one year

| Era | Model | Limit |
|-----|--------|--------|
| v5 / merger | host seek ≈ guest | lucky layouts only |
| Chapter 2 | guest-aware overwrite | needs already-allocated QCOW2 clusters |
| Chapter 3 / 6.0 | QCOW2 allocate + envelopes | no FATX remap |
| **Chapter 4 / 6.1** | **FATX remap + allocate** | **universal surgical restore path** |

Product integration of this engine (UI / workflows) is delivered through
[SaveState](https://github.com/Matteo842/SaveState) rather than by reinventing
the block device elsewhere.

---

## 7. Files for this chapter

```
xemu_lab/remap.py
xemu_lab/fatx.py      # + free cluster / slot / title clusters
xemu_lab/restore.py   # auto same-guest | remap
tests/test_qcow2_fatx.py   # FatxAllocAndRemapTests
CHAPTER4_FATX_REMAP.md     # this report
```
