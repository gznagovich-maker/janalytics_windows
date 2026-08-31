---
name: smogon-damage-calc-python
description: Skill per agenti Antigravity per integrare e automatizzare i calcoli di danno di Pokémon Smogon in Python usando il DB SQLite interno di Janalytics.
---

# Smogon Damage Calculator Skill per Antigravity (Python & Node.js Bridge)

## 1. Architettura e Principi Generali
Il calcolatore ufficiale di Smogon (`@smogon/calc`) è sviluppato in **TypeScript** ed è il gold standard per i calcoli di danno nel competitivo Pokémon (Gen 1-9, VGC e Singles). 

Per utilizzare il calcolatore all'interno dell'ecosistema **Janalytics** con Python:
1. **Bridge Node.js + Python**: Un wrapper Python invoca uno script Node.js (`calc_bridge.js`) tramite `subprocess`, sfruttando l'engine nativo di Smogon.
2. **Integrazione col Database Interno SQLite**: **Tutti i dati** (statistiche base di Pokémon, mosse, tipi, abilità e strumenti) vengono attinti direttamente dal **database SQLite interno di Janalytics**. Dipendenze da file JSON esterni (come `pokedex.json` o `moves.json`) sono totalmente eliminate.

---

## 2. Configurazione dell'Ambiente

### Prerequisiti
1. **Node.js** con il pacchetto ufficiale Smogon:
   ```bash
   npm install @smogon/calc
   ```
2. **Python 3.10+** (utilizzando `sqlite3`, `dataclass`, `subprocess` e `json`).

---

## 3. Node.js Bridge (`calc_bridge.js`)

Crea il file `calc_bridge.js` nella root del progetto o nella cartella degli agenzi/tools:

```javascript
// calc_bridge.js
const { calculate, Pokemon, Move, Field } = require('@smogon/calc');

function runCalculation(input) {
  const gen = input.gen || 9;
  
  // Costruzione oggetti Smogon
  const attacker = new Pokemon(gen, input.attacker.name, input.attacker.options || {});
  const defender = new Pokemon(gen, input.defender.name, input.defender.options || {});
  const move = new Move(gen, input.move.name, input.move.options || {});
  const field = new Field(input.field || {});

  const result = calculate(gen, attacker, defender, move, field);

  return {
    damage: result.damage,
    minDamage: Array.isArray(result.damage) ? result.damage[0] : result.damage,
    maxDamage: Array.isArray(result.damage) ? result.damage[result.damage.length - 1] : result.damage,
    koChance: result.kochance ? result.kochance().text : null,
    description: result.desc()
  };
}

// Interfaccia I/O via Stdin/Stdout per Python
let rawData = '';
process.stdin.on('data', chunk => { rawData += chunk; });
process.stdin.on('end', () => {
  try {
    const input = JSON.parse(rawData);
    const output = runCalculation(input);
    console.log(JSON.stringify(output));
  } catch (err) {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
  }
});
```

---

## 4. Wrapper Python Tipizzato & Integrazione DB (`smogon_calc.py`)

Questo modulo Python definisce le data class per configurare gli attacchi e fornisce l'integrazione nativa con il **database SQLite interno** per caricare le info di Pokémon e Mosse.

```python
import json
import sqlite3
import subprocess
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict

@dataclass
class PokemonOptions:
    level: int = 50  # Standard VGC
    item: Optional[str] = None
    ability: Optional[str] = None
    nature: Optional[str] = None
    evs: Optional[Dict[str, int]] = None  # es. {"hp": 252, "atk": 0, "def": 4, "spa": 0, "spd": 0, "spe": 252}
    ivs: Optional[Dict[str, int]] = None  # es. {"hp": 31, "atk": 31, ...}
    boosts: Optional[Dict[str, int]] = None  # es. {"atk": 1, "spa": -1}
    teraType: Optional[str] = None  # es. "Fairy", "Water", "Stellar"
    isStellar: bool = False

@dataclass
class MoveOptions:
    useZ: bool = False
    isMax: bool = False
    isCrit: bool = False
    hits: int = 1
    overriddenBP: Optional[int] = None

@dataclass
class FieldOptions:
    gameType: str = "Doubles"  # "Singles" o "Doubles"
    weather: Optional[str] = None  # "Sun", "Rain", "Sand", "Snow"
    terrain: Optional[str] = None  # "Electric", "Grassy", "Psychic", "Misty"
    isReflect: bool = False
    isLightScreen: bool = False
    isAuroraVeil: bool = False
    # Abilità Ruin Gen 9
    isTabletsOfRuin: bool = False
    isSwordOfRuin: bool = False
    isVesselOfRuin: bool = False
    isBeadsOfRuin: bool = False
    # Modificatori di supporto Doubles
    isHelpingHand: bool = False
    isFriendGuard: bool = False

class SmogonDamageCalc:
    def __init__(self, bridge_path: str = "calc_bridge.js", db_path: Optional[str] = "janalytics.db"):
        self.bridge_path = bridge_path
        self.db_path = db_path

    def fetch_pokemon_from_db(self, pokemon_name: str) -> Dict[str, Any]:
        """Recupera i dati base del Pokémon dal DB interno SQLite."""
        if not self.db_path:
            return {}
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM pokemon WHERE name = ? OR identifier = ?", (pokemon_name, pokemon_name.lower()))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return {}

    def calculate(
        self,
        attacker_name: str,
        defender_name: str,
        move_name: str,
        attacker_opts: Optional[PokemonOptions] = None,
        defender_opts: Optional[PokemonOptions] = None,
        move_opts: Optional[MoveOptions] = None,
        field_opts: Optional[FieldOptions] = None,
        gen: int = 9
    ) -> Dict[str, Any]:
        """Esegue il calcolo del danno invocando il bridge Node.js."""
        
        payload = {
            "gen": gen,
            "attacker": {
                "name": attacker_name,
                "options": asdict(attacker_opts) if attacker_opts else {}
            },
            "defender": {
                "name": defender_name,
                "options": asdict(defender_opts) if defender_opts else {}
            },
            "move": {
                "name": move_name,
                "options": asdict(move_opts) if move_opts else {}
            },
            "field": asdict(field_opts) if field_opts else {}
        }

        # Esecuzione del subprocess Node.js
        proc = subprocess.Popen(
            ["node", self.bridge_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = proc.communicate(input=json.dumps(payload))

        if proc.returncode != 0:
            raise RuntimeError(f"Errore durante l'esecuzione del calcolatore: {stderr}")

        return json.loads(stdout)
```

---

## 5. Guida Completa all'Utilizzo del Calcolatore

Per sfruttare al massimo il calcolatore di Smogon tramite Python, è fondamentale comprendere come vengono modellate le meccaniche di gioco e quali parametri passare.

### A. Condizioni di Campo e Formato VGC (`FieldOptions`)
* **Riduzione Danno ad Area**: Impostando `gameType: "Doubles"`, il calcolatore riduce automaticamente del 25% il danno di mosse multi-target (es. *Dazzling Gleam*, *Rock Slide*, *Make It Rain*, *Astral Barrage*).
* **Meteo & Terreni**:
  * `weather: "Sun"` aumenta il danno di mosse Fuoco (1.5x) e riduce quelle Acqua (0.5x), oltre ad attivare *Protosynthesis* o *Solar Power*.
  * `terrain: "Electric"` aumenta del 30% il danno Elettro sui Pokémon a terra e attiva *Quark Drive*.
  * `terrain: "Grassy"` aumenta del 30% le mosse Erba e dimezza il danno di *Earthquake* / *Bulldoze*.
* **Abilità Ruin (Gen 9)**:
  * `isTabletsOfRuin`: Riduce l'Attacco di tutti gli altri Pokémon del 25%.
  * `isSwordOfRuin`: Riduce la Difesa di tutti gli altri Pokémon del 25%.
  * `isVesselOfRuin`: Riduce l'Attacco Speciale di tutti gli altri Pokémon del 25%.
  * `isBeadsOfRuin`: Riduce la Difesa Speciale di tutti gli altri Pokémon del 25%.

### B. Teracristallizzazione e Modificatori Attaccante/Difensore
* **Tera Standard**: Impostando `teraType: "Fairy"` su un Pokémon non-Fairy, il Pokémon acquisisce la STAB Fairy (1.5x) e perde i suoi tipi originali per le difese. Se ha già il tipo Fairy, la STAB diventa 2.0x.
* **Tera Stellar**: Impostare `teraType: "Stellar"`. Boost del 20% su tutte le mosse non-STAB (1 sola volta per tipo mossa in VGC) e STAB potenziata sui tipi nativi.

### C. Calcolo dei Range di Danno e KO Chance
L'output restituisce:
* `damage`: Un array di 16 valori interi relativi ai 16 possibili roll casuali di danno (da 0.85 a 1.00).
* `minDamage` e `maxDamage`: I valori estremi del roll.
* `koChance`: Una stringa formattata prodotta da Smogon (es. `"62.5% chance to 2HKO"`, `"guaranteed 1HKO"`).

---

## 6. Ricette di Codice Avanzate per Antigravity

### Ricetta 1: Benchmark Difensivo per Spread EV (Survive Calculator)
Trova l'investimento minimo di EV in HP e Difesa Speciale per garantire la sopravvivenza al 100% contro una minaccia specifica del meta:

```python
def optimize_defensive_evs(
    calc: SmogonDamageCalc,
    defender_name: str,
    attacker_name: str,
    move_name: str,
    attacker_item: str = "Choice Specs",
    attacker_nature: str = "Modest"
) -> Dict[str, int]:
    """
    Trova la combinazione minima di EV (HP / SpD) per sopravvivere a un attacco specifico.
    """
    for ev_hp in range(0, 253, 4):
        for ev_spd in range(0, 253, 4):
            # Calcolo HP totali a Lvl 50 per benchmark esatto
            # Assumendo base HP stimati dal DB o generici
            res = calc.calculate(
                attacker_name=attacker_name,
                defender_name=defender_name,
                move_name=move_name,
                attacker_opts=PokemonOptions(
                    evs={"spa": 252, "spe": 252},
                    nature=attacker_nature,
                    item=attacker_item
                ),
                defender_opts=PokemonOptions(
                    evs={"hp": ev_hp, "spd": ev_spd},
                    nature="Calm"
                ),
                field_opts=FieldOptions(gameType="Doubles")
            )
            
            # Se persino il Max Damage roll non manda in KO il difensore
            if "guaranteed 1HKO" not in res.get("koChance", "") and "100% chance to OHKO" not in res.get("koChance", ""):
                if res.get("maxDamage", 999) < (150 + ev_hp // 8):  # Esempio soglia HP
                    return {"hp": ev_hp, "spd": ev_spd, "ko_chance": res.get("koChance")}
                    
    return {"hp": 252, "spd": 252, "status": "Requires Tera or Screens"}
```

### Ricetta 2: Benchmark Offensivo (Offensive EV Threshold)
Determina i minimi EV in Attacco Speciale/Fisico necessari per ottenere un OHKO/2HKO garantito su una spread standard del meta:

```python
def find_minimum_offense_evs(
    calc: SmogonDamageCalc,
    attacker_name: str,
    defender_name: str,
    move_name: str,
    target_evs: Dict[str, int] = {"hp": 252, "spd": 4}
) -> int:
    """
    Trova la SpA/Atk minima per un 1HKO o 2HKO.
    """
    for spa_ev in range(0, 253, 4):
        res = calc.calculate(
            attacker_name=attacker_name,
            defender_name=defender_name,
            move_name=move_name,
            attacker_opts=PokemonOptions(evs={"spa": spa_ev}, nature="Modest"),
            defender_opts=PokemonOptions(evs=target_evs),
            field_opts=FieldOptions(gameType="Doubles")
        )
        if "guaranteed 1HKO" in res.get("koChance", ""):
            return spa_ev
            
    return 252  # Ritorna il massimo se non si raggiunge l'OHKO
```

### Ricetta 3: Integrazione Nativa col Database SQLite di Janalytics
Integrazione completa per estrarre il team dal DB SQLite e lanciare i calcoli:

```python
def analyze_matchup_from_db(db_path: str, my_pokemon: str, opponent_pokemon: str, move_used: str):
    calc = SmogonDamageCalc(db_path=db_path)
    
    # 1. Recupero dati nativi da DB SQLite
    my_data = calc.fetch_pokemon_from_db(my_pokemon)
    opp_data = calc.fetch_pokemon_from_db(opponent_pokemon)
    
    # 2. Esecuzione calcolo con i nomi validati dal DB
    result = calc.calculate(
        attacker_name=my_data.get("name", my_pokemon),
        defender_name=opp_data.get("name", opponent_pokemon),
        move_name=move_used,
        attacker_opts=PokemonOptions(evs={"atk": 252}, nature="Adamant"),
        defender_opts=PokemonOptions(evs={"hp": 252, "def": 4}),
        field_opts=FieldOptions(gameType="Doubles")
    )
    
    return result["description"], result["koChance"]
```

---

## 7. Troubleshooting e Checklist per l'Agente
1. **Nomenclatura Smogon**: Assicurarsi di usare le stringhe formattate come attese da `@smogon/calc`:
   * Forma di Urshifu: `Urshifu-Rapid-Strike` o `Urshifu` (Single Strike).
   * Ogerpon: `Ogerpon-Hearthflame`, `Ogerpon-Wellspring`, `Ogerpon-Cornerstone`.
   * Forme Regionali: `Ninetales-Alola`, `Arcanine-Hisui`.
   * Tesori delle Rovine: `Chien-Pao`, `Chi-Yu`, `Ting-Lu`, `Wo-Chien`.
2. **Standard VGC Lvl 50**: Ricordarsi di mantenere `level: 50` in `PokemonOptions` per tutte le simulazioni VGC.
3. **Rolls di Danno**: L'array `damage` contiene sempre 16 numeri interi in ordine crescente. Per calcolare percentuali esatte, dividere ogni valore per gli HP totali del difensore a livello 50.
