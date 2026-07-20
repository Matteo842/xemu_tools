# xemu_tools

**Research lab and engine for surgical Xbox Original save backup/restore on xemu QCOW2 HDDs.**

After roughly one year of work (started August 2025), this project became — to our knowledge — the **first** system that can correctly **extract** a first-generation Xbox game save from a virtual HDD and **put it back in the right place**, including on disks where that game was **never launched**.

End users should not start here. The production implementation lives in **[SaveState](https://github.com/Matteo842/SaveState)**.

---

## If you want to use this

| Audience | Where to go |
|----------|-------------|
| **Players / save managers** | **[SaveState](https://github.com/Matteo842/SaveState)** — UI, workflows, and the integrated surgical engine |
| **Researchers / journalists / developers** | This repository — method, lab notes, and the QEMU-free stack under `xemu_lab/` |

This repo is a **personal forensic laboratory**. Paths, golden images, batch launchers, and menus assume a fixed local layout (e.g. `D:\xemu\…`). It is **not** a drop-in tool for arbitrary PCs — at least not yet.

---

## Why this matters

xemu stores Xbox saves inside a single large **QCOW2** virtual hard disk with a **FATX** filesystem. Saves for many titles share that image. The hard problems are not “copy some files”:

1. **Guest ≠ host** — a guest byte offset is not a file offset into the `.qcow2`. Real L1/L2 mapping is required.
2. **Sparse / virgin disks** — if the game was never run, the clusters for its save may be unallocated or compressed. Blind overwrite fails; allocate-on-write with full QCOW2 cluster envelopes is required.
3. **Busy multi-game disks** — cluster numbers from the backup are often already used by other titles. Correct restore needs **FATX remapping** onto free clusters, not stomping existing games.

Earlier approaches (legacy “v5” merger era) often appeared to work when host seek ≈ guest by luck. The current stack is **guest-aware**, **QEMU-free** (no `qemu-img` / QEMU in the supported path), and chooses restore automatically:

- **same-guest** — overwrite allocated clusters (+ optional allocate / envelopes on sparse targets)
- **remap** — reallocate free FATX clusters, rewrite dirent/FAT, write data at new guest offsets

Backup format: **XBSV v7** (surgical segments + QCOW2 cluster envelopes). One backup format; the restore path decides.

---

## What was proven in lab (July 2026)

Human-verified in xemu, not only `verified=True` in Python:

| Scenario | Result |
|----------|--------|
| Surgical restore of one title without corrupting others | PASS |
| Cross-golden restore (e.g. Halo / Black checkpoints) when clusters are allocated | PASS |
| **Black on a virgin/sparse HDD** via XBSV v7 + QCOW2 allocate | PASS in-game |
| **Black remapped onto a populated multi-game HDD** (Mercenaries, ToeJam, Halo 2, NFS present; Black never launched there) | PASS — Black save OK; other titles intact |

Technical write-ups:

- [CHAPTER2_GUEST_AWARE_LAB.md](CHAPTER2_GUEST_AWARE_LAB.md) — guest-aware QCOW2/FATX lab, overwrite-only era  
- [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md) — allocate-on-write + XBSV v7 envelopes  
- [CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md) — FATX remap for universal multi-game restore  

---

## Architecture (current)

```
xemu_lab/
  qcow2.py    # L1/L2 block device: read, overwrite, opt-in allocate
  fatx.py     # Fixed Xbox partitions + FATX (UDATA/TDATA)
  backup.py   # XBSV v6/v7 surgical backup
  restore.py  # Auto same-guest | remap
  remap.py    # Free-cluster plan old→new
  compare.py  # Guest-aware image diff
  catalog.py  # Lab HDD registry
  safety.py   # xemu closed, goldens read-only, atomic copy + hash
  titles.py   # Title ID display names

xemu_test_lab.py      # Numerical lab menu (local environment)
START_XEMU_TEST.bat   # Entry for that menu
tests/                # Automated QCOW2/FATX/remap checks
```

Legacy discovery scripts and older session notes live under `old_script/`, `old_script_2/`, and `old_AI_referance/`. They are history, not the write engine.

**Evolution (short):**

| Era | Model | Limit |
|-----|--------|--------|
| v5 / merger | host seek ≈ guest | lucky layouts only |
| Chapter 2 | guest-aware overwrite | needs allocated QCOW2 clusters |
| Chapter 3 | allocate + envelopes | no FATX remap |
| **Chapter 4** | **remap + allocate** | **universal surgical restore path** |

---

## For press / technical articles

Suggested framing:

- **Problem:** first Xbox saves trapped in one QCOW2+FATX image; prior tools either dumped whole disks or restored only when cluster layout already matched.
- **Result:** title-level extract/restore that works on virgin disks and on disks where the title never ran, without replacing the whole HDD or wiping sibling games.
- **Method:** pure-Python guest block device over QCOW2, FATX-aware backup (XBSV v7), then restore via overwrite, allocate, or remap as needed — no QEMU dependency in the supported pipeline.
- **Product surface:** [SaveState](https://github.com/Matteo842/SaveState); this repo is the R&D and documentation trail (~Aug 2025 → Jul 2026 for the guest-aware / remap milestone).

Author: [Matteo842](https://github.com/Matteo842).

---

## Safety rules (lab)

1. Golden images under the lab backup tree are **read-only**.
2. Writes only on the configured active HDD copy.
3. xemu must be closed before copy/restore.
4. Allocate / remap are not crash-atomic mid-write — work on a copy; restore from golden if interrupted.
5. Lab `verified=True` is necessary but not sufficient; in-game checks in xemu were part of the milestone.

---

## Known limits (engine v1)

- UDATA-centric (rich TDATA is not the focus).
- Remapping over an existing title may leave orphaned old clusters (no aggressive free-chain in v1).
- Full UDATA directory (no free slot) fails clearly; no automatic directory-chain growth in v1.
- This tree is environment-specific; packaging for third-party machines is out of scope here.

---

## Acknowledgments

- [xemu](https://xemu.app/) — original Xbox emulator  
- Xbox homebrew / FATX documentation community  
- Games used as fixtures across the year (among others): Mercenaries, Halo 2, NFS Underground 2, ToeJam & Earl III, Black  

---

*Built over ~one year of iterative forensics. Every guest byte has to land in the right host cluster — and on the right FATX chain.*
