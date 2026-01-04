# 🎮 AI Reference - Xbox Save Surgical Restore

**Documento di riferimento per AI e sviluppatori futuri**

**Status Progetto:** ✅ PRODUCTION READY (v5.1)  
**Ultimo aggiornamento:** 4 Gennaio 2026

---

## 📋 Quick Reference

### File Principale
```
single_game_merger.py  →  Script principale backup/restore
```

### Costanti Critiche
```python
FAT16_OFFSET = 0x00161000      # Tabella FAT primaria
FAT32_OFFSET = 0x00311000      # Tabella FAT secondaria
DATA_START = 0x00443000        # Inizio dati cluster
CLUSTER_SIZE = 16384           # 16KB per cluster
ENTRY_SIZE = 64                # Dimensione directory entry
```

### Formule
```python
cluster_to_offset = lambda c: DATA_START + ((c - 2) * CLUSTER_SIZE)
read_fat16 = lambda data, c: struct.unpack('<H', data[FAT16_OFFSET + c*2:][:2])[0]
```

---

## 🎯 Cosa Funziona

| Versione | Giochi Supportati | Note |
|----------|-------------------|------|
| v5/v5.1 | Mercenaries, Halo 2, NFS Underground 2 | Approccio dinamico |
| Custom | ToeJam & Earl III | Richiede hardcoding |

---

## ⚠️ Cosa NON Fare

1. **NON modificare FAT_TABLE_OFFSET** senza ricalcolare tutto
2. **NON saltare il backup FAT32** - è critico quanto FAT16
3. **NON assumere che tutti i giochi abbiano la stessa struttura**
4. **NON usare v3/v4** - sono obsolete, usa sempre v5+

---

## 🔧 Troubleshooting

### "Save non trovato dopo restore"
1. Esegui `python diff_complete.py`
2. Verifica se ci sono bytes diversi in aree non coperte
3. Estendi la scansione cluster o aggiungi aree hardcoded

### "Hash non corrisponde"
- Il file backup è corrotto, ricrealo

### "Gioco si carica ma save è vuoto"
- Mancano directory entries del save slot interno
- Verifica che `scan_directory` trovi le entries

---

## 📚 Documentazione Estesa

- `AI_REFERENCE_SESSION2.md` - Scoperta problema Halo 2, analisi FAT chain
- `AI_REFERENCE_SESSION3.md` - Soluzione v5, test finali, fix v5.1

---

## 🏗️ Architettura

```
analyze_game_dynamic()
    ├── scan cluster 3-15 per entries
    ├── trova game folder
    ├── trova sibling save slots (nomi hex)
    ├── scansiona contenuto save slots
    │   └── fallback cluster+1 se vuoto
    ├── segue FAT chain
    └── calcola FAT range con margine

backup_single_game_v5()
    ├── chiama analyze_game_dynamic()
    ├── serializza directory entries
    ├── copia FAT16/FAT32 range
    ├── copia data chunks
    └── salva con hash MD5

restore_single_game_v5()
    ├── verifica hash
    ├── ripristina directory entries
    ├── ripristina FAT16/FAT32 range
    └── ripristina data chunks
```

---

## 📊 Strutture Gioco Incontrate

### Tipo 1: Standard (Mercenaries)
```
UDATA/4c410015/
    └── subdirectory con SaveMeta.xbx
```

### Tipo 2: Dati Diretti (Halo 2)
```
UDATA/4d530064/  → contiene dati, non directory entries
Save slot in cluster separato (27127)
```

### Tipo 3: Sibling Slots (NFS Underground 2)
```
UDATA/4541005a/  → contiene dati
12130F4013AB/    → save slot come sibling (non figlio!)
```

### Tipo 4: Anomalo (ToeJam)
```
Save slot a cluster 17710+ (lontanissimo)
Richiede diff e hardcoding
```

---

*Generato automaticamente - Non modificare manualmente*
