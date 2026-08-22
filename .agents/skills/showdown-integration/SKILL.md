---
name: showdown-integration
description: >-
  Use this skill when developing the VGC Replay Analyzer, parsing Pokémon Showdown replay logs, interacting with PokéAPI v2, or managing Event Sourcing UI updates in PySide6.
---

# Integrazione API Pokémon Showdown e PokéAPI

Questa skill fornisce le linee guida architetturali e la mappatura degli eventi per l'applicazione VGC Replay Analyzer.

## 1. Linee Guida Architetturali (Rete e UI)

*   **Non Bloccare la GUI:** Le chiamate di rete a Showdown o PokéAPI devono avvenire in background (es. tramite `QThread` in PySide6).
*   **Caching Obbligatorio (PokéAPI):** Le richieste a PokéAPI (es. Pokémon, abilità, strumenti, mosse) devono essere salvate in una cache locale (SQLite, es. `pokeapi_cache.db` o file JSON) al primo fetch per prevenire ban IP.
*   **Paginazione Showdown:** Usa il timestamp dell'ultimo replay (`uploadtime`) come parametro `before` per scorrere le pagine nella ricerca di `search.json`.
*   **Offline-First:** L'app deve poter caricare e analizzare i replay salvati localmente senza richiedere una connessione internet.

## 2. Event Sourcing e Mappatura Tag (Parser & UI)

I log di Showdown seguono un flusso sequenziale per turni. Per il rendering UI (es. `QTreeWidget` e `QProgressBar`):

*   **Inizializzazione:** `|player|`, `|poke|`, `|teamsize|`. Servono per la team preview e assegnazione slot (`p1a`, `p1b`, `p2a`, `p2b`).
*   **Eventi Primari (Nodi Principali):**
    *   `|turn|{numero}`: delimita il turno.
    *   `|switch|` / `|drag|`: ingresso in campo. Associa la build allo slot e resetta HP correnti.
    *   `|move|`: esecuzione attacco. Mostra chi e cosa usa.
    *   `|cant|`: azione fallita per stato (flinch, par, slp).
    *   `|faint|`: KO. HP a 0, slot si svuota.
*   **Sotto-Eventi e Modificatori (Nodi Secondari, prefisso `-`):**
    *   `|-damage|` / `|-heal|`: modifica gli HP correnti e aggiorna la barra visiva.
    *   `|-boost|` / `|-unboost|`: altera i modificatori statistici (es. `Atk +1`).
    *   `|-status|`: applica icone (brn, psn, slp).
    *   `|-weather|` / `|-terrain|` / `|-start|`: modificano l'ambiente globale o del lato (Tailwind, Trick Room, SunnyDay).

### Algoritmo UI (Event Sourcing)
Per mostrare uno stato cronologico esatto al clic di un turno:
1. Clona i dati base immutabili dal database.
2. Cicla cronologicamente tutte le `Turn_Action` precedenti o uguali a quella selezionata.
3. Applica i tag (es. sottrarre `damage_pct`, sommare `stat_boost`).
4. Esegui il rendering visivo del frame.

## 3. Riferimenti Dettagliati

In caso di dubbi specifici su entità, tag o implementazioni, fai riferimento alle guide complete (consultabili in ogni momento):

*   [Guida Entità API Showdown e PokéAPI](file:///c:/Users/Mirco/Documents/Jorkcorp/janalytics_windows/Guide/guida_api_entita_showdown.md)
*   [Mappatura Dettagliata dei Tag UI](file:///c:/Users/Mirco/Documents/Jorkcorp/janalytics_windows/Guide/mappatura_tag_showdown.md)
*   [Guida alle Situazioni di Gioco (Showdown)](file:///c:/Users/Mirco/Documents/Jorkcorp/janalytics_windows/Guide/guida_situazioni_tag_showdown.md)
*   [Istruzioni Operative e Client (Master Prompt)](file:///c:/Users/Mirco/Documents/Jorkcorp/janalytics_windows/Guide/skill_utilizzo_api_showdown.md)
