# 🔧 AI Reference - Session 6 (Halo 2 Analysis Complete)

**Data:** 6 Gennaio 2026, 03:56 - 06:23  
**Obiettivo:** Capire perché il restore del checkpoint Halo 2 fallisce
**RISULTATO:** ✅ Mystery SOLVED - Halo 2 è un caso limite!

---

## 🎯 SCOPERTA PRINCIPALE

### Halo 2 usa l'HDD come RAM Dump!

A differenza di altri giochi (Mercenaries, NFS, ToeJam), **Halo 2 salva i checkpoint nella cache del gioco**, non in `auxilary.bin`.

| Componente | Dimensione | Contiene Checkpoint? |
|------------|------------|---------------------|
| `auxilary.bin` | 4 MB | ❌ Solo ~31KB cambiano tra CP |
| `cache000.map` | 180 MB | ✅ Parte dei dati del CP |
| `cache001.map` | 520 MB | ✅ Parte dei dati del CP |
| Area post-cache | variable | ✅ Contiene dati critici |

**Per ripristinare un checkpoint di Halo 2 servono ~270 MB!**

---

## 📊 Test Effettuati

| Test | Byte Copiati | Risultato |
|------|--------------|-----------|
| Solo cluster 10-279 + 11473 | ~4.4 MB | ❌ Stesso CP |
| Escludendo cache (< cluster 10000) | 80 KB | ❌ Stesso CP |
| Fino a cluster 36218 | 80 KB | ⚠️ Menu OK, dati corrotti! |
| **Tutto H1 (270MB)** | **270 MB** | **✅ FUNZIONA!** |

### Analisi Distribuzione Differenze H1 vs H2:

```
Cluster 1-58 (pre-cache): 93 byte diversi
Cluster 59-267 (auxilary.bin area): 30,954 byte diversi
Cluster 268-1000: 38,381 byte diversi
Cluster 10001-11578: 100 byte diversi
Cluster 36219+ (post-cache): 137,088,296 byte diversi (137 MB!)

FAT area: 0 byte diversi
Pre-FAT (header): 10,943 byte diversi

TOTALE: 270,673,349 bytes
```

---

## 🔍 Struttura Scoperta

### File del Save (in H1):
```
auxilary.bin:
  - Entry @ offset 0x0b4f3080 (cluster 11473)
  - Dati @ cluster 12, size 4,186,132 bytes
  
profile:
  - Entry @ cluster 11473
  - Dati @ cluster 11, size 500 bytes
  
SaveMeta.xbx:
  - Entry @ cluster 11473
  - Dati @ cluster 10, size 50 bytes
```

### File Cache:
```
cache000.map:
  - first_cluster=59
  - size=188,743,680 bytes (180 MB)
  - Cluster range: 59-11578 (11520 cluster)

cache001.map:
  - first_cluster=2939
  - size=545,259,520 bytes (520 MB)
  - Cluster range: 2939-36218 (33280 cluster)
```

### Dimensioni HDD:
```
H1 (checkpoint 1): 1,008,861,184 bytes = ~61467 cluster
H2 (checkpoint 2): 1,188,298,752 bytes = ~72419 cluster
```

---

## ⚠️ Perché Halo 2 è un Caso Limite

1. **L'HDD cresce enormemente** - Da 985KB (vuoto) a 1GB+ solo avviando il gioco
2. **I checkpoint sono nella cache** - Non in auxilary.bin come ci si aspetterebbe
3. **Dati distribuiti ovunque** - Cluster 36219-61467 contengono dati critici
4. **Serve tutto** - ~270 MB per ripristinare un singolo checkpoint

### Conseguenza per il Backup Dinamico:
- ❌ Non puoi fare un backup "chirurgico" per Halo 2
- ❌ Non puoi usare il metodo diff (richiede ENTRAMBI gli HDD)
- ✅ Devi salvare l'intero stato del gioco (~700MB cache + save)

---

## ✅ Cosa Funziona (per altri giochi)

Il sistema v5.1 funziona perfettamente per:
- Mercenaries
- NFS Underground 2
- ToeJam & Earl III

Questi giochi hanno save più piccoli e strutturati.

---

## 🎯 Prossimi Passi (Session 7)

### Cambio Strategia: Test con "Black"

1. Metti in pausa Halo 2 (caso limite, gestiremo dopo)
2. Testa con "Black" - gioco più strutturato
3. Implementa `restore_game_dynamic_v6` con logica "Valet Parking"

### Requisiti per v6 ("File System Driver"):
1. **NO offset assoluti** dal backup
2. Riceve BLOB dei file estratti
3. Legge FAT del Target per trovare cluster liberi (0x0000)
4. Scrive file nei nuovi cluster liberi
5. Ricostruisce catena FAT corretta
6. Aggiorna Directory Entry per puntare al nuovo cluster

---

## 📁 Script Creati in Questa Sessione

| Script | Scopo |
|--------|-------|
| `analyze_halo2_save.py` | Trova auxilary.bin e file save |
| `debug_fat_chain.py` | Debug della FAT chain |
| `analyze_diff_areas.py` | Distribuzione differenze per area |
| `analyze_cache_detail.py` | Analisi dettagliata cache |
| `analyze_post_cache.py` | Cosa c'è nell'area post-cache |
| `copy_exact_diff.py` | Copia tutti i byte diversi |
| `restore_no_cache.py` | Restore escludendo cache |
| `restore_to_36218.py` | Restore fino a cluster 36218 |
| `restore_full_h1.py` | Restore completo H1 |
| `simple_restore_halo2.py` | Primo tentativo (fallito) |

---

## 💡 Lezioni Apprese

1. **Non tutti i giochi sono uguali** - Halo 2 è un caso estremo
2. **La cache può contenere checkpoint** - Non solo texture
3. **L'HDD cresce enormemente** - Halo 2 usa l'HDD come RAM dump
4. **Test con giochi "normali"** - Prima di generalizzare

---

## 🏆 Risultato della Sessione

**MYSTERY SOLVED!** Sappiamo esattamente perché Halo 2 richiede 270MB:
- I checkpoint sono salvati nella cache, non in auxilary.bin
- È un caso limite che altri giochi probabilmente non hanno
- Il prossimo passo è testare con un gioco più normale (Black)

---

*Sessione completata: 6 Gennaio 2026, 06:23*
*Prossima sessione: Test con "Black" e implementazione v6*
