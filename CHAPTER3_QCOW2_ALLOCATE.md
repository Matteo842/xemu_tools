# Capitolo 3 — Allocate-on-write QCOW2 (fase 6.0)

**Questo file non è un `AI_REFERENCE_SESSION*`. Non mescolarlo con le sessioni v5.**

Continua da [CHAPTER2_GUEST_AWARE_LAB.md](CHAPTER2_GUEST_AWARE_LAB.md).

| Campo | Valore |
|--------|--------|
| Data | 18 luglio 2026 |
| Scope v1 | Allocate QCOW2 agli **stessi** guest offset del backup |
| Formato backup | **XBSV v7** (envelope cluster QCOW2 interi) + lettura v6 |
| Fuori scope all’epoca | Remap FATX → vedi [CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md) |
| QEMU / qemu-img | Esclusi |
| Entry | `START_XEMU_TEST.bat` → restore → conferma allocate |

---

## 1. Problema iniziale

Overwrite-only falliva su cluster compressi/unalloc. Il primo allocate (solo
byte chirurgici XBSV v6 su cluster QCOW2 da 64 KiB azzerati) poteva distruggere
FAT/root/UDATA nello stesso cluster guest → lab `verified=True` ma save assenti
in gioco.

---

## 2. Fix (v7 + envelope)

Un solo metodo di backup (v7). Gli envelope sono **dati in più** usati dal
restore solo dove serve.

1. Backup XBSV **v7**: segmenti chirurgici (= v6) + envelope cluster QCOW2.
2. Restore **senza** allocate: solo segmenti chirurgici → **parity v6**.
3. Restore **con** allocate: envelope **solo** sui cluster che non sono
   overwrite-safe; sugli altri di nuovo solo chirurgia (= v6). Poi verify FATX.
4. Backup v6 senza envelope: allocate su unalloc/zero a copertura parziale → rifiuto.

---

## 3. Collaudo umano PASS (18 luglio 2026)

| Step | Esito |
|------|--------|
| Restore `Black (18-07-26 11-30) v7` su live vergine, allocate=sì | Lab PASS: verified, envelopes=4, qcow2_new=4, host_grown=262144 |
| Size file subito dopo lab | ~1800 KB (< B1 2048 KB) |
| Boot xemu + save 1% | **OK in gioco** |
| Size file dopo xemu | **2048 KB** (= B1) |

Interpretazione size: B1 = vergine + primo CP Black, footprint host 2048 KB.
Il lab alloca in modo mirato i 4 envelope del save; altri cluster host che B1
aveva già “toccato” possono restare non materializzati finché xemu non li legge
o scrive. Al boot xemu completa l’allocazione host → stessa size di B1, con i
save già validi (non è xemu che “inventa” il checkpoint: lo legge dal restore).

---

## 4. Fase successiva (6.1)

Il remap FATX su multi-game è documentato in
[CHAPTER4_FATX_REMAP.md](CHAPTER4_FATX_REMAP.md) (collaudo HDD5 + Black v7 PASS
in gioco su tutti i Title ID).

---

## 5. Sicurezza

- Golden in `D:\xemu\bk` → mai in scrittura
- Allocate non è rollback atomico → sempre su copia/live
- Crash a metà → dirty bit; ripristinare da golden

---

## 6. Test automatici

- Allocate unalloc / zero / compresso / L2 mancante
- v6 allocate parziale su unalloc → reject
- v7 serialize + restore con envelope
- Forensi B1/B2 invariati
