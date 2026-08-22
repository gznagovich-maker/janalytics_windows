# Guida Completa alla Mappatura dei Tag di Pokémon Showdown per UI VGC

Questa guida mappa in modo dettagliato ogni tag (evento) presente nei replay log di Pokémon Showdown, descrivendo i relativi attributi/campi, fornendo esempi reali tratti dalle tue lottate di test e spiegando come strutturarli ed organizzarli a livello visivo (UI/UX) e logico (Event Sourcing) all'interno del tuo software PySide6.

---

## 1. Architettura Concettuale della UI per gli Eventi

In una schermata avanzata di analisi match (come la tua `ReplayDetailWidget`), un turno non è un blocco statico, ma una sequenza temporale di azioni. Per organizzare al meglio lo schermo, dobbiamo dividere i log di Showdown in due categorie fondamentali di tag:

1. **Eventi Primari (Timeline Nodes)**: Sono le azioni principali che avvengono nel turno (es. `|move|`, `|switch|`, `|cant|`, `|faint|`). Questi devono comparire come nodi o righe principali nell'albero degli eventi (`QTreeWidget`).
2. **Modificatori / Sotto-Eventi (Sub-Items / Detail Modifiers)**: Sono le conseguenze immediate di un'azione (es. `|-damage|`, `|-boost|`, `|-ability|`, `|-status|`). Identificati dal prefisso trattino `-`, nella UI non devono essere visualizzati come azioni separate, ma come **sotto-nodi espandibili** o come **effetti grafici combinati** (es. aggiornamento barra HP, icone di stato o notifiche animate sullo schermo).

---

## 2. Dizionario dei Tag Showdown & Mappatura UI

Di seguito viene analizzato ogni singolo tag del protocollo di Showdown rilevante per il formato Doubles VGC.

### A. Fase di Inizializzazione (Meta-Dati Pre-Match)

Questi tag si trovano in cima al replay e servono a pre-popolare l'interfaccia prima del Turno 1.

#### 1. `|player|` (Allenatori del Match)
* **Campi / Attributi**: `|player|{p1/p2}|{Username}|{Avatar}|{ELO Rating}`
* **Esempio**: `|player|p1|7upikid|lucas-gen4pt|1069`
* **Mappatura UI/UX**: Popola le intestazioni dei due lati del campo (Giocatore 1 a sinistra, Giocatore 2 a destra) con il nome dell'allenatore e l'eventuale rating ELO.
* **Impatto sullo Stato**: Registra i due trainer del match e assegna i rispettivi ID di gioco (`p1` e `p2`).

#### 2. `|poke|` (Team Preview)
* **Campi / Attributi**: `|poke|{p1/p2}|{Specie, Livello, Genere}|` (il genere è opzionale)
* **Esempio**: `|poke|p1|Kangaskhan, L50, F|`
* **Mappatura UI/UX**: Popola la griglia o il box del team (di solito composto da 6 icone/nomi per giocatore in alto o ai lati dello schermo).
* **Impatto sullo Stato**: Inserisce il Pokémon nel team di 6 elementi di quel giocatore. Lo stato iniziale è "non portato" (`is_brought = False`).

#### 3. `|teamsize|` & `|start|` (Inizio del Match)
* **Campi / Attributi**: `|teamsize|{p1/p2}|{Numero di Pokémon portati}` e `|start|`
* **Esempio**: `|teamsize|p1|4`
* **Mappatura UI/UX**: Aggiorna i box dei team oscurando o contrassegnando come non portati (grigi) i 2 Pokémon esclusi (visto che in VGC si portano solo 4 Pokémon su 6). `|start|` abilita la visualizzazione della board e fa partire la timeline dei turni.

---

### B. Eventi Primari del Replay (Nodi Principali UI)

Questi tag costituiscono la timeline sequenziale del match. Ogni volta che si seleziona uno di questi elementi nel `QTreeWidget`, il pannello di ispezione a destra deve mostrare lo stato esatto del campo in quell'istante.

#### 4. `|turn|` (Marcatore del Turno)
* **Campi / Attributi**: `|turn|{Numero Turno}`
* **Esempio**: `|turn|1`
* **Mappatura UI/UX**: Crea il nodo principale dell'albero a comparsa (`Turno 1`, `Turno 2`, ecc.). Può mostrare badge rapidi per condizioni globali attive in quel turno (es. `[Clima: Sole]`, `[Trick Room - Turno 2/5]`).
* **Impatto sullo Stato**: Incrementa il contatore del turno e azzera le condizioni "single-turn" (es. Protect, Fake Out flinch-state).

#### 5. `|switch|` / `|drag|` (Ingresso in Campo)
* **Campi / Attributi**: `|switch|{p1a/p1b/p2a/p2b}: {Nick/Specie}|{Specie, Livello, Genere}|{HP attuale/HP totale}` (gli HP possono contenere anche lo stato, es. `100/100 status`)
* **Esempio**: `|switch|p1a: Kangaskhan|Kangaskhan, L50, F|100/100`
* **Mappatura UI/UX**: Rappresenta visivamente l'ingresso in campo del Pokémon. Nella UI, aggiorna istantaneamente lo slot corrispondente (`P1 Slot A`, ecc.) mostrando il nome del Pokémon, la barra HP piena e l'eventuale icona del genere.
* **Impatto sullo Stato**:
  * Imposta `PokemonBuild.is_brought = True`.
  * Assegna l'ID della build allo slot attivo del campo (es. `active_p1a_id = b.id`).
  * Imposta la percentuale di HP correnti (`current_hp_pct = 100.0`) e lo stato di salute (se presente).

#### 6. `|move|` (Esecuzione Mossa)
* **Campi / Attributi**: `|move|{p1a/p1b/p2a/p2b: NomeAttore}|{Nome Mossa}|{p1a/p1b/p2a/p2b: NomeTarget o vuoto}|[from] {Fonte, es. ability/item}|[of] {PokémonOrigine}`
* **Esempio**: `|move|p1a: Kangaskhan|Fake Out|p2a: Floette`
* **Mappatura UI/UX**: È il nodo d'azione fondamentale. Mostra l'icona del tipo di mossa (es. Normale per Fake Out) e il testo descrittivo: `Kangaskhan usa Fake Out su Floette`. Nel pannello di destra, evidenzia l'attaccante e il bersaglio principale.
* **Impatto sullo Stato**: Traccia l'ordine dell'azione nel database (`action_order`). Registra che la mossa è stata rivelata per quel Pokémon (salvataggio nella tabella `Pokemon_Move`).

#### 7. `|cant|` (Azione Fallita)
* **Campi / Attributi**: `|cant|{p1a/p1b/p2a/p2b: Pokémon}|{Motivo/Condizione}|{Mossa (opzionale)}`
* **Esempio**: `|cant|p2a: Floette|flinch`
* **Mappatura UI/UX**: Rendi questa riga visivamente distinta (ad esempio, colore grigio o icona di sbarramento). Spiega chiaramente perché il Pokémon non ha potuto agire (es. `Floette tentenna per il flinch!`, `Floette è paralizzata e non può muoversi`).
* **Impatto sullo Stato**: Nessun cambio di HP, ma può azzerare lo stato di tentennamento (`flinch`) a fine turno.

#### 8. `|faint|` (Pokémon KO)
* **Campi / Attributi**: `|faint|{p1a/p1b/p2a/p2b: Pokémon}`
* **Esempio**: `|faint|p1b: Starmie`
* **Mappatura UI/UX**: Cambia lo stato dello slot grafico a destra mettendolo in stato "Esausto" (icona grigia o teschio). Rendi rossa la riga nell'albero degli eventi.
* **Impatto sullo Stato**: Imposta `current_hp_pct = 0.0`. Svuota lo slot attivo del campo corrispondente (imposta `active_p1b_id = Null` al completamento delle azioni di pulizia del turno).

---

### C. Sotto-Eventi e Modificatori (Secondari - Prefisso `-`)

Questi tag avvengono sempre all'interno o subito dopo un evento primario. Devono essere raggruppati all'interno dell'azione principale che li ha generati.

#### 9. `|-damage|` (Danno subito)
* **Campi / Attributi**: `|-damage|{Pokémon}|{HP attuale/HP totale o percentuale}|[from] {Fonte (es. brn, weather, Recoil)}`
* **Esempio**: `|-damage|p2a: Floette|81/100` o `|-damage|p2a: Floette|47/100 brn|[from] brn`
* **Mappatura UI/UX**: Aggiorna istantaneamente la barra degli HP (`QProgressBar`) dello slot del Pokémon riducendo la percentuale. Se il danno deriva da uno stato (es. Scottatura `brn`) o dal meteo, mostra una piccola icona di testo accanto alla barra HP.
* **Impatto sullo Stato**: Calcola i danni subiti calcolando la differenza di HP prima e dopo l'evento. Aggiorna `current_hp_pct` sul Pokémon.

#### 10. `|-heal|` (Cura ricevuta)
* **Campi / Attributi**: `|-heal|{Pokémon}|{HP attuale/HP totale}|[from] {Fonte (es. drain, item: Sitrus Berry)}|[of] {PokémonOrigine}`
* **Esempio**: `|-heal|p2b: Sinistcha|89/100|[from] drain|[of] p1b: Starmie`
* **Mappatura UI/UX**: Identico a `-damage`, ma la barra degli HP si riempie ed è colorata di verde/notifica di cura.
* **Impatto sullo Stato**: Aumenta `current_hp_pct` sul Pokémon.

#### 11. `|-boost|` / `|-unboost|` (Variazione Statistiche)
* **Campi / Attributi**: `|-boost|{Pokémon}|{Statistica, es: atk/def/spe/spa/spd/evs/acc}|{Stadi aumentati o diminuiti}|[from] {Fonte}`
* **Esempio**: `|-unboost|p1b: Starmie|atk|1` o `|-boost|p2a: Floette|spa|1`
* **Mappatura UI/UX**: Mostra badge o frecce (blu in su per i boost, arancioni/rosse in giù per gli unboost) accanto ai Pokémon nel pannello dei dettagli. Es. `SpA +1`, `Atk -1`.
* **Impatto sullo Stato**: Modifica i modificatori dinamici (`stat_stages`) del Pokémon (da -6 a +6). Fondamentale per il calcolatore dei danni!

#### 12. `|-ability|` (Attivazione Abilità)
* **Campi / Attributi**: `|-ability|{Pokémon}|{Nome Abilità}|[from] {Fonte}|[of] {PokémonOrigine}`
* **Esempio**: `|-ability|p2b: Incineroar|Intimidate|boost`
* **Mappatura UI/UX**: Mostra un popup rapido o un tooltip interattivo che spiega cosa fa l'abilità (recuperando i dati statici da PokéAPI).
* **Impatto sullo Stato**: Rileva ufficialmente l'abilità del Pokémon (`PokemonBuild.ability = 'Intimidate'`).

#### 13. `|-enditem|` / `|-item|` (Strumenti in Azione)
* **Campi / Attributi**: `|-enditem|{Pokémon}|{Strumento}|[eat]|[from] {Fonte}`
* **Esempio**: `|-enditem|p2a: Incineroar|Sitrus Berry|[eat]`
* **Mappatura UI/UX**: Evidenzia il consumo dello strumento. Aggiorna la build nel visualizzatore del team mettendo lo strumento in trasparenza o sbarrato.
* **Impatto sullo Stato**: Rivela lo strumento del Pokémon (`PokemonBuild.item = 'Sitrus Berry'`) e ne traccia l'uso (il Pokémon non ha più uno strumento attivo per quel match).

#### 14. `|-status|` / `|-curestatus|` (Stati Alterati)
* **Campi / Attributi**: `|-status|{Pokémon}|{Stato: brn/psn/slp/prz/frz}` e `|-curestatus|{Pokémon}|{Stato}`
* **Esempio**: `|-status|p2a: Floette|brn` (Scottatura)
* **Mappatura UI/UX**: Mostra un badge colorato specifico sullo slot del Pokémon in campo (es. un badge viola `PSN` o rosso `BRN`).
* **Impatto sullo Stato**: Modifica la variabile `status` del Pokémon. Se scottato (`brn`), riduce l'Attacco fisico effettivo del 50%; se paralizzato (`prz`), riduce la Velocità del 50% (o 25% a seconda della generazione).

#### 15. `|-weather|` & `|-terrain|` (Meteo e Campi di Gioco)
* **Campi / Attributi**: `|-weather|{Clima o 'none'}|[upkeep]|[from] {Fonte}` e `|-terrain|{Campo o 'none'}|[from] {Fonte}`
* **Esempio**: `|-weather|SunnyDay|[from] ability: Drought|[of] p1a: Torkoal`
* **Mappatura UI/UX**: Cambia lo sfondo grafico della "board" nella UI (es. un gradiente arancione per il Sole, viola per il Campo Psichico) e popola il widget delle condizioni ambientali globali.
* **Impatto sullo Stato**: Aggiorna `MatchState.weather = 'SunnyDay'` o `MatchState.terrain = 'PsychicTerrain'`.

#### 16. `|-start|` / `|-end|` (Inizio e Fine Effetti Singoli/Lato)
* **Campi / Attributi**: `|-start|{Bersaglio/Lato}|{Effetto}|[of] {Origine}`
* **Esempi Chiave VGC**:
  * `|-start|p1: 7upikid|Tailwind` (Ventoincoda lato P1) -> Imposta `tailwind_p1 = True`. Mostra l'icona del vento sul lato P1.
  * `|-fieldstart|move: Trick Room` (Distortozona globale) -> Imposta `trick_room = True`. Mostra l'effetto della stanza deformata.
  * `|-singleturn|p2a: Floette|Protect` (Mossa Protezione) -> Contrassegna Floette come protetta nello slot visivo.
* **Mappatura UI/UX**: Estremamente utile per mostrare i contatori dei turni rimanenti per Tailwind, Trick Room, Reflect, e Screens ai lati dello schermo dell'utente.

#### 17. `|-mega|` / `|-terastallize|` (Meccaniche di Turno Generazionali)
* **Campi / Attributi**: `|-mega|{Pokémon}|{Specie base}|{Pietra Mega}` e `|-terastallize|{Pokémon}|{Tipo Tera}`
* **Esempio**: `|-mega|p1b: Starmie|Starmie|Starminite`
* **Mappatura UI/UX**: Aggiunge un badge brillante `MEGA` o cambia l'icona del tipo del Pokémon in campo con il tipo Tera selezionato.
* **Impatto sullo Stato**: Cambia le statistiche base del Pokémon (es. Megaevoluzione modifica le stat base del Pokédex) o sovrascrive il tipo difensivo (`PokemonBuild.tera_type = 'Fairy'`).

---

## 3. Schema Riassuntivo di Mappatura per l'Interfaccia

Per semplificare l'implementazione del tuo codice PySide6, ecco una tabella riassuntiva che puoi usare come "mappa di programmazione" per capire quali widget e quali campi del database andare ad aggiornare quando leggi un tag:

| Tag Replay | Tipo Evento | Widget UI Principale | Widget UI Dettagli (Destra) | Campi DB Coinvolti (Tabella `Turn_Action` / `Pokemon_Build`) |
| :--- | :--- | :--- | :--- | :--- |
| `|player|` | Inizializzazione | `QLabel` (Nome Allenatore) | Pannello Team Intestazione | `Trainer.id`, `Team.trainer_id` |
| `|poke|` | Inizializzazione | `QTableWidget` / Icone Team | Griglia statiche Pokémon | `Pokemon_Build.species_id` |
| `|switch|` | Primario (Nodo) | `QTreeWidget` (Nodo azione) | Aggiorna Slot Campo (`p1a`, ecc.) | `Turn_Action.active_p1a_id` ... `active_p2b_id` |
| `|move|` | Primario (Nodo) | `QTreeWidget` (Mossa, Tipo) | Esecutore, Bersaglio, Animazione | `Turn_Action.actor_build_id`, `target_build_id` |
| `|cant|` | Primario (Nodo) | `QTreeWidget` (Testo grigio) | Descrizione del blocco di stato | `Turn_Action.details` (es. "flinch", "paralyze") |
| `|faint|` | Primario (Nodo) | `QTreeWidget` (Testo rosso) | Slot in campo -> Vuoto | `Pokemon_Build` (HP = 0) |
| `|-damage|` | Sotto-evento | Sub-item dell'albero | `QProgressBar` (HP %) | `Turn_Action.tags` (es. `{"damage_pct": 19.0}`) |
| `|-boost|` | Sotto-evento | Sub-item dell'albero | Icona stat (es. `Atk +1` blu) | `Turn_Action.tags` (es. `{"stat_boost": {"atk": 1}}`) |
| `|-ability|`| Sotto-evento | Tooltip informativo | Visualizza Abilità nella Build | `Pokemon_Build.ability` |
| `|-enditem|`| Sotto-evento | Icona strumento sbarrata | Contrassegna oggetto come consumato | `Pokemon_Build.item` |
| `|-weather|`| Sotto-evento | Sfondo Board / Widget Stato| Icona Clima attivo con turni | `Turn.weather` |

---

## 4. Algoritmo Consigliato per l'Estrattore (Event Sourcing)

Dato che hai rimosso la tabella degli snapshot storici per risparmiare spazio (Event Sourcing), ecco la logica Python da implementare nella UI quando l'utente clicca su un'azione specifica:

1. **Inizializza lo stato temporaneo**: Clona i dati base immutabili dal database per i 4 Pokémon portati in campo (HP = 100%, boost = 0, nessun clima).
2. **Cicla in ordine cronologico**: Leggi tutte le `Turn_Action` registrate con `action_order` precedente o uguale all'azione selezionata.
3. **Applica i tag JSON**:
   * Se incontri un tag `damage_pct`, sottrai la percentuale dagli HP temporanei.
   * Se incontri un tag `stat_boost`, somma gli stadi temporanei.
   * Se incontri uno `switch`, cambia il Pokémon occupante quello slot temporaneo.
4. **Rendering visivo**: Disegna la schermata con i valori calcolati al volo in questo esatto "frame" della partita. Questo garantirà una UI ultra-reattiva e senza bug di desincronizzazione cronologica!
