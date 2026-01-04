# 🔧 AI Reference - Session 2 (Dynamic Backup Debugging)

**⚠️ QUESTO FILE È UN CONTINUO DI `AI_REFERENCE.md` - LEGGI PRIMA QUELLO!**

**Data sessione:** 3-4 Gennaio 2026 (fino alle 4 AM)
**Obiettivo:** Implementare backup/restore DINAMICO (senza hardcodare metadata_areas)

---

## 🎯 Obiettivo Raggiunto Parzialmente

### ✅ Funziona:
- **Mercenaries (4c410015)**: Backup dinamico V4 funziona perfettamente

### ❌ Non Funziona Ancora:
- **Halo 2 (4d530064)**: Profilo visibile ma dati corrotti
- **ToeJam & Earl III (5345000f)**: Same problem (non testato a fondo)

---

## 🔄 Cosa Abbiamo Implementato (V4 Dynamic)

### Nuovo file sorgente: `xbox_hdd3.qcow2`
Contiene 3 giochi:
- Mercenaries (4c410015) → cluster 5
- ToeJam (5345000f) → cluster 40  
- **Halo 2 (4d530064) → cluster 54** ← nuovo gioco test

### Algoritmo Dinamico V4 in `single_game_merger.py`:

1. **Trova gioco in UDATA** cercando l'ID (8 char hex)
2. **Segue la FAT chain** del game folder
3. **Rileva tipo struttura**:
   - Se primo byte è 1-42 → struttura standard con directory entries
   - Altrimenti → dati diretti (NO subdirectory)
4. **Cerca save slot separati** in due modi:
   - Cercando `SaveMeta.xbx` che punta a cluster nella chain del gioco
   - Cercando directory con nomi hex (es. `589BCCD01326`) che puntano alla chain
5. **Estrae tutte le FAT16, FAT32 entries e data chunks**

---

## 🔍 Scoperte Chiave della Sessione

### Struttura Diversa tra Giochi

| Gioco | Tipo Struttura | Save Slot |
|-------|---------------|-----------|
| Mercenaries | Directory entries standard | Dentro UDATA (cluster 9) |
| ToeJam | Dati diretti | Cluster separato 17710 |
| Halo 2 | Dati diretti | **DUE** save slot: 27127 e 20539 |

### Il Problema di Halo 2

Dopo il restore dinamico, ci sono ancora **3,003 bytes** diversi tra source e target:

| Area | Cluster | Bytes | Contenuto |
|------|---------|-------|-----------|
| 0x00050000 | pre-data | 1 | Header counter |
| 0x001f0000 | FAT | 67 | FAT metadata |
| 0x00200000 | FAT | 6 | FAT metadata |
| **0x00310000** | **147+** | **233** | **FAT32 entries!** |
| 0x05410000 | 5111 | 1,470 | Dati (Mercenaries?) |
| 0x0a410000 | 10231 | 6 | Dati (altro gioco?) |
| 0x1af60000 | 27339 | 1,220 | "daeh" header |

### 🔑 Il Problema Reale

I cluster **5111, 10231, 27339** NON sono nella chain di Halo 2!
- Cluster 5111 → chain di 501 cluster, puntato da 5110 (probabilmente Mercenaries)
- Cluster 10231 → chain di 143 cluster
- Cluster 27339 → standalone, non puntato da nessuno

**Quando elimini un save in xemu, vengono modificate anche aree di ALTRI giochi!**

Questo causa il problema: il nostro backup ripristina solo Halo 2, ma non le aree "collaterali" toccate dall'eliminazione.

---

## 📂 Save Slot di Halo 2 - Analisi Dettagliata

### Save Slot 1 (cluster 27127):
```
'SaveMeta.xbx' → cluster 59, 50 bytes
'profile' → cluster 60, 500 bytes  
'auxilary.bin' → cluster 61, 4,186,132 bytes (4 MB)
```

### Save Slot 2 (cluster 20539):
```
'TitleMeta.xbx' → cluster 55
'TitleImage.xbx' → cluster 56
'SaveImage.xbx' → cluster 57
'589BCCD01326' → cluster 58 (directory profilo)
```

### Halo 2 Game Folder Chain:
- Cluster 54-146 (93 clusters)
- I file del save slot usano cluster DENTRO questa chain

---

## 🧪 Test Effettuati

| Test | Risultato |
|------|-----------|
| Backup Mercenaries → Restore | ✅ Funziona |
| Backup Halo 2 → Restore | ❌ Profilo visibile ma dati corrotti |
| `restore_all_diffs.py` (copia tutte le differenze) | ✅ Funziona |

Questo conferma che se copiamo TUTTE le differenze (3,003 bytes), Halo 2 funziona.
Ma non è una soluzione pratica perché richiede il file sorgente completo.

---

## 📝 Script Utili Creati

| Script | Scopo |
|--------|-------|
| `diff_complete.py` | Diff byte-per-byte tra source e target |
| `find_save_slots.py` | Trova tutti i SaveMeta.xbx nell'HDD |
| `check_missing.py` | Analizza i cluster che mancano nel backup |
| `restore_all_diffs.py` | Copia TUTTE le differenze (per debug) |

---

## ⚠️ Problema Irrisolto

**Come trovare DINAMICAMENTE i cluster "collaterali" (5111, 10231, 27339)?**

Questi cluster:
- NON sono nelle FAT chain di Halo 2
- Vengono modificati quando elimini il save
- Appartengono probabilmente ad altri giochi

Possibili soluzioni da esplorare:
1. Salvare anche i cluster "vicini" ai save slot
2. Fare backup di TUTTO UDATA insieme
3. Investigare COME xemu modifica il filesystem quando elimina un save
4. Trovare un pattern per identificare quali cluster appartengono a quale gioco

---

## 🗂️ File Aggiornati

| File | Cambiamento |
|------|-------------|
| `single_game_merger.py` | Linee ~240-370: nuova logica per trovare save slot |
| `HDD_SOURCE` | Ora usa `xbox_hdd3.qcow2` |
| `GAME_NAMES` | Aggiunto `"4d530064": "Halo 2"` |

---

## 🔧 Costanti Filesystem (reminder)

```python
DATA_START = 0x00443000
CLUSTER_SIZE = 16384  # 16KB
FAT_TABLE_OFFSET = 0x00161000  # FAT16
FAT32_TABLE_OFFSET = 0x00311000  # FAT32
```

---

## 🎯 Prossimi Passi Suggeriti

1. **Investigare xemu**: capire esattamente cosa fa quando elimina un save
2. **Approccio alternativo**: invece di "delete + restore", fare solo "overwrite"
3. **Backup più ampio**: includere aree FAT complete invece di singole entries
4. **Fallback**: accettare che alcuni giochi richiedono approccio diverso

---

*Sessione terminata: 4 Gennaio 2026, 04:00*
*Ultimo test funzionante: Mercenaries con backup dinamico V4*
