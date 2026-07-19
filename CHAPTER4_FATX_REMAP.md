# Capitolo 4 — Remap FATX (fase 6.1)

**Questo file non è un `AI_REFERENCE_SESSION*`. Non mescolarlo con le sessioni v5.**

Continua da [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md) (allocate QCOW2)
e [CHAPTER2_GUEST_AWARE_LAB.md](CHAPTER2_GUEST_AWARE_LAB.md) (overwrite-only).

| Campo | Valore |
|--------|--------|
| Data resoconto | 19 luglio 2026 |
| Scope | Restore universale su HDD multi-game (cluster FATX già usati) |
| Formato backup | **XBSV v7** invariato (un solo metodo) |
| Codice | `xemu_lab/remap.py` + API free-cluster in `fatx.py` + auto-path in `restore.py` |
| QEMU / qemu-img | Esclusi |
| Entry | `START_XEMU_TEST.bat` → restore |

---

## 1. Perché un capitolo nuovo

Con 6.0 il restore su **vergine/sparse** funziona (allocate QCOW2 + envelope).
Restava il buco storico: su HDD **già popolato** i numeri cluster FATX del
backup (es. Black da B1: 5–11) sono spesso occupati da altri Title ID.
Overwrite same-guest = corruzione.

La 6.1 è la **riallocazione logica FATX**: stessi dati del backup, nuovi cluster
liberi sul target, dirent/FAT riscritti. È il pezzo che rende il tool usabile
come motore di savestate chirurgico “davvero universale”, non solo su layout
fortunati.

---

## 2. Comportamento (un backup, due path di restore)

Il backup resta XBSV v7. Decide solo il restore:

| Condizione | Path | Cosa fa |
|------------|------|---------|
| Cluster del backup liberi, o già del Title ID sul live | **same-guest** | Come cap. 2/3 (chirurgia ± envelope QCOW2) |
| Cluster occupati da altri / Title assente con collisione | **remap** | Alloca cluster liberi, patch `first_cluster`, FAT nuove, dati ai nuovi guest offset; QCOW2 allocate/RMW sui nuovi offset |

Preflight: se servono più cluster liberi di quanti ce ne sono → errore, zero scritture.

Menu: elenca i giochi UDATA sul live; se il Title del backup non c’è, chiede conferma esplicita prima di procedere (remap automatico se serve).

---

## 3. Architettura breve

```
XBSV v7  →  decide_restore_path(live FATX)
              ├─ same-guest → pending chirurgici (+ envelope se allocate)
              └─ remap      → build_remap_plan → pending nuovi offset
                                              → apply via QCOW2WritableBlockDevice
```

Moduli:

- [`xemu_lab/fatx.py`](xemu_lab/fatx.py) — `find_free_clusters`, `find_directory_slot`, `collect_title_clusters`, helper FAT
- [`xemu_lab/remap.py`](xemu_lab/remap.py) — decisione + piano `old→new`
- [`xemu_lab/restore.py`](xemu_lab/restore.py) — auto-scelta path, report `mode` / `clusters_remapped`

---

## 4. Collaudo umano PASS (19 luglio 2026)

Procedura:

1. Copia golden **HDD5** → `xbox_hdd.qcow2` (Merc + ToeJam + Halo 2 + NFS)
2. Restore **`Black (18-07-26 11-30) v7`** (Title assente sul live)
3. Lab: `mode=remap`, `remapped=7`, `verified=True`, `envelopes=0`

| Titolo | Dopo remap | In xemu |
|--------|------------|---------|
| Black (nuovo) | presente | save 1% OK |
| Halo 2 | intatto | profilo + save OK |
| ToeJam & Earl III | intatto | carica OK |
| Mercenaries | intatto | OK |
| NFS Underground 2 | intatto | OK |

Interpretazione: non è un dump 1:1 dell’HDD sorgente Black; è un **innesto chirurgico** del solo Title ID su un disco multi-game già valido. Gli altri save non sono stati toccati a livello di gameplay.

---

## 5. Cosa dimostra / limiti rimasti

**Dimostra**

- Remap FATX QEMU-free su HDD retail-like multi-game.
- Coesistenza same-guest (regressione ToeJam/Merc già vista) + remap (Black su HDD5).
- Un solo formato backup (v7) per vergine e multi-game.

**Limiti noti (non bloccanti per savestate base)**

- Remap UDATA-centric (come il backup di default); TDATA “ricco” non è il focus.
- Sostituendo un Title già presente in remap, i vecchi cluster possono restare orfani (niente free-chain aggressivo in v1).
- Directory UDATA piena (nessuno slot) → errore chiaro, niente estensione automatica catena dir in v1.
- `verified=True` + list_games non sostituiscono il verdetto in xemu — qui il verdetto c’è.

---

## 6. Posizione nel progetto (dopo ~1 anno)

| Era | Modello | Limite |
|-----|---------|--------|
| v5 / merger | seek host ≈ guest | layout fortunati |
| Cap. 2 | guest-aware overwrite | solo cluster QCOW2 già allocati |
| Cap. 3 / 6.0 | allocate QCOW2 + envelope | non rimappa FATX |
| **Cap. 4 / 6.1** | **remap FATX + allocate** | **path universale per restore chirurgico** |

Prossimo passo naturale (prodotto): integrare questo motore in savestate / UI, non reinventare il block device.

---

## 7. File di questo capitolo

```
xemu_lab/remap.py
xemu_lab/fatx.py      # + free cluster / slot / title clusters
xemu_lab/restore.py   # auto same-guest | remap
tests/test_qcow2_fatx.py   # FatxAllocAndRemapTests
CHAPTER4_FATX_REMAP.md     # questo resoconto
```
