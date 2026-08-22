# AI Master Skill: Showdown & PokéAPI Client Developer

Questo file contiene le istruzioni operative, i pattern architetturali e i prompt strutturati per addestrare o guidare un agente AI di coding (come Cursor, GitHub Copilot, ecc.) nell'implementazione ottimale del client di rete per le API di Pokémon Showdown e PokéAPI v2.

---

## 1. Linee Guida Architetturali (Strict Rules)

1. **Non Bloccare la GUI (Threading):** Poiché le chiamate di rete sono bloccanti, l'interrogazione delle API di Showdown e PokéAPI deve avvenire esclusivamente all'interno di un thread di background (`QThread`) gestito tramite segnali e slot in PySide6.
2. **Criterio Fair Use & Caching Locale:** PokéAPI applica regole rigidissime contro il sovraccarico dei propri server. È **obbligatorio** implementare un sistema di caching locale (es. SQLite o file JSON locali) per memorizzare le risposte statiche di Pokémon, mosse, strumenti e abilità dopo la prima richiesta, prevenendo ban permanenti dell'indirizzo IP.
3. **Gestione del Silenzio in Rete (Offline-First):** L'applicazione deve poter caricare i replay già archiviati localmente nel database SQLite anche in assenza di connessione internet.

---

## 2. Implementazione Tecnica: Modelli di Riferimento

### 2.1 Caching Layer e Client PokéAPI (Python)
Ecco la struttura consigliata in Python per gestire le richieste a PokéAPI con cache integrata su SQLite per evitare il sovraccarico:

```python
import os
import sqlite3
import requests

CACHE_DB_PATH = "pokeapi_cache.db"

class PokeAPIClient:
    def __init__(self):
        self.init_cache_db()
        self.base_url = "https://pokeapi.co/api/v2"

    def init_cache_db(self):
        """Inizializza il database locale per la cache delle risposte PokéAPI."""
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                endpoint TEXT,
                resource_key TEXT,
                response_json TEXT,
                PRIMARY KEY (endpoint, resource_key)
            )
        """)
        conn.commit()
        conn.close()

    def get_cached_response(self, endpoint: str, resource_key: str) -> Optional[str]:
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT response_json FROM api_cache WHERE endpoint = ? AND resource_key = ?",
            (endpoint, resource_key.lower())
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def save_to_cache(self, endpoint: str, resource_key: str, data_json: str):
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO api_cache (endpoint, resource_key, response_json) VALUES (?, ?, ?)",
            (endpoint, resource_key.lower(), data_json)
        )
        conn.commit()
        conn.close()

    def fetch_data(self, endpoint: str, resource_key: str) -> dict:
        """Esegue una GET su PokéAPI controllando prima la cache."""
        cached = self.get_cached_response(endpoint, resource_key)
        if cached:
            import json
            return json.loads(cached)

        # Chiamata HTTP
        url = f"{self.base_url}/{endpoint}/{resource_key.lower()}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            import json
            self.save_to_cache(endpoint, resource_key, json.dumps(data))
            return data
            
        response.raise_for_status()
```

### 2.2 Replay Search Client (Showdown)
Ecco come gestire le chiamate di ricerca di Pokémon Showdown supportando la paginazione basata sul timestamp `before`:

```python
import requests
from typing import List, Dict, Any

class ShowdownReplayClient:
    def __init__(self):
        self.search_url = "https://replay.pokemonshowdown.com/search.json"

    def search_replays(self, user: str = "", user2: str = "", format_filter: str = "", before: int = None) -> List[Dict[str, Any]]:
        """
        Cerca i replay su Pokémon Showdown applicando i parametri opzionali.
        Il parametro 'before' gestisce la paginazione.
        """
        params = {}
        if user:
            params["user"] = user
        if user2:
            params["user2"] = user2
        if format_filter:
            params["format"] = format_filter
        if before:
            params["before"] = before

        response = requests.get(self.search_url, params=params)
        if response.status_code == 200:
            # Ritorna una lista di dizionari con i metadati del replay
            return response.json()
        response.raise_for_status()
```

---

## 3. Master Prompt per l'Agente AI di Coding

*Copia e incolla il prompt sottostante all'interno dell'agente AI a cui desideri affidare la scrittura materiale delle classi di rete.*

```text
CONTESTO OPERATIVO:
Stiamo sviluppando un'applicazione PySide6 per l'analisi competitiva di Pokémon VGC. L'applicazione deve importare i dati dal database e dalle API di Pokémon Showdown e PokéAPI v2.
Le nostre tabelle del database SQLAlchemy includono:
- Pokedex (species_id, base_hp, base_atk, base_def, base_spa, base_spd, base_spe)
- Pokemon_Build (team_id, species_id, ability, item, tera_type, ev_hp, iv_hp...)
- Pokemon_Move (build_id, move_name)

OBIETTIVO:
Genera un modulo Python chiamato `network/api_clients.py` che contiene le classi per interrogare le API esterne e un worker asincrono PySide6 (`QThread`) in `network/api_workers.py` per gestire l'interazione con l'interfaccia utente senza bloccare la schermata principale.

REQUISITI DI CODICE:
1. Implementa la classe `PokeAPIClient` con un sistema di caching SQLite locale (`pokeapi_cache.db`). Ogni volta che l'applicazione richiede i dati per un Pokémon, un'abilità, un oggetto o una mossa, la classe deve prima verificare se la risposta JSON è memorizzata nel DB locale. Se esiste, la decodifica e la restituisce. Altrimenti esegue la richiesta HTTP GET, salva il JSON nel database della cache e lo restituisce.
2. Implementa la classe `ShowdownReplayClient` per cercare replay pubblici. Deve supportare la ricerca con filtri combinati per 'user', 'user2' e 'format'. Deve supportare la paginazione tramite il parametro 'before'.
3. Crea un metodo `import_pokemon_to_pokedex(species_name: str)` in `PokeAPIClient` che interroga l'endpoint `/pokemon/{species_name}` e popola la tabella SQLAlchemy `Pokedex` del nostro database locale inserendo le statistiche base del Pokémon (HP, Atk, Def, SpA, SpD, Spe) e i suoi tipi elementali.
4. Implementa il thread di background `ReplaySearchWorker(QThread)` in `network/api_workers.py` che emette un segnale `results_found(list)` con i replay trovati oppure `error_occurred(str)` in caso di eccezioni di rete.

Scrivi codice Python 3.12 modulare, type-hinted, pulito e documentato. Non utilizzare librerie non standard ad eccezione di 'requests' e 'PySide6'.
```
