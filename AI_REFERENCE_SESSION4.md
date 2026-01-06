# 🔄 AI Reference - Session 4 (HANDOFF)

**Data:** 5 Gennaio 2026  
**Obiettivo:** Implementare analisi dinamica del TARGET per restore cross-HDD

---

## 📋 Situazione Attuale

### ✅ Cosa Funziona (v5.1)
Il sistema di backup/restore funziona **perfettamente** quando:
- SOURCE e TARGET sono lo **stesso HDD** (o stessa dimensione/struttura)
- Testato con 4 giochi: Mercenaries, Halo 2, NFS Underground 2, ToeJam

### ❌ Problema Scoperto
Quando l'utente:
1. Fa backup su HDD piccolo
2. Gioca su HDD più grande (nuovo)
3. Prova a ripristinare il backup vecchio

**Il restore NON funziona** perché:
- Gli OFFSET salvati nel backup sono relativi all'HDD SOURCE
- L'HDD TARGET ha struttura diversa (dimensione diversa = cluster in posizioni diverse)
- Il restore scrive agli offset SBAGLIATI

### Test Eseguito
```
1. Backup Halo 2 da HDD5 (checkpoint A)
2. Giocato Halo 2 su HDD target, avanzato a checkpoint B
3. Tentato restore del backup (checkpoint A)
4. Risultato: Il gioco carica checkpoint B, non A
   (il restore ha scritto in posizioni sbagliate)
```

---

## 🎯 Obiettivo Session 4

Implementare **ANALISI DINAMICA DEL TARGET** nel restore:

```python
# ATTUALE (non funziona cross-HDD):
def restore():
    for offset, data in backup:
        target.write(offset, data)  # Offset dal SOURCE!

# NUOVO (da implementare):
def restore():
    # 1. Trova dove sono i save sul TARGET
    target_game = analyze_game_dynamic(target_data, game_id)
    
    # 2. Mappa backup_cluster -> target_cluster
    # 3. Scrivi dati nelle posizioni CORRETTE del target
```

---

## 📁 File da Leggere

### Essenziali
1. **`single_game_merger.py`** - Script principale (1243 righe)
   - `analyze_game_dynamic()` - Trova cluster gioco (linea ~155)
   - `backup_single_game_v5()` - Backup (linea ~500)
   - `restore_single_game_v5()` - Restore DA MODIFICARE (linea ~600)

2. **`AI_REFERENCE_SESSION3.md`** - Documentazione completa v5.1

3. **`diff_complete.py`** - Utility per confrontare HDD

### Costanti Critiche
```python
FAT16_OFFSET = 0x00161000
FAT32_OFFSET = 0x00311000
DATA_START = 0x00443000
CLUSTER_SIZE = 16384
```

---

## 🔧 Approccio Suggerito

### Fase 1: Analisi Target
Nel restore, prima di scrivere:
```python
# Leggi anche il TARGET
with open(HDD_TARGET, 'rb') as f:
    target_data = f.read()

# Trova dove sono i save del gioco sul TARGET
target_analysis = analyze_game_dynamic(target_data, game_id)
```

### Fase 2: Mapping Cluster
Creare una mappa:
```python
# backup_cluster -> Quali dati contiene
# target_cluster -> Dove scrivere quei dati
```

### Fase 3: Problema Directory Entries
Le directory entries hanno offset assoluti. Se il gioco è in cluster diverso sul target:
- Devo trovare l'entry del gioco sul TARGET
- Sovrascrivere QUELLA entry (non quella del backup)

### Fase 4: FAT Entries
Stesso problema - le FAT entries devono essere scritte per i cluster del TARGET, non del SOURCE.

---

## ⚠️ Complessità

Questo è più complesso del backup perché:

1. **Struttura può essere diversa**: Il save sul target potrebbe avere più/meno file
2. **Cluster non 1:1**: Backup ha 10 cluster, target ne ha 12
3. **Directory entries**: Devono puntare ai cluster CORRETTI del target
4. **FAT chain**: Deve essere ricostruita per il target

### Possibile Semplificazione
Invece di "merge intelligente", potremmo:
1. **DELETE** il save esistente sul target (marca entries come deleted, azzera FAT)
2. **RECREATE** il save copiando i dati in cluster liberi
3. **UPDATE** FAT e directory entries

Questo è più "distruttivo" ma più semplice da implementare.

---

## 🧪 Test da Fare

1. Creare due HDD di dimensioni diverse con lo stesso gioco
2. Fare backup da uno
3. Restore sull'altro
4. Verificare che il save funzioni

---

## 📊 HDD Disponibili per Test

- `xbox_hdd.qcow2` - HDD attivo xemu
- `xbox_hdd3.qcow2` - Backup con 3 giochi
- `xbox_hdd4.qcow2` - Solo NFS
- `xbox_hdd5.qcow2` - Multi-gioco (usato come source attuale)

---

## 💡 Note Finali

Il progetto ha richiesto 5 mesi di sviluppo iterativo. La v5.1 funziona perfettamente per il caso d'uso "stesso HDD". L'estensione a "cross-HDD" è il prossimo passo logico ma richiede un ripensamento dell'architettura del restore.

**Leggi prima AI_REFERENCE_SESSION3.md per capire come funziona il sistema attuale!**

---

*Ultimo aggiornamento: 5 Gennaio 2026, 01:09*
