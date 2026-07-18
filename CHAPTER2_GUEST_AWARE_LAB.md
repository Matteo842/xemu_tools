# Capitolo 2 — Laboratorio guest-aware QCOW2/FATX (QEMU-free)

**Questo file non è un `AI_REFERENCE_SESSION*`. Non mescolarlo con le sessioni v5.**

Quei documenti descrivono l’era `single_game_merger.py` (seek host ≈ guest).  
Questo documento apre il capitolo successivo: mapping L1/L2 reale, backup XBSV v6, restore overwrite-only in Python, **senza QEMU**.

| Campo | Valore |
|--------|--------|
| Data resoconto | 18 luglio 2026 |
| Entry point | `START_XEMU_TEST.bat` → `xemu_test_lab.py` |
| Codice nuovo | `xemu_lab/` |
| Oracle legacy (non usare in write) | `single_game_merger.py` |
| QEMU / qemu-img | Esclusi di proposito |

---

## 1. Perché un capitolo nuovo

Per mesi il restore “funzionava” spesso perché gli offset guest venivano usati come offset del file `.qcow2`. Su layout fortunati combaciava; non era un block device corretto.

Vincoli di progetto (da non dimenticare):

- Compatibilità Linux → niente dipendenza da `qemu.exe` Windows.
- `qemu-img convert` aveva ricostruito HDD con dimensioni sbagliate.
- Build dei tool QEMU modificati di xemu da sorgente (Ubuntu) fallita / incompleta.
- Scrittura ammessa solo in Python sul mapping guest→host già validato.

---

## 2. Cosa è stato costruito

### Lettura (gate read-only)

- `xemu_lab/qcow2.py` — `QCOW2BlockDevice` read-only, L1/L2, zero/unallocated, rifiuto backing/cifratura/feature incompatibili.
- `xemu_lab/fatx.py` — partizioni Xbox fisse, FATX, catene, `E:\UDATA` / `E:\TDATA`.
- `xemu_lab/compare.py` — diff guest-aware per regione/cluster.
- `xemu_lab/catalog.py` — registro `hdd_backups.json`, file non catalogati senza significato inventato.

### Scrittura (fase successiva al gate)

- `QCOW2WritableBlockDevice.write_at` — **solo overwrite** di cluster QCOW2 già allocati, non zero, non compressi. Niente allocate-on-write, niente update L2/refcount.
- `xemu_lab/backup.py` — formato **XBSV v6/v7** (offset solo guest; v7 + envelope cluster QCOW2) + JSON; nomi file leggibili.
- `xemu_lab/restore.py` — apply dir → FAT → data (v7: envelope se allocate), fsync, read-back + check Title ID FATX.
- `xemu_lab/safety.py` — xemu chiuso, divieto scrittura in `D:\xemu\bk`, copia atomica + hash, rollback = ricopia golden.
- `xemu_lab/titles.py` — mappa nomi da `GAME_NAMES` del merger + scan UDATA guest-aware.

`single_game_merger.py` **non è stato modificato** e **non è il motore di write**.

---

## 3. Gate forensi (prima delle scritture)

| Check | Esito | Note |
|--------|--------|------|
| B1/B2 mapping + delta 64 byte | PASS | CONFIG 1; E cluster 5/9/11 → 2/2/59 |
| H1/H2 delta guest-aware | PASS | Totale 428 287 103; Y 427 278 322; E 1 008 759; altro 22 |
| B1/B2 in gioco | OK | Non corrotti; restano fixture, non golden di restore “fidati” in assoluto |

---

## 4. Collaudi restore in xemu (18 luglio 2026)

Convenzione: backup da golden in `D:\xemu\bk` (sempre `rb`); restore solo su `D:\xemu\xbox_hdd.qcow2` (live).

### Prove base / chirurgia

| # | Test | Esito |
|---|------|--------|
| 1 | Ciclo HDD1 Mercenaries (copia + delete + restore) | PASS in gioco |
| 2 | Backup/restore ToeJam da HDD2 | PASS |
| 3 | Delete Mercenaries, restore solo ToeJam | PASS — Mercenaries resta assente (non è dump 1:1 HDD) |
| 4 | Backup Mercenaries da HDD1 → restore su live basato su HDD5 (Merc cancellato, altri giochi presenti) | PASS — Merc ok; Halo / ToeJam / NFS intatti |
| 5 | Backup Halo H1 → restore su live H2 | PASS — stesso checkpoint di H1 |
| 6 | Black B1 → live B2 | PASS — 1% |
| 7 | Black B2 → live B1 | PASS — 3% |

### Limite colpito, poi superato (allocate / cap. 3)

| # | Test | Esito | Dettaglio |
|---|------|--------|-----------|
| 8a | Restore Black su HDD vergine, overwrite-only | **FAIL controllato** | cluster QCOW2 compresso/unalloc |
| 8b | Stesso scenario, backup **XBSV v7** + allocate | **PASS in gioco** (18/07/2026) | `Black (18-07-26 11-30) v7`; envelopes=4; save 1% leggibile |

Dettaglio size (osservazione utente, collaudo 8b): subito dopo il lab il live era ~1800 KB (meno di B1=2048 KB); dopo aver avviato xemu e verificato il save, il file live è tornato **2048 KB**. Il lab aveva allocato i 4 envelope necessari al save; xemu, leggendo/scrivendo il disco, ha portato il contenitore host alla stessa footprint di B1. I save erano già corretti prima di quella crescita.

Resoconto tecnico allocate / v7: [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md).

---

## 5. Cosa dimostra / cosa non dimostra

**Dimostra**

- Il restore non è una copia cieca golden→live: altri Title ID restano quelli del live.
- Cross-golden funziona quando i cluster QCOW2 necessari sono già allocati (e non compressi) sul target.
- Halo (centinaia di cluster) e Black checkpoint passano sullo stesso motore di Mercenaries/ToeJam.
- Con XBSV v7 + allocate: restore Black su HDD vergine/sparse **funziona in gioco** (non solo read-back lab).

**Non dimostra**

- Che la size host post-lab sia già identica al golden (può crescere al primo boot xemu).
- Remap FATX se i cluster del backup sono già occupati da altri Title ID (fase **6.1**).
- Che `verified=True` da solo basti senza conferma in xemu — sul vergine v7 c’è conferma gameplay.

---

## 6. Prossimi stress / fase successiva

Documentazione allocate: [CHAPTER3_QCOW2_ALLOCATE.md](CHAPTER3_QCOW2_ALLOCATE.md). Remap FATX = **6.1**.

Stress candidato (non ancora fatto): HDD multi-game + restore di un Title ID
**assente** sul target (same-guest / senza remap). Se i cluster FATX del backup
sono liberi può funzionare; se sono già usati da altri giochi → collisione
(serve 6.1).

---

## 7. File e cartelle di questo capitolo

```
xemu_test_lab.py
START_XEMU_TEST.bat
xemu_lab/
  qcow2.py      # read + writable + allocate opt-in
  fatx.py
  compare.py
  catalog.py
  backup.py     # XBSV v6/v7
  restore.py
  safety.py
  titles.py
tests/test_qcow2_fatx.py
surgical_backups_v6/   # output backup (gitignore)
CHAPTER2_GUEST_AWARE_LAB.md   # questo resoconto
CHAPTER3_QCOW2_ALLOCATE.md    # fase 6.0 allocate-on-write
```

Non usare come specifica operativa: `AI_REFERENCE_SESSION1.md` … `SESSION8.md` (era v5 / offset fisici).

---

## 8. Regole operative rimaste valide

1. Golden in `D:\xemu\bk` → solo lettura.
2. Write solo sull’HDD attivo configurato.
3. xemu chiuso prima di copia/restore.
4. B1/B2 = fixture forensi utili; primo collaudo “prodotto” era HDD1, poi stress multi-game / Halo / Black.
5. Nessun qemu-img nel percorso supportato.
