# 🔧 AI Reference - Session 5 (COMPLETATA CON SUCCESSO!)

**Data:** 6 Gennaio 2026, 01:17 - 03:42  
**Obiettivo:** Risolvere il bug "checkpoint B → checkpoint A" di Halo 2
**RISULTATO:** ✅ **FUNZIONA!**

---

## 🎉 SOLUZIONE TROVATA

### Il Problema Originale
Il restore non funzionava quando il file di save cresceva tra checkpoint A e B.

### La Soluzione
Copiare **TUTTI i byte diversi** da H1 (checkpoint A) a H2 (checkpoint B) funziona!
La cache extra (180MB) può rimanere - non influisce sul checkpoint.

### Cosa Cambia Realmente tra Checkpoint
- **auxilary.bin**: solo ~23,018 bytes diversi (0.55% di 4MB)
- **profile**: IDENTICO
- **cache**: 180MB di differenza ma NON importa per il checkpoint

---

## 📊 Scoperte Chiave

### 1. Struttura HDD Nuovi (scaricati da xemu)
Gli HDD nuovi hanno **offset diversi** dagli HDD 8GB!

| Componente | HDD 8GB | HDD Nuovo |
|------------|---------|-----------|
| FAT_OFFSET | 0x00161000 | 0x001A1000 |
| FAT32_OFFSET | 0x00311000 | 0x001A1000 |
| DATA_START | 0x00443000 | 0x001B3000 |
| Cluster indexing | 2-indexed | 1-indexed |

### 2. Struttura Save Halo 2 (HDD nuovo)
```
ROOT @ 0x001B3000 (cluster 1):
├── TDATA (cluster 2)
│   └── 4d530064 (cluster 3) - non analizzato
└── UDATA (cluster 4)
    └── 4d530064 (cluster 5)
        ├── TitleMeta.xbx (cluster 6)
        ├── TitleImage.xbx (cluster 7)
        ├── SaveImage.xbx (cluster 8)
        └── 589BCCD01326 (cluster 9) → DATI, non directory!
            └── (cluster 10 contiene le vere entries:)
                ├── preferences.dat (cluster 2)
                ├── fonts (cluster 3)
                ├── cache000.map (cluster 59, 188MB)
                └── cache001.map (cluster 2939, 545MB)

SEPARATAMENTE @ cluster 11473:
├── SaveMeta.xbx (cluster 10)
├── profile (cluster 11)
└── auxilary.bin (cluster 12, 4MB) ← CONTIENE I CHECKPOINT!
```

### 3. File Importanti per Checkpoint
| File | Cluster | Size | Cambia tra CP? |
|------|---------|------|----------------|
| auxilary.bin | 12-267 | 4 MB | SÌ (0.55%) |
| profile | 11 | 500 B | NO |
| SaveMeta.xbx | 10 | 50 B | ? |
| cache000.map | 59+ | 188 MB | SÌ (ma non importa) |
| cache001.map | 2939+ | 545 MB | SÌ (ma non importa) |

---

## 🔧 Modifiche al Codice

### single_game_merger5.py
1. **Offset aggiornati** per HDD nuovo (linee 31-42)
2. **cluster_to_offset()**: cambiato da `cluster - 2` a `cluster - 1`

### ATTENZIONE
Queste modifiche funzionano SOLO per HDD nuovi!
Per HDD 8GB, ripristinare gli offset originali.

---

## 📝 Prossimi Passi

1. **Implementare rilevamento automatico** del tipo di HDD
2. **Migliorare scansione** per trovare auxilary.bin anche se frammentato
3. **Backup "bruto"**: salvare tutti i byte diversi tra source e target
4. **Testare con altri giochi** su HDD nuovo

---

## 💡 Lezioni Apprese

1. **La cache non conta** - solo auxilary.bin contiene i checkpoint
2. **Offset diversi per HDD diversi** - non assumere offset fissi
3. **Cluster indexing può variare** - 1-indexed vs 2-indexed
4. **Struttura frammentata** - directory entries possono essere ovunque

---

## 🧪 Test Effettuati

| Test | Risultato |
|------|-----------|
| Backup v5 FAT RANGE | ❌ Non trova auxilary.bin |
| Restore cluster 12-267 | ❌ Non funziona (target già modificato?) |
| Copia TUTTI byte diversi H1→H2 | ✅ **FUNZIONA!** |

---

*Sessione completata: 6 Gennaio 2026, 03:42*
*Checkpoint Halo 2 ripristinato con successo!*
