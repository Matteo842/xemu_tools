# Chapter 3 — QCOW2 allocate-on-write (phase 6.0)

Continues from [CHAPTER2_GUEST_AWARE_LAB.md](CHAPTER2_GUEST_AWARE_LAB.md).

This chapter covers restoring a surgical save onto **virgin or sparse** QCOW2
disks — including cases where the game was never launched on the target HDD.

It is **not** part of the older `AI_REFERENCE_SESSION*` notes (legacy v5 /
physical-offset era).

| Field | Value |
|--------|--------|
| Date | 18 July 2026 |
| v1 scope | Allocate QCOW2 clusters at the **same** guest offsets as the backup |
| Backup format | **XBSV v7** (full QCOW2 cluster envelopes) + still readable as v6 |
| Out of scope at the time | FATX remap → see [CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md) |
| QEMU / qemu-img | Excluded |
| Lab entry | `START_XEMU_TEST.bat` → restore → confirm allocate |

> Paths such as `D:\xemu\…` are lab-specific. For end-user use, see
> [SaveState](https://github.com/Matteo842/SaveState).

---

## 1. The problem

Overwrite-only restore fails when the needed QCOW2 clusters are compressed or
unallocated.

An early allocate attempt (writing only the surgical XBSV v6 bytes into freshly
zeroed 64 KiB QCOW2 clusters) could destroy FAT / root / UDATA that shared the
same guest cluster. The lab reported `verified=True`, but saves were missing
in-game.

---

## 2. The fix (v7 + envelopes)

There is a single backup method: **v7**. Envelopes are **extra data** consumed
by restore only where allocate is required.

1. **XBSV v7 backup:** surgical segments (same as v6) **plus** full QCOW2 cluster
   envelopes
2. **Restore without allocate:** surgical segments only → **v6 parity**
3. **Restore with allocate:** envelopes **only** on clusters that are not
   overwrite-safe; elsewhere surgical writes only (= v6). Then FATX verify
4. **v6 backup without envelopes:** allocate onto unalloc/zero with only partial
   cluster coverage → **rejected**

---

## 3. Human PASS (18 July 2026)

| Step | Result |
|------|--------|
| Restore `Black (18-07-26 11-30) v7` onto virgin live, allocate=yes | Lab PASS: verified, envelopes=4, qcow2_new=4, host_grown=262144 |
| File size right after lab | ~1800 KB (< B1 at 2048 KB) |
| Boot xemu + 1% save | **OK in-game** |
| File size after xemu | **2048 KB** (= B1) |

**How to read the size change:** B1 is “virgin + first Black checkpoint”, host
footprint 2048 KB. The lab allocates only the four envelopes needed for the
save. Other host clusters that B1 had already touched can remain unmaterialised
until xemu reads or writes them. On boot, xemu completes host allocation → same
size as B1, while the saves were already valid (xemu is **not** inventing the
checkpoint; it is reading it from the restore).

---

## 4. Next phase (6.1)

FATX remap on multi-game disks is documented in
[CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md) (HDD5 + Black v7 PASS in-game
for every Title ID checked).

---

## 5. Safety

- Goldens under the lab backup tree → never opened for write
- Allocate is not crash-atomic mid-write → always run on a copy / live disk
- Crash halfway → treat the image as dirty; restore from golden

---

## 6. Automated tests

Covered in the suite (among others):

- Allocate for unallocated / zero / compressed / missing L2
- v6 partial allocate onto unalloc → reject
- v7 serialize + restore with envelopes
- Forensic B1/B2 fixtures remain unchanged by the gate
