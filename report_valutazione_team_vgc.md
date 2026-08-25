# Report Architetturale: Estrazione e Archiviazione degli Effetti per la Valutazione del Team (VGC)

## 1. Introduzione e Fattibilità

Sì, è assolutamente possibile determinare in maniera univoca gli effetti di mosse, strumenti e abilità tramite tag strutturati. 
Mentre **PokéAPI** fornisce eccellenti dati descrittivi e di classificazione, **Pokémon Showdown** è la risorsa definitiva per la logica competitiva. I file dati di Showdown (`moves.ts`, `abilities.ts`, `items.ts`) contengono nativamente sistemi di **flags** (tag) progettati per far funzionare il simulatore di battaglia. Sfruttare questi dati è il metodo raccomandato per alimentare un motore di valutazione di composizione del team (Team Evaluation) all'interno del VGC Replay Analyzer.

---

## 2. Identificare ed Estrarre gli Effetti (I Tag Nativi)

### 2.1 Approccio tramite Pokémon Showdown (Raccomandato)
I dati di Showdown strutturano gli effetti meccanici in dictionary e proprietà direttamente parsabili.

**Per le Mosse (`data/moves.ts`):**
*   **Oggetto `flags`:** Identifica interazioni meccaniche binarie e univoche. Esempi:
    *   `contact: 1` -> La mossa fa contatto (attiva Rocky Helmet, Rough Skin).
    *   `protect: 1` -> La mossa è bloccabile da Protezione/Individua.
    *   `sound: 1` -> La mossa è sonora (bypassa Sostituto, counterabile da Soundproof).
    *   `punch: 1` -> La mossa è potenziata dall'abilità Iron Fist.
    *   `bullet: 1` -> La mossa è bloccata da Bulletproof.
*   **Oggetto `secondary`:** Definisce gli effetti collaterali, come probabilità di calo statistiche o alterazioni di stato.
    *   Esempio: `{chance: 10, status: 'frz'}` (Geloraggio, 10% probabilità di congelare).
*   **Proprietà `target`:** Definisce il raggio d'azione.
    *   Esempi: `allAdjacentFoes` (danno spread come Rock Slide), `any` (bersaglio singolo, selezionabile ovunque), `self` (setup personale come Swords Dance).

**Per le Abilità (`data/abilities.ts`) e Strumenti (`data/items.ts`):**
In Showdown queste logiche sono gestite tramite callback JavaScript (`onModifyAtk`, `onStart`, ecc.). È consigliabile eseguire un processo di **ETL manuale o basato su regole** per assegnare a queste entità dei tag standardizzati nel tuo database, come ad esempio `weather_setter`, `intimidate_clone`, o `stat_immunity`.

### 2.2 Approccio tramite PokéAPI (Ibrido)
PokéAPI espone per ogni mossa l'oggetto `meta`, utile per raggruppamenti logici generici ma meno granulare di Showdown.
*   `category.name`: Distingue mosse in base al ruolo (`damage`, `ailment`, `heal`, `force-switch`).
*   `ailment.name`: Identifica lo stato inflitto (es. `paralysis`).
*   `stat_chance` / `healing` / `drain`: Valori per calcoli matematici di recupero e danno.

**Conclusione sull'Estrazione:** Utilizza uno script Python/Node per estrarre la chiave `flags` dalle mosse di Showdown e converti quelle chiavi in veri e propri Tag relazionali per la tua architettura.

---

## 3. Store Intelligente nel Database (Architettura Relazionale)

Per sviluppare una feature di **Team Composition Evaluation** scalabile in PySide6, il database (es. SQLite) deve permettere incroci rapidi tra entità e tag. 
L'approccio raccomandato è un **Modello Relazionale a Molti-a-Molti (Many-to-Many)**.

### Struttura delle Tabelle Proposta
1.  **Tabella `Tags` (Dizionario Master)**
    Questa tabella definisce tutti i concetti e le categorie del metagame.
    *   `id` (PK, Integer)
    *   `name` (String: "contact", "sound", "speed_control", "weather_rain")
    *   `category` (String: "mechanic", "utility", "offensive", "defensive")

2.  **Tabella `Moves` (Base)**
    *   `id` (PK), `name`, `type`, `base_power`, `category` (Special/Physical/Status).

3.  **Tabella `Move_Tags` (Join Table)**
    Collega una mossa a uno o più tag.
    *   `move_id` (FK verso Moves)
    *   `tag_id` (FK verso Tags)
    *   *Opzionale:* `value` (Float, utile per salvare intensità o probabilità, es. chance = 30 per un drop statistiche).

4.  *Stesso principio applicabile per `Item_Tags` e `Ability_Tags`.*

### Inserimento Intelligente (Logica di Popolamento)
Durante la fase di setup del DB, converti la logica strutturata in record DB:
*   *Se in Showdown `flags.sound == 1` -> `INSERT INTO Move_Tags (move_id, tag_sound_id)`*
*   *Se in Showdown `target == 'allAdjacentFoes'` -> `INSERT INTO Move_Tags (move_id, tag_spread_id)`*
*   *Regola Custom*: Se mossa IN ('Tailwind', 'Icy Wind', 'Electroweb', 'Trick Room') -> Associa il tag `speed_control`.

---

## 4. Implementazione Pratica: Valutazione Composizione Team

Una volta che il database mappa ogni mossa/strumento/abilità ai suoi tag, il motore di valutazione agisce come un **Rules Engine** analizzando il pool di mosse e abilità scelte per il team (max 24 mosse, 6 abilità).

### Calcolo del "Team Coverage Score" (Logica Applicativa)
1.  **Estrazione del Profilo Team:**
    Esegui una query SQL per recuperare tutti i tag unici (e il loro conteggio) presenti nel team analizzato.
    ```sql
    SELECT t.name, COUNT(t.name) 
    FROM Tags t 
    JOIN Move_Tags mt ON t.id = mt.tag_id 
    WHERE mt.move_id IN (?, ?, ...)
    GROUP BY t.name;
    ```

2.  **Regole di Valutazione e Sinergia (Esempi in Python/PySide6):**
    *   **Controllo Speed Control:**
        ```python
        if 'speed_control' not in team_tags:
            add_alert("Warning", "Il team non possiede metodi di manipolazione della velocità (Tailwind, Icy Wind).")
        ```
    *   **Gestione Protect/Stall:**
        ```python
        if 'bypass_protect' not in team_tags (Feint, Unseen Fist):
            add_alert("Tip", "Considera l'inserimento di danni chip o mosse per spezzare le protezioni.")
        ```
    *   **Analisi Anti-Sinergie (Fuoco Amico):**
        ```python
        if 'spread_ground' in team_tags (Earthquake):
            if not any(ally_has_tag('immunity_ground')):
                add_alert("Danger", "Il team subisce danni ingenti dal proprio Terremoto. Inserire Pokémon Volanti o con Levitazione.")
        ```
    *   **Combo Danni Meteo:**
        ```python
        if 'weather_rain_setter' in team_tags and 'rain_abuser' in team_tags (Swift Swim):
            add_alert("Synergy", "Sinergia Pioggia trovata.")
        ```

### Integrazione in PySide6
Nel tuo applicativo VGC Replay Analyzer, questa feature si traduce in una view elegante (es. `QDockWidget` o Tab separato) che mostra un `QRadarChart` per visualizzare il bilanciamento Offensivo, Difensivo e Utility, e una lista (o card view) degli avvisi (Warning, Tips, Synergy) calcolati dalle regole sopra indicate.
