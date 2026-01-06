# 🎉 AI Reference - Session 7 (v5.2 - COMPLETATA!)

**Data:** 6 Gennaio 2026, 08:13 - 10:27  
**Obiettivo:** Fix restore per gioco "Black" + Rilevamento automatico tipo HDD  
**RISULTATO:** ✅ **FUNZIONA! Tutti i giochi testati OK**

---

## 🏆 Risultati della Sessione

### Giochi Testati con Successo
| Gioco | Title ID | Restore | Note |
|-------|----------|---------|------|
| **Black** | 45410083 | ✅ | Restore 3% → 1% funzionante |
| **Mercenaries** | 4c410015 | ✅ | Restore funzionante |
| **Altri giochi** | vari | ✅ | Tutti i save non corrotti |

---

## 🔧 Fix Implementati (v5.2)

### 1. Rilevamento Automatico Tipo HDD

Prima lo script usava offset FISSI che funzionavano solo per un tipo di HDD.
Ora rileva automaticamente:

```python
def detect_hdd_type(data: bytes) -> str:
    """
    Rileva tipo HDD basandosi su signature FATX
    """
    # HDD piccoli: FATX @ 0x001A0000
    # HDD 8GB: FATX @ 0x00160000
    
    if data[0x001A0000:0x001A0004] == b'FATX':
        # HDD piccolo (nuovo xemu)
        FAT_TABLE_OFFSET = 0x001A1000
        DATA_START = 0x001B3000
        CLUSTER_INDEX_BASE = 1  # 1-indexed
        return 'small'
    elif data[0x00160000:0x00160004] == b'FATX':
        # HDD 8GB originale
        FAT_TABLE_OFFSET = 0x00161000
        DATA_START = 0x00443000
        CLUSTER_INDEX_BASE = 2  # 2-indexed
        return '8gb'
```

**Output:**
```
Tipo HDD rilevato: 8gb (FAT @ 0x00161000, DATA @ 0x00443000)
```

### 2. Fix Cluster Non Linkati (Black)

**Problema:** Il gioco "Black" ha una struttura particolare:
- Save slot `1AAF1A0557C1` punta a cluster 9
- Cluster 9 è **COMPLETAMENTE VUOTO**
- Le vere entries `SaveMeta.xbx` e `Profilo` sono in cluster 17
- I dati del save sono in cluster 18-19
- **Nessun collegamento FAT tra cluster 9 e 17!**

**Soluzione:** Ricerca brute-force limitata (range 10-50) quando il cluster del save slot è vuoto:

```python
if not inner_entries:
    print(f"[!] Cluster {ss['first_cluster']} vuoto, ricerca brute-force...")
    for search_cluster in range(10, 51):
        chunk = data[cluster_to_offset(search_cluster):...]
        if b"SaveMeta.xbx" in chunk:
            found_entries = scan_directory(data, search_cluster)
            if found_entries:
                print(f"[✓] Trovate {len(found_entries)} entries in cluster {search_cluster}!")
```

### 3. Estensione Automatica Range Allocati

**Problema:** Anche trovando cluster 17, mancavano cluster 18-19 con i dati reali.

**Soluzione:** Scansiona la FAT per trovare tutti i cluster allocati (FAT ≠ 0x0000) nel range:

```python
# Trova primo cluster FREE
for c in range(max_cluster + 1, max_cluster + 100):
    if read_fat16_entry(data, c) == 0x0000:
        first_free = c
        break

# Includi tutti i cluster allocati fino a first_free
for c in range(min_cluster, first_free):
    if read_fat16_entry(data, c) != 0x0000:
        result['all_clusters'].add(c)
```

**Risultato per Black:**
```
Prima:  Cluster 5-9 (5 cluster)
Dopo:   Cluster 5-23 (19 cluster, include 17-19 con i dati!)
```

### 4. Disabilitato Azzeramento Cluster Extra

**Problema:** Lo script azzerava cluster "extra" trovati sul target (>7000 cluster = 116MB!)
Questo poteva corrompere dati di altri giochi.

**Soluzione:** Disabilitato di default:

```python
ENABLE_CLUSTER_ZEROING = False  # ⚠️ PERICOLOSO - lasciare a False!

if target_extra_clusters and ENABLE_CLUSTER_ZEROING:
    # Azzera cluster...
elif target_extra_clusters:
    print(f"[SKIP] Azzeramento cluster extra DISABILITATO (sicurezza)")
```

---

## 📊 Struttura Scoperta: Black (45410083)

```
Cluster 1: ROOT (TDATA→2, UDATA→4)
Cluster 2: TDATA/45410083 → cluster 3
Cluster 4: UDATA/45410083 → cluster 5
Cluster 5: Game folder entries
  ├── TitleMeta.xbx → cluster 6
  ├── TitleImage.xbx → cluster 7
  ├── SaveImage.xbx → cluster 8
  └── 1AAF1A0557C1 → cluster 9 (VUOTO!)

Cluster 9: VUOTO (tutti 0x00)! ❌

Cluster 17: Save slot entries (non linkato!)
  ├── SaveMeta.xbx → cluster 10
  └── Profilo → cluster 11

Cluster 18: SaveMeta content
Cluster 19: Profile DATA (dove sono le differenze 1% vs 3%)

FAT: Cluster 1-23 = 0xFFFF (allocati), Cluster 24+ = 0x0000 (free)
```

**Differenze B1 (1%) vs B2 (3%):**
- Solo 64 bytes diversi!
- Cluster 5: 2 bytes (timestamp TitleMeta)
- Cluster 17: 2 bytes (timestamp SaveMeta)
- Cluster 19: 59 bytes (**dati del save!**)

---

## 📁 File Modificati

| File | Cambiamento |
|------|-------------|
| `single_game_merger.py` | v5.2 con tutti i fix |
| `analyze_black_diff.py` | Script per analizzare differenze Black |
| `diff_complete.py` | Fix per mostrare differenze pre-data |

---

## 💡 Idea per Halo 2 (Prossima Sessione)

Halo 2 è un caso speciale che richiede ~270MB per il restore (include cache).

**Possibile soluzione:**
1. Riconoscere Title ID `4d530064` (Halo 2)
2. Per quel gioco specifico, includere TUTTI i cluster usati (anche cache)
3. Salvare backup più grande ma funzionante

```python
if game_id == "4d530064":  # Halo 2
    # Strategia speciale: includi tutta la cache
    # ~700MB backup ma funzionante al 100%
```

---

## 🎯 Riepilogo Comandi Utili

```bash
# Avvia script principale
python single_game_merger.py

# Analizza differenze tra due HDD
python diff_complete.py

# Analizza differenze specifiche Black
python analyze_black_diff.py
```

---

## ⚠️ Note Importanti

1. **Non riattivare ENABLE_CLUSTER_ZEROING** senza una buona ragione
2. **Halo 2 non funziona ancora** con restore standard (serve strategia speciale)
3. **Testare sempre** dopo ogni restore prima di giocare troppo

---

*Sessione completata: 6 Gennaio 2026, 10:27*
*Prossima sessione: Implementare strategia speciale per Halo 2*
