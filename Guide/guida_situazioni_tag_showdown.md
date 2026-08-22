# Guida Completa alla Mappatura dei Tag e Eventi di Pokémon Showdown per VGC

Questa guida tecnica è progettata per supportare lo sviluppo del parser Python e dell'interfaccia PySide6 del tuo software di analisi di gioco per il Pokémon VGC. Fornisce una mappatura esaustiva e rigorosa di ogni situazione di gioco (danno, climi, stadi, abilità, strumenti, ecc.) collegandola direttamente alla sintassi dei log di Pokémon Showdown.

---

## 1. Struttura del Turno e Flusso Temporale

I log di Pokémon Showdown sono strutturati in modo strettamente sequenziale ed orientati agli eventi (Event Sourcing). Un turno di gioco è sempre delimitato da tag specifici.

### Delimitatore del Turno
* **Tag:** `|turn|{numero}`
* **Significato:** Segnala l'inizio di un nuovo turno di gioco. Tutte le azioni successive avvengono all'interno di questo turno fino al prossimo tag `|turn|`.
* **Esempio:** 
  ```text
  |turn|1
  ```

### Fase di Manutenzione di Fine Turno (Upkeep)
* **Tag:** `|upkeep`
* **Significato:** Segnala la fine delle azioni principali del turno e l'inizio della risoluzione degli effetti di fine turno (danni da scottatura/veleno, Leftovers, climatici, ecc.). Questa fase si conclude con il tag `|turn|` successivo o con la fine della partita.
* **Esempio:**
  ```text
  |upkeep
  ```

### Marcatore Temporale
* **Tag:** `|t:|{timestamp}`
* **Significato:** Indica il tempo UNIX (in secondi) in cui l'evento o la decisione è avvenuta. Utile per analizzare i tempi di decisione dei giocatori.
* **Esempio:**
  ```text
  |t:|1781093484
  ```

---

## 2. Eventi Primari (Nodi Principali della Timeline)

Questi eventi rappresentano le azioni principali compiute dai Pokémon o dai giocatori. Nella tua interfaccia basata su `QTreeWidget`, questi tag dovrebbero generare i nodi di primo livello all'interno di ciascun turno.

### A. Esecuzione di una Mossa
* **Tag:** `|move|{pokemon_attore}|{nome_mossa}|{pokemon_bersaglio}|[attributi_opzionali]`
* **Attributi:**
  * `{pokemon_attore}`: Identificativo dello slot e nome (es. `p1a: Kangaskhan`).
  * `{nome_mossa}`: Nome della mossa eseguita (es. `Fake Out`).
  * `{pokemon_bersaglio}`: Lo slot e il nome del bersaglio designato. Se la mossa non ha un bersaglio singolo (es. mosse ad area come *Heat Wave*), questo campo può essere vuoto o riferito a una direzione generica.
  * `[spread]`: Indica che la mossa colpisce più bersagli (es. `[spread] p1a,p1b`).
* **Esempio Reale:**
  ```text
  |move|p1a: Kangaskhan|Fake Out|p2a: Floette
  ```

### B. Sostituzione (Switch e Drag)
* **Tag:** 
  * `|switch|{slot_giocatore: nome}|{specie, livello, genere}|{hp_correnti}/{hp_totali}`
  * `|drag|{slot_giocatore: nome}|{specie, livello, genere}|{hp_correnti}/{hp_totali}` (usato per switch forzati da mosse come *Roar* o *Dragon Tail*).
* **Attributi:**
  * `{slot_giocatore: nome}`: Lo slot di campo (`p1a`, `p1b`, `p2a`, `p2b`) seguito dal nome del Pokémon (es. `p2a: Incineroar`).
  * `{specie, livello, genere}`: I dettagli del Pokémon (es. `Incineroar, L50, M`). Il livello predefinito è 100 se non specificato; in VGC è quasi sempre `L50`.
  * `{hp_correnti}/{hp_totali}`: La percentuale o il valore nominale di HP con cui entra in campo (es. `100/100`).
* **Esempio Reale:**
  ```text
  |switch|p2a: Incineroar|Incineroar, L50, M|100/100
  ```

### C. Sfinimento (Faint)
* **Tag:** `|faint|{pokemon_finito}`
* **Significato:** Il Pokémon specificato ha esaurito gli HP e va KO. Questo evento deve attivare la rimozione visiva del Pokémon dal campo di battaglia e segnare lo stato come "fnt" (fainted).
* **Esempio Reale:**
  ```text
  |faint|p1b: Starmie
  ```

### D. Incapacità di Agire (Cant)
* **Tag:** `|cant|{pokemon}|{motivo}|{mossa_tentata}`
* **Significato:** Il Pokémon non può eseguire la mossa selezionata a causa di una condizione di stato o un effetto volatile (tentennamento, paralisi, sonno, provocazione, ecc.).
* **Motivi Comuni (`{motivo}`):**
  * `flinch` (Tentennamento indotto da mosse come *Fake Out*).
  * `paralysis` (Paralisi).
  * `slp` (Sonno).
  * `recharge` (Turno di ricarica, es. dopo *Giga Impact*).
  * `recoil` (Incapacità dovuta a blocco).
  * `Taunt` (Incapacità di usare mosse di stato sotto l'effetto di Provocazione).
* **Esempio Reale:**
  ```text
  |cant|p2a: Floette|flinch
  ```

---

## 3. Sotto-Eventi e Modificatori (Secondari / Effetti Visivi)

Questi tag iniziano sempre con un trattino (`-`) e rappresentano gli effetti diretti prodotti dalle mosse o dalle abilità. Nella UI PySide6, **non devono essere nodi principali**, ma devono aggiornare visivamente le barre degli HP, mostrare icone di stato o aggiornare i testi di riepilogo del nodo mossa genitore.

### A. Riduzione degli HP (Danno)
* **Tag:** `|-damage|{pokemon_colpito}|{hp_rimanenti}/{hp_totali}|[motivo_opzionale]`
* **Attributi:**
  * `{pokemon_colpito}`: Il Pokémon che subisce il danno.
  * `{hp_rimanenti}/{hp_totali}`: Il nuovo stato di salute del Pokémon dopo il danno (es. `43/100` o `0 fnt` se va KO).
  * `[motivo_opzionale]`: Se il danno non è causato da un attacco diretto, Showdown specifica la fonte:
    * `[from] brn` (Scottatura)
    * `[from] psn` o `[from] tox` (Avvelenamento)
    * `[from] Sandstorm` o `[from] Hail` (Clima)
    * `[from] item: Life Orb` (Danno da contraccolpo dello strumento Assorbisfera)
    * `[from] ability: Iron Barbs` / `[from] Rocky Helmet` (Abilità o strumenti di contatto)
    * `[from] Recoil` (Contraccolpo da mosse come *Flare Blitz*)
* **Esempi Reali:**
  * *Danno diretto da attacco:*
    ```text
    |-damage|p2a: Floette|81/100
    ```
  * *Danno a fine turno da Scottatura (Burn):*
    ```text
    |-damage|p2a: Floette|37/100 brn|[from] brn
    ```

### B. Ripristino degli HP (Cura)
* **Tag:** `|-heal|{pokemon_curato}|{hp_rimanenti}/{hp_totali}|[motivo_opzionale]`
* **Attributi:**
  * `[motivo_opzionale]`: Rileva la fonte di guarigione:
    * `[from] drain|[of] {pokemon_bersaglio}` (Effetto vampirismo da mosse come *Matcha Gotcha* o *Giga Drain*).
    * `[from] item: Leftovers` (Avanzi)
    * `[from] item: Sitrus Berry` (Baccacedro)
    * `[from] move: Life Dew` (Sgocciolamento)
* **Esempi Reali:**
  * *Cura tramite mossa drenante (Matcha Gotcha):*
    ```text
    |-heal|p2b: Sinistcha|60/100|[from] drain|[of] p1a: Kangaskhan
    ```
  * *Cura tramite strumento consumo (Baccacedro):*
    ```text
    |-heal|p2a: Incineroar|60/100|[from] item: Sitrus Berry
    ```

### C. Variazione delle Statistiche (Boost / Unboost)
* **Tag:** 
  * `|-boost|{pokemon}|{stat}|{stadi}` (Aumento di statistiche)
  * `|-unboost|{pokemon}|{stat}|{stadi}` (Diminuzione di statistiche)
  * `|-setboost|{pokemon}|{stat}|{stadi}` (Forzatura a uno stadio specifico, es. *Belly Drum*)
  * `|-clearboost|{pokemon}` (Annullamento di tutti i boost di un Pokémon, es. *Haze*)
* **Statistiche (`{stat}`):** `atk` (Attacco), `def` (Difesa), `spa` (Attacco Speciale), `spd` (Difesa Speciale), `spe` (Velocità), `eva` (Elusione), `acc` (Precisione).
* **Esempi Reali:**
  * *Diminuzione di Attacco da Intimidate:*
    ```text
    |-unboost|p1b: Starmie|atk|1
    ```
  * *Aumento tramite Calm Mind:*
    ```text
    |-boost|p2a: Floette|spa|1
    |-boost|p2a: Floette|spd|1
    ```

### D. Stati Alterati Primari
* **Tag:**
  * `|-status|{pokemon}|{stato}` (Applicazione dello stato)
  * `|-curestatus|{pokemon}|{stato}` (Guarigione dallo stato)
  * `|-cureteam|{pokemon}` (Cura dell'intero team da stati alterati, es. *Aromatherapy*)
* **Stati (`{stato}`):**
  * `brn` ( Scottatura / Burn )
  * `par` ( Paralisi / Paralysis )
  * `slp` ( Sonno / Sleep )
  * `psn` ( Avvelenamento / Poison )
  * `tox` ( Tossina / Bad Poison )
  * `frz` ( Congelamento / Freeze )
* **Esempio Reale:**
  ```text
  |-status|p2a: Floette|brn
  ```

---

## 4. Clima, Campi ed Effetti Ambientali

Nel VGC il controllo del campo è fondamentale. Questi tag modificano lo stato globale del campo o lo stato dei singoli lati (Side) dei giocatori.

| Elemento di Gioco | Tag di Attivazione | Tag di Fine / Rimozione | Esempio di Log Showdown |
| :--- | :--- | :--- | :--- |
| **Meteo (Weather)** | `|-weather|{tipo_clima}|[from]...` | `|-weather|none` | `|-weather|SunnyDay\|[from] ability: Drought` |
| **Campi (Terrains)** | `|-fieldstart|{tipo_campo}` | `|-fieldend|{tipo_campo}` | `|-fieldstart|move: Psychic Terrain` |
| **Trick Room** | `|-fieldstart|move: Trick Room` | `|-fieldend|move: Trick Room` | `|-fieldstart|move: Trick Room\|[of] p1b: Chandelure` |
| **Ventoincoda (Tailwind)**| `|-sidestart|{lato}: {giocatore}|move: Tailwind` | `|-sideend|{lato}: {g}|move: Tailwind`| `|-sidestart|p1: 7upikid\|move: Tailwind` |
| **Riflesso (Reflect)** | `|-sidestart|{lato}: {giocatore}|move: Reflect` | `|-sideend|{lato}: {g}|move: Reflect` | `|-sidestart|p2: jirkunow\|move: Reflect` |
| **Schermoluce (L.Screen)**| `|-sidestart|{lato}: {giocatore}|move: Light Screen`| `|-sideend|{lato}: {g}|move: Light Screen`| `|-sidestart|p1: 7upikid\|move: Light Screen` |
| **Velaurora (Aurora Veil)**| `|-sidestart|{lato}: {giocatore}|move: Aurora Veil` | `|-sideend|{lato}: {g}|move: Aurora Veil` | `|-sidestart|p2: jirkunow\|move: Aurora Veil` |

### Tipi di Clima Comuni (`{tipo_clima}`):
* `SunnyDay` (Sole)
* `RainDance` (Pioggia)
* `Sandstorm` (Tempesta di Sabbia)
* `Snow` (Neve)
* `none` (Annullamento del clima)

### Tipi di Campi Comuni (`{tipo_campo}`):
* `ElectricTerrain` (Campo Elettrico)
* `GrassyTerrain` (Campo Erboso)
* `MistyTerrain` (Campo Nebbioso)
* `PsychicTerrain` (Campo Psichico)

---

## 5. Abilità e Strumenti (Abilities & Items)

Molti effetti speciali avvengono passivamente all'ingresso in campo o al soddisfacimento di determinate condizioni.

### Attivazione Abilità
* **Tag:** `|-ability|{pokemon}|{nome_abilita}|[effetto]|[of] {pokemon_attivatore}`
* **Significato:** Traccia l'annuncio o l'attivazione di un'abilità.
* **Esempio Reale (Intimidate):**
  ```text
  |-ability|p2a: Incineroar|Intimidate|boost
  ```

### Attivazione Strumento
* **Tag:** `|-item|{pokemon}|{nome_strumento}|[motivo]`
* **Significato:** Mostra che un Pokémon ha rivelato o attivato uno strumento.
* **Esempio Reale:**
  ```text
  |-item|p1a: Sneasler|White Herb|[from] item: White Herb
  ```

### Consumo Strumento
* **Tag:** `|-enditem|{pokemon}|{nome_strumento}|[motivo]`
* **Significato:** Lo strumento è stato consumato (es. una bacca mangiata, una White Herb consumata, una focalnastro attivata).
* **Esempio Reale:**
  ```text
  |-enditem|p2a: Incineroar|Sitrus Berry|[eat]
  ```

---

## 6. Meccaniche Speciali della Generazione 9

Questi tag gestiscono le meccaniche di trasformazione uniche dei giochi competitivi, essenziali per aggiornare correttamente le icone dei Pokémon nella tua interfaccia grafica.

### A. Teracristallizzazione (Terastallization)
* **Tag:** `|-tera|{pokemon}|{tipo_teratipo}`
* **Significato:** Il Pokémon specificato attiva la Teracristallizzazione cambiando il proprio tipo primario nel teratipo indicato.
* **Esempio:**
  ```text
  |-tera|p1b: Chandelure|Grass
  ```

### B. Megaevoluzione (Mega Evolution)
* **Tag:**
  * `|detailschange|{pokemon}|{nuovo_nome_dettagli}`
  * `|-mega|{pokemon}|{specie_base}|{pietra_mega}`
* **Significato:** Rappresenta il cambio di forma e l'attivazione della Megaevoluzione (utilizzata in tier speciali o passate della Generazione 9 Champions).
* **Esempio Reale:**
  ```text
  |detailschange|p1b: Starmie|Starmie-Mega, L50
  |-mega|p1b: Starmie|Starmie|Starminite
  ```

---

## 7. Eventi di Attivazione e Immunità (Messaggi Informativi)

Questi tag servono per descrivere perché un'azione è fallita o ha avuto un esito particolare, consentendo al tuo parser di popolare il campo `details` nel database.

### Efficacia del Danno
* **Tag Superefficace:** `|-supereffective|{pokemon_bersaglio}`
* **Tag Poco Efficace:** `|-resisted|{pokemon_bersaglio}`
* **Esempio Reale:**
  ```text
  |-supereffective|p2b: Sinistcha
  ```

### Immunità Totale
* **Tag:** `|-immune|{pokemon_bersaglio}|[from]...`
* **Significato:** Il bersaglio è totalmente immune all'attacco (es. tipo Spettro colpito da mossa Normale, o tipo Terra colpito da mossa Elettro).
* **Esempio Reale:**
  ```text
  |move|p1a: Kangaskhan|Last Resort|p2b: Sinistcha
  |-immune|p2b: Sinistcha
  ```

### Fallimento dell'Azione (Fail e Miss)
* **Tag Fallimento generico:** `|-fail|{pokemon}|{azione_fallita}` (es. quando si usa *Thunder Wave* su un tipo Terra).
* **Tag Mossa Mancata:** `|-miss|{pokemon_attore}|{pokemon_bersaglio}` (la mossa è fallita a causa della precisione).
* **Esempio Reale:**
  ```text
  |-fail|p1a: Kangaskhan|unboost|Attack|[from] ability: Scrappy|[of] p1a: Kangaskhan
  ```

---

## 8. Flusso Completo di un Turno: Esempio di Parsing

Ecco come una breve sequenza di log grezzo viene interpretata dal tuo parser e mappata nello stato del campo (`MatchState`) e nelle azioni del database:

### Log Grezzo di Showdown:
```text
|turn|5
|switch|p1a: Torkoal|Torkoal, L50, M|100/100
|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Torkoal
|move|p1b: Chandelure|Heat Wave|p2b: Sinistcha|[spread] p2a,p2b
|-damage|p2a: Floette|43/100
|-damage|p2b: Sinistcha|0 fnt
|-status|p2a: Floette|brn
|faint|p2b: Sinistcha
```

### Interpretazione Logica per l'Interfaccia:
1. **`|turn|5`**: L'interfaccia incrementa il contatore del turno. Crea un nodo principale nel `QTreeWidget` intitolato **"Turno 5"**.
2. **`|switch|p1a: Torkoal...`**:
   * *Azione:* Lo slot `p1a` viene aggiornato visivamente mostrando l'icona di **Torkoal** al 100% degli HP.
   * *DB:* Viene inserita una `TurnAction` di tipo `switch`.
3. **`|-weather|SunnyDay...`**:
   * *Stato:* Il clima globale del campo (`MatchState.weather`) diventa **"SunnyDay"**. L'interfaccia mostra un'icona del sole sullo sfondo.
4. **`|move|p1b: Chandelure|Heat Wave...`**:
   * *Azione:* Viene creato un nodo nel widget dell'albero: **"#1 MOVE: Chandelure usa Heat Wave"**.
5. **`|-damage|p2a: Floette|43/100`**:
   * *Sotto-evento:* Aggiorna la `QProgressBar` dell'HP del Pokémon nello slot `p2a` (Floette) portandola al **43%**.
6. **`|-damage|p2b: Sinistcha|0 fnt`** e **`|faint|...`**:
   * *Sotto-evento & Azione:* La barra degli HP di Sinistcha scende a **0%**. Lo slot `p2b` viene segnato come vuoto/faint.
7. **`|-status|p2a: Floette|brn`**:
   * *Sotto-evento:* Accanto all'icona di Floette compare l'etichetta rossa **"BRN"** (Scottatura).
