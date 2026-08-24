---
name: limitless-tcg-api
description: >-
  Knowledge base and reference for the Limitless TCG API specifically for VGC tournaments,
  including details on endpoints for tournaments, standings, pairings, and metagame.
---

# Limitless TCG API - VGC Integration Guide

Questa skill contiene le informazioni chiave sulle API di Limitless TCG (documentazione: https://docs.limitlesstcg.com/developer.html) per quanto riguarda il gioco organizzato VGC (Video Game Championships).

L'obiettivo è fornire all'agente il contesto necessario per interagire con queste API al fine di recuperare risultati, teamlist, archetipi e statistiche sui tornei.

## Informazioni Estraibili dai Tornei VGC

### 1. Elenco e Dettagli dei Tornei (`/tournaments` e `/tournaments/{id}/details`)
- **Filtri Base:** Ricerca di tornei per `game=VGC`, formato o organizzatore.
- **Informazioni Evento:** ID, nome, data, partecipanti, tipo di evento (online/live) e piattaforma (es. Switch).
- **Struttura:** Fasi del torneo (Svizzera, Top Cut), numero di round, e formati (BO1/BO3/BO5).
- **Regole:** Presenza di open teamsheets e regole speciali o ban list imposte dall'organizzatore.

### 2. Risultati e Giocatori (`/tournaments/{id}/standings`)
Questo endpoint è il cuore delle analisi statistiche:
- **Piazzamenti:** Classifica, nazione, e record di V-P-S dei giocatori.
- **Teamlist:** Tramite l'oggetto `decklist`, è possibile ricavare l'esatta composizione del team (Pokémon, mosse, abilità, strumenti).
- **Metagame / Archetipi:** Tramite l'oggetto `deck`, il sistema assegna un archetipo (ID, nome composizione e icone dei Pokémon core) al team, essenziale per l'analisi del metagame.
- **Drops:** Identificazione del round in cui un giocatore si è ritirato.

### 3. Match e Incontri (`/tournaments/{id}/pairings`)
Fornisce lo storico completo degli incontri (matchups) del torneo:
- **Identificazione:** Fase e round dell'incontro.
- **Risultato:** Giocatori coinvolti ed esito della partita (vincitore, tie, bye, no-show).

### 4. Categorizzazione Metagame (`/games` e `/games/{id}/decks`)
- **Regole di Archetipo:** Permette di interrogare come Limitless assegna automaticamente un team a un certo archetipo, tramite i requisiti di Pokémon specifici.

### 5. Webhooks in Tempo Reale
- È supportato un webhook (`tournament:ended`) che notifica la conclusione di un evento tramite POST request, molto utile per evitare il polling continuo sulle API e aggiornare automaticamente un database locale o i rating Elo dei giocatori.
