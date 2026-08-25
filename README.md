# RCShure - Shure Axient Digital Real-Time Monitor & Offline Simulator

**RCShure** è un'applicazione desktop standalone nativa per Windows (.exe portabile "zero-conf") progettata per il monitoraggio in tempo reale e la simulazione offline dei ricevitori microfonici digitali professionali **Shure Axient Digital** (modelli **AD4D** a 2 canali e **AD4Q** a 4 canali).

---

## Caratteristiche Principali

- **Zero Dipendenze Runtime**: Costruito al 100% con la Standard Library di Python 3 (`tkinter`, `socket`, `threading`, `time`, `json`, `queue`, `random`, `math`). Nessuna necessità di installare librerie esterne pesanti né DLL di terze parti.
- **Portabilità Totale ("Zero-Conf")**: Compilabile in un unico file standalone `.exe` eseguibile direttamente da una chiavetta USB su qualsiasi PC Windows moderno, anche completamente offline e senza Python installato.
- **Interfaccia Grafica Broadcast Dark**: Look professionale "Broadcast Control Room" con tema scuro ad alto contrasto, Canvas vettoriali personalizzati e scaling ad alta definizione (High-DPI aware).
- **VU-Meter Audio Reattivo con Peak Hold**: Indicatore di livello audio a segmenti colorati (Verde $\rightarrow$ Giallo $\rightarrow$ Arancione $\rightarrow$ Rosso Clip 0dBFS) con marker peak hold per transitori rapidi.
- **Monitor RF Link & Antenna Diversity**: Barra orizzontale graduata di qualità RF (0-255 / 0-100%) con badge dinamico per commutazione Antenna A / B.
- **Telemetria Batteria Intelligente**: Icona batteria dinamica con calcolo ore e minuti residui (`TX_BATT_MINS`), numero di barre (`TX_BATT_BARS`) e allarme visivo in caso di batteria scarica (< 20%).
- **Indicatori LED di Stato**: Flag virtuali LED per Mute, Interferenza RF rilevata (`INTERFERENCE_STATUS`), Crittografia attiva (`ENCRYPTION`) e Overload audio (Peak).
- **Simulatore Offline Nativo Integrato**: Possibilità di testare e dimostrare l'applicazione in qualsiasi momento senza avere fisicamente a disposizione un ricevitore Shure, simulando un AD4Q a 4 canali con dinamiche vocali realistiche, oscillazioni RF, scarica della batteria ed eventi di interferenza.
- **Connessione TCP Robusta & Auto-Reconnect**: Thread worker dedicato per comunicazioni non-bloccanti sulla porta standard 2202 e riconnessione automatica ogni 5 secondi in caso di disconnessione o caduta della rete.

---

## Architettura e Protocollo Shure

L'applicazione comunica via socket TCP/IP sulla porta standard **2202** utilizzando la specifica **Shure Command Strings**:
- Tutti i comandi sono racchiusi tra `<` e `>` e terminati con newline (`\n`).
- **Discovery e Setup**:
  - `< GET MODEL >` per identificare se l'apparato è un AD4D (2 canali) o AD4Q (4 canali).
  - `< GET <ch> CHAN_NAME >` e `< GET <ch> FREQUENCY >` per recuperare nomi e frequenze sintonizzate.
  - `< SET <ch> METER_RATE 00100 >` per abilitare la telemetria continua ad alta frequenza (ogni 100ms).
- **Messaggi Telemetrici Ricevuti**:
  - `< SAMPLE <ch> AUDIO_PEAK <val> RF_QUAL <val> RF_ANTENNA <A/B> ... >`
  - `< REP <ch> INTERFERENCE_STATUS <DETECTED/NONE> >`
  - `< REP <ch> TX_BATT_MINS <mins> >`

---

## Come Eseguire lo Script Python

Se si desidera eseguire l'applicazione dal codice sorgente:

```powershell
python axient_monitor.py
```

---

## Compilazione in Singolo File `.exe` Standalone

Per compilare l'applicazione in un singolo eseguibile portabile `.exe` per Windows:

### 1. Installare PyInstaller (se non già presente)
```powershell
pip install pyinstaller
```

### 2. Eseguire il comando di compilazione
```powershell
pyinstaller --clean --onefile --noconsole --name "RCShure" axient_monitor.py
```

Oppure fare doppio click sul file **`build.bat`** incluso nel repository.

### 3. Risultato
Il file eseguibile standalone sarà generato in:
```
dist\RCShure.exe
```
Questo singolo file `.exe` può essere copiato su una chiavetta USB e avviato su qualunque PC con Windows (10/11/Server) senza alcuna installazione.

---

## Utilizzo

1. **Avvio**: Lanciare `RCShure.exe` o `python axient_monitor.py`.
2. **Modalità Ricevitore Reale**:
   - Inserire l'indirizzo IP del ricevitore Shure Axient (es. `192.168.1.50`).
   - Verificare la porta (default: `2202`).
   - Assicurarsi che la spunta *"Modalità Simulazione Offline"* sia disattivata.
   - Cliccare su **CONNETTI**.
3. **Modalità Simulazione Offline**:
   - Attivare la spunta *"Modalità Simulazione Offline"*.
   - Cliccare su **CONNETTI**.
   - Verranno generati in tempo reale dati telemetrici coerenti a 4 canali per testare l'interfaccia.

---

## Licenza
Distribuito sotto licenza MIT.
