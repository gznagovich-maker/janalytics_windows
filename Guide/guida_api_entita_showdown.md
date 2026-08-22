# Guida Completa alle API di Pokémon Showdown e PokéAPI v2

Questo documento è stato progettato per fornire a un agente di intelligenza artificiale (AI) tutto il contesto necessario per comprendere, interrogare e integrare i servizi esterni di **Pokémon Showdown** e **PokéAPI v2** all'interno dell'applicazione VGC Replay Analyzer.

---

## 1. Pokémon Showdown: Web APIs e Replay

Pokémon Showdown espone le sue API web principalmente restituendo dati in formato **JSON**. La convenzione generale del simulatore è semplice: aggiungendo `.json` o `.log` in coda all'URL di qualsiasi risorsa pubblica si ottiene la rappresentazione strutturata dei dati.

### 1.1 Download di un Replay Singolo
Per scaricare e analizzare i replay, Showdown offre due formati:
* **Log Grezzo (Raw Log):** Fornisce la cronologia sequenziale del match con tutti i tag nativi dei turni e delle azioni (es. `|move|`, `|switch|`, `|-damage|`).
  * **URL:** `https://replay.pokemonshowdown.com/{replay_id}.log`
* **File JSON:** Contiene i metadati completi del replay, inclusi la data, i giocatori, il formato, il log testuale incorporato e l'input log (se disponibile).
  * **URL:** `https://replay.pokemonshowdown.com/{replay_id}.json`

### 1.2 Ricerca e Filtro dei Replay
L'endpoint di ricerca e scouting dei replay è:
* **Base URL:** `https://replay.pokemonshowdown.com/search.json`

I replay possono essere filtrati in modo estremamente preciso tramite parametri in query string (GET):

* **Filtro per Utente Singolo:** Cerca tutti i replay giocati da un determinato allenatore.
  * **Parametro:** `user` (es. `?user=7upikid`)
* **Filtro per Coppia di Utenti:** Cerca i replay in cui si sono scontrati due specifici allenatori. Utilissimo per tracciare storici di rivalità o partite di tornei.
  * **Parametri:** `user` e `user2` (es. `?user=7upikid&user2=jirkunow`)
* **Filtro per Formato (Tier VGC):** Filtra i replay per formato competitivo.
  * **Parametro:** `format` (es. `?format=gen9vgc2026regma`)
* **Combinazione di Filtri:** È possibile combinare liberamente utenti e formato per raffinare la ricerca.
  * **Esempio:** `https://replay.pokemonshowdown.com/search.json?user=zarel&user2=yuyuko&format=gen7randombattle`

### 1.3 Paginazione delle Ricerche
* **Limite di Risultati:** Ogni richiesta di ricerca restituisce un massimo di **51 risultati** in formato JSON.
* **Logica di Offset:** Se l'API restituisce esattamente 51 risultati, significa che esiste almeno un'altra pagina di replay disponibili.
* **Filtro Temporale (`before`):** Per scorrere le pagine (paginazione), Showdown utilizza un approccio basato sul timestamp dell'ultimo replay visualizzato, invece di un classico parametro di offset a pagine numeriche.
  * **Parametro:** `before` (es. `?user=zarel&before=1372221987`)
  * **Valore da usare:** Il valore del campo `uploadtime` dell'ultimo replay dell'elenco appena ricevuto.

---

## 2. PokéAPI v2: Importazione e Mappatura delle Entità

La PokéAPI v2 è un'API RESTful di sola consultazione (GET) che non richiede autenticazione. Fornisce l'intera banca dati di Pokémon, abilità, strumenti e mosse.

Di seguito è riportata la mappatura esatta delle entità e degli attributi utili ai fini dello sviluppo del VGC Replay Analyzer, formattata per l'assimilazione immediata da parte di un agente di programmazione AI.

### 2.1 Entità: Pokémon (Specie e Varietà)
Rappresenta i dati biologici e le statistiche di base immutabili di ogni Pokémon. Nel database relazionale, questa entità popola la tabella `Pokedex`.
* **Descrizione:** Contiene le statistiche base, i tipi elementali e i riferimenti alle abilità disponibili per ogni specie o forma alternativa.
* **Endpoint API:** `https://pokeapi.co/api/v2/pokemon/{id_or_name}/`
* **Attributi Mappati:**
  - `id`: Identificativo numerico intero univoco della specie/varietà nel database di PokéAPI.
  - `name`: Nome in stringa minuscola del Pokémon (es. `incineroar`, `urshifu-rapid-strike`).
  - `types`: Lista di oggetti che definiscono i tipi elementali del Pokémon (es. `fire`, `dark`) e il rispettivo slot d'ordine.
  - `stats`: Lista contenente i valori delle statistiche base di combattimento (`base_stat`) associati alle relative statistiche: `hp`, `attack`, `defense`, `special-attack`, `special-defense`, `speed`.
  - `abilities`: Elenco delle abilità che il Pokémon può possedere, con l'indicazione se si tratta di un'abilità nascosta (`is_hidden`) e il suo slot (1, 2 o 3).
  - `sprites`: Dizionario di URL che ospitano gli sprite grafici ufficiali (es. `front_default` per il rendering in battaglia).
  - `species`: Riferimento alla risorsa `PokemonSpecies` per identificare le relazioni parentali di evoluzione e le forme alternative che condividono lo stesso ID Pokédex nazionale.

### 2.2 Entità: Ability (Abilità)
Definisce l'effetto passivo associato a un Pokémon durante l'incontro (es. *Intimidate*, *Drought*).
* **Descrizione:** Fornisce i metadati descrittivi e le regole di attivazione in battaglia delle abilità dei Pokémon.
* **Endpoint API:** `https://pokeapi.co/api/v2/ability/{id_or_name}/`
* **Attributi Mappati:**
  - `id`: Identificativo numerico intero dell'abilità.
  - `name`: Nome identificativo in formato stringa minuscola (es. `intimidate`).
  - `names`: Lista di traduzioni localizzate del nome dell'abilità in diverse lingue (utilizzato per recuperare il nome italiano, es. "Prepotenza").
  - `effect_entries`: Descrizione dell'effetto dell'abilità sul campo di battaglia in diverse lingue (solitamente si estrae la descrizione sintetica `short_effect` in lingua inglese).
  - `pokemon`: Elenco dei Pokémon che possono possedere questa abilità, suddivisi per slot e potenziale di abilità nascosta.

### 2.3 Entità: Item (Strumento)
Rappresenta gli strumenti assegnabili ai Pokémon in battaglia (es. *Sitrus Berry*, *Choice Specs*).
* **Descrizione:** Fornisce dati sugli strumenti, i loro effetti attivi/passivi e la pocket d'appartenenza nella borsa.
* **Endpoint API:** `https://pokeapi.co/api/v2/item/{id_or_name}/`
* **Attributi Mappati:**
  - `id`: Identificativo numerico intero dello strumento.
  - `name`: Nome univoco in stringa minuscola (es. `sitrus-berry`).
  - `names`: Traduzioni localizzate del nome dello strumento in diverse lingue (es. "Baccasitrus" in italiano).
  - `effect_entries`: Spiegazione testuale dell'effetto dello strumento quando consumato o tenuto in battaglia.
  - `sprites`: URL dello sprite bidimensionale dell'icona dell'oggetto (`default` per l'icona PNG).
  - `attributes`: Elenco di caratteristiche dello strumento (es. `holdable` per verificare se è assegnabile a un Pokémon, o `consumable`).

### 2.4 Entità: Move (Mossa)
Mappa le caratteristiche di ogni attacco o mossa di stato utilizzabile dai Pokémon durante un incontro.
* **Descrizione:** Definisce i parametri offensivi, difensivi e tattici delle mosse. Nel database relazionale, questi dati vengono utilizzati per convalidare le mosse associate alla tabella `Pokemon_Move`.
* **Endpoint API:** `https://pokeapi.co/api/v2/move/{id_or_name}/`
* **Attributi Mappati:**
  - `id`: Identificativo numerico intero della mossa.
  - `name`: Nome univoco in stringa minuscola (es. `matcha-gotcha`).
  - `names`: Traduzioni localizzate del nome della mossa (es. "Tè Matcha" in italiano).
  - `power`: Potenza base dell'attacco (espresso come valore intero; impostato a `0` o `null` per mosse di stato).
  - `accuracy`: Percentuale di precisione della mossa (es. `90` per il 90% di precisione; impostato a `null` per mosse infallibili come *Swift* o *Rage Powder*).
  - `pp`: Punti Potenza di base utilizzabili.
  - `priority`: Valore di priorità della mossa compreso tra `-8` e `8` (es. `1` per *Fake Out*, `0` per attacchi standard, `-7` per *Trick Room*).
  - `type`: Tipo elementale della mossa (es. `grass`, `fire`).
  - `damage_class`: Classe di danno della mossa, categorizzata come `physical`, `special` o `status`.
  - `effect_entries`: Descrizione dell'effetto della mossa, con indicazione degli effetti secondari e delle percentuali di attivazione (`effect_chance`).
  - `meta`: Oggetto contenente metadati avanzati sulla mossa, inclusi i turni minimi/massimi d'effetto, la percentuale di assorbimento della salute (`drain`), o le probabilità di infliggere stati alterati (`ailment_chance`).
