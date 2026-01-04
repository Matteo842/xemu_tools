# 🎉 AI Reference - Session 3 (PROBLEMA RISOLTO!)

**⚠️ QUESTO FILE È UN CONTINUO DI `AI_REFERENCE_SESSION2.md` - LEGGI PRIMA QUELLO!**

**Data sessione:** 4 Gennaio 2026
**Obiettivo:** ~~Documentazione completa FATX + Strategia per risolvere il problema di Halo 2~~
**RISULTATO:** ✅ **HALO 2 FUNZIONA!** La v5 con FAT Range ha risolto il problema!

---

## 📚 Fonti Ufficiali Consultate

1. **xboxdevwiki.net/FATX** - Wiki ufficiale della community Xbox
2. **github.com/mborgerson/fatx** (libfatx) - Libreria FATX usata da xemu
3. **free60.org** - Documentazione della community
4. **Ricerche sul comportamento di delete in FATX**

---

## 🔬 Struttura FATX - Documentazione Completa

### Header FATX (Superblock)
Il superblock è di **4096 bytes** e contiene:

```c
struct fatx_superblock {
    uint32_t signature;           // 0x00: "FATX" (0x58544146)
    uint32_t volume_id;           // 0x04: Serial number
    uint32_t sectors_per_cluster; // 0x08: Tipicamente 32 (=16KB cluster)
    uint32_t root_cluster;        // 0x0C: Cluster della root directory
    uint16_t unknown1;            // 0x10: Sconosciuto
    uint8_t  padding[4078];       // Padding a 4096 bytes
};
```

### Directory Entry FATX (64 bytes)
Questa è la struttura **CRITICA** per il nostro problema:

```c
struct fatx_raw_directory_entry {
    uint8_t  filename_len;    // 0x00: Lunghezza nome (0xE5 = deleted!)
    uint8_t  attributes;      // 0x01: Attributi file (0x10 = directory)
    char     filename[42];    // 0x02: Nome file (42 bytes max)
    uint32_t first_cluster;   // 0x2C: PRIMO CLUSTER del file/directory
    uint32_t file_size;       // 0x30: Dimensione file
    uint16_t modified_time;   // 0x34: Ora modifica
    uint16_t modified_date;   // 0x36: Data modifica
    uint16_t created_time;    // 0x38: Ora creazione
    uint16_t created_date;    // 0x3A: Data creazione
    uint16_t accessed_time;   // 0x3C: Ora accesso
    uint16_t accessed_date;   // 0x3E: Data accesso
};
// Total: 64 bytes
```

### Layout Disco Xbox (Retail)

| Partizione | Offset | Size | Lettera | Contenuto |
|------------|--------|------|---------|-----------|
| Data | 0x80000 | 750MB | C: | System/Dashboard |
| Shell | 0x2EE80000 | 750MB | E: | **UDATA/TDATA** |
| Cache1 | 0x5DC80000 | 750MB | X: | Cache |
| Cache2 | 0x8CA80000 | 750MB | Y: | Cache |
| Cache3 | 0xBB880000 | 750MB | Z: | Cache |

**⚠️ IMPORTANTE:** Il nostro HDD xemu usa un layout diverso! Gli offset che abbiamo trovato (FAT16 a 0x161000, FAT32 a 0x311000) sono specifici per l'immagine pre-formattata di xemu.

---

## 🔑 Scoperta Chiave: Come Funziona la Cancellazione FATX

### Quando xemu/Xbox cancella un save:

1. **Directory Entry** → Il primo byte (filename_len) viene impostato a `0xE5`
2. **FAT Chain** → I cluster vengono azzerati (marcati come "free")
3. **Dati** → I dati NON vengono cancellati immediatamente, restano sul disco

### Questo spiega il problema di Halo 2!

Quando cancelliamo il save di Halo 2:
- I suoi cluster (54-146) vengono marcati come "free" nella FAT
- Ma la FAT è una struttura CONDIVISA con tutti i giochi
- Le modifiche alla FAT colpiscono anche aree usate POTENZIALMENTE da altri giochi

---

## 🎯 Analisi del Problema con Halo 2

### Cluster modificati che NON sono nella chain di Halo 2:

| Offset | Cluster | Bytes | Problema |
|--------|---------|-------|----------|
| 0x00310000 | 147+ | 233 | FAT32 entries di cluster NON in Halo 2! |
| 0x05410000 | 5111 | 1,470 | Appartiene a Mercenaries |
| 0x0a410000 | 10231 | 6 | Chain di 143 cluster |
| 0x1af60000 | 27339 | 1,220 | Standalone, "daeh" header |

### Ipotesi: Il problema NON è nei dati, ma nella FAT!

Quando xemu cancella un file:
1. Azzera i FAT entries del file cancellato
2. Potrebbe modificare "metadati" interni della FAT (allocator state?)
3. Questi metadati influenzano come vengono allocati i NUOVI cluster

---

## 💡 Strategie Proposte (in ordine di preferenza)

### Strategia 1: Backup della FAT Completa (Più Sicura)

**Concetto:** Invece di salvare solo i FAT entries dei cluster del gioco, salvare TUTTA la sezione FAT.

**Pro:**
- Garantisce coerenza completa
- Risolve il problema dei "cluster collaterali"

**Contro:**
- Backup più grandi (~128KB per FAT32)
- Potrebbe sovrascrivere modifiche fatte da altri giochi

### Strategia 2: Approccio "Overwrite" invece di "Delete + Restore"

**Concetto:** Non cancellare mai il save originale. Sovrascrivere direttamente i dati.

**Come funzionerebbe:**
1. Non cancellare il save del gioco target
2. Scrivere i dati del backup direttamente sugli stessi cluster
3. Aggiornare solo i FAT entries necessari

**Pro:**
- Evita completamente il problema della cancellazione
- Più veloce

**Contro:**
- Richiede che i cluster siano liberi o già usati dal gioco
- Complesso se la struttura del save è cambiata

### Strategia 3: Backup "Esteso" della FAT

**Concetto:** Identificare TUTTE le aree FAT che potrebbero cambiare e salvarle.

**Come:**
1. Prima del backup, fare un dump della FAT completa
2. Identificare quali entries appartengono a cluster "vicini" o correlati
3. Salvare anche queste entries

### Strategia 4: "Surgical Write" - Ricrea solo il necessario

**Concetto:** Invece di restaurare, RICREA la struttura del save.

**Come:**
1. Trova un cluster libero
2. Scrivi i dati del save
3. Aggiorna la FAT con la nuova chain
4. Ricrea la directory entry

**Pro:**
- Non dipende dalla struttura precedente

**Contro:**
- Molto più complesso
- Rischio di corrompere il filesystem

---

## 🔧 Strategia Consigliata: Backup FAT Range

Data la nostra analisi, propongo un approccio ibrido:

### Fase 1: Identificare il "FAT Range" del gioco

```python
def get_fat_range(game_clusters):
    """
    Data una lista di cluster, trova il range FAT che copre
    tutti i cluster potenzialmente correlati.
    """
    min_cluster = min(game_clusters)
    max_cluster = max(game_clusters)
    
    # Aggiungi margine di sicurezza
    margin = 50  # cluster extra prima e dopo
    
    start_cluster = max(0, min_cluster - margin)
    end_cluster = max_cluster + margin
    
    return start_cluster, end_cluster
```

### Fase 2: Salvare TUTTO il FAT range

Invece di salvare solo i FAT entries dei cluster specifici, salviamo l'intera porzione della FAT che copre il range del gioco.

### Fase 3: Al restore, ripristinare l'intero range

Questo garantisce che tutti i "metadati" correlati siano ripristinati.

---

## 📊 Costanti FATX Importanti (da libfatx)

```python
# Da fatx_internal.h
FATX_SIGNATURE = 0x58544146           # "FATX"
FATX_SUPERBLOCK_SIZE = 4096           # 4KB
FATX_FAT_OFFSET = 4096                # FAT inizia dopo superblock
FATX_FAT_RESERVED_ENTRIES_COUNT = 1   # Entry 0 riservata
FATX_MAX_FILENAME_LEN = 42            # Max 42 caratteri
FATX_END_OF_DIR_MARKER = 0xFF         # Fine directory
FATX_DELETED_MARKER = 0xE5            # File cancellato

# Tipi FAT
FATX_FAT_TYPE_16 = 1                  # < 65520 cluster
FATX_FAT_TYPE_32 = 2                  # >= 65520 cluster

# Attributi directory entry
FATX_ATTR_READ_ONLY = 0x01
FATX_ATTR_HIDDEN = 0x02
FATX_ATTR_SYSTEM = 0x04
FATX_ATTR_DIRECTORY = 0x10
FATX_ATTR_ARCHIVE = 0x20
```

---

## 🔄 Struttura Save Xbox (UDATA)

### Gerarchia tipica:
```
E:\UDATA\
└── {TitleID}\           # es. 4d530064 (Halo 2)
    ├── TitleMeta.xbx    # Metadati titolo
    ├── TitleImage.xbx   # Immagine titolo (64x64)
    └── {SaveSlotID}\    # es. 589BCCD01326
        ├── SaveMeta.xbx # Metadati save
        ├── SaveImage.xbx # Immagine save
        └── [save data]  # Dati specifici del gioco
```

### File SaveMeta.xbx formato:
```
TitleName=Game Title Name
```
Può contenere localizzazioni con codici lingua (es. `[jp]TitleName=...`)

---

## 🧪 Test da Effettuare

1. **Test FAT Range:** Implementare backup con range FAT e verificare se risolve Halo 2
2. **Test Overwrite:** Provare a sovrascrivere invece di delete+restore
3. **Confronto pre/post:** Fare dump FAT prima e dopo delete per vedere ESATTAMENTE cosa cambia

## ✅ IMPLEMENTAZIONE COMPLETATA

### Funzioni Aggiunte in `single_game_merger.py`:

1. **`calculate_fat_range(clusters, margin=100)`**
   - Prende i cluster usati dal gioco
   - Calcola min/max e aggiunge un margine di sicurezza (default 100 cluster)
   - Ritorna il range da salvare

2. **`backup_single_game_v5(game_id)`**
   - Usa `analyze_game_dynamic()` (dalla v4) per trovare tutti i cluster
   - Calcola il FAT range con margine
   - Salva BLOCCHI INTERI di FAT16 e FAT32 invece di entries singole
   - Crea file `{game_id}_fatrange_{timestamp}.bin` e `.json`

3. **`restore_single_game_v5(backup_file, metadata_file)`**
   - Legge il backup v5
   - Ripristina il BLOCCO INTERO della FAT16 e FAT32
   - Questo include tutti i "cluster collaterali"

### Formato Backup v5:

```
[Header]
  Magic: "XBSV" (4 bytes)
  Version: 5 (uint32)
  Game ID: 8 bytes ASCII

[Directory Entries]
  Count: uint32
  Per entry: offset (uint32) + data (64 bytes)

[FAT16 Range]  <-- NUOVO in v5!
  Range Start Cluster: uint32
  Range Cluster Count: uint32
  File Offset: uint32
  Data Size: uint32
  Data: bytes

[FAT32 Range]  <-- NUOVO in v5!
  Range Start Cluster: uint32
  Range Cluster Count: uint32
  File Offset: uint32
  Data Size: uint32
  Data: bytes

[Data Chunks]
  Count: uint32
  Per chunk: cluster, offset (uint32 each) + size (uint32) + data
```

### Menu Aggiornato:

```
1. Lista giochi disponibili

--- BACKUP (consigliato: v5) ---
2. Backup FAT RANGE v5 (CONSIGLIATO)
3. Backup dinamico v4 (legacy)

--- RESTORE ---
4. Restore (auto-detect versione)

--- ALTRO ---
5. Lista backup disponibili
0. Esci
```

---

## 📝 Prossimi Passi ~~Concreti~~ → COMPLETATI!

1. [x] ~~Modificare `single_game_merger.py` per salvare un FAT range invece di entries singoli~~
2. [x] ~~Aggiungere opzione per backup "esteso" della FAT~~
3. [x] ~~Testare con Halo 2~~
4. [x] ~~Se funziona, generalizzare l'approccio~~

---

## 🎉 RISULTATO TEST FINALE

**Test effettuato:** 4 Gennaio 2026, ~04:43

1. Backup v5 di Halo 2 creato con successo
2. Cancellati TUTTI i save (Halo 2, Mercenaries, ToeJam & Earl)
3. Ripristinato SOLO il backup v5 di Halo 2
4. Risultati:
   - **Halo 2:** ✅ FUNZIONA! Save caricati correttamente
   - **Mercenaries:** ✅ "You have no saved games" (corretto, non ripristinato)
   - **ToeJam & Earl:** ✅ "Nessuna partita disponibile" (corretto, non ripristinato)

**CONCLUSIONE:** La v5 con FAT Range FUNZIONA e risolve il problema dei "cluster collaterali"!

---

*Sessione iniziata: 4 Gennaio 2026, 04:14*
*Documentazione FATX completata da fonti ufficiali*
*TEST PASSATO: 04:43*
*Halo 2 finalmente funziona! 🎮*

