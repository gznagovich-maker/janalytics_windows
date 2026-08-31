import json
import sqlite3
import subprocess
import os
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict

@dataclass
class PokemonOptions:
    level: int = 50
    item: Optional[str] = None
    ability: Optional[str] = None
    nature: Optional[str] = None
    evs: Optional[Dict[str, int]] = None
    ivs: Optional[Dict[str, int]] = None
    boosts: Optional[Dict[str, int]] = None
    teraType: Optional[str] = None
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
    gameType: str = "Doubles"
    weather: Optional[str] = None
    terrain: Optional[str] = None
    isReflect: bool = False
    isLightScreen: bool = False
    isAuroraVeil: bool = False
    isTabletsOfRuin: bool = False
    isSwordOfRuin: bool = False
    isVesselOfRuin: bool = False
    isBeadsOfRuin: bool = False
    isHelpingHand: bool = False
    isFriendGuard: bool = False

class SmogonDamageCalc:
    def __init__(self, bridge_path: str = "calc_bridge.js", db_path: Optional[str] = "janalytics.db"):
        self.bridge_path = bridge_path
        self.db_path = db_path
        
        if not os.path.isabs(self.bridge_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.bridge_path = os.path.join(base_dir, self.bridge_path)

        if self.db_path and not os.path.isabs(self.db_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(base_dir, self.db_path)

    def fetch_pokemon_from_db(self, pokemon_name: str) -> Dict[str, Any]:
        """Recupera i dati base del Pokémon dal DB interno SQLite."""
        if not self.db_path or not os.path.exists(self.db_path):
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
        payload = self._build_payload(
            gen, attacker_name, defender_name, move_name,
            attacker_opts, defender_opts, move_opts, field_opts
        )
        return self._run_node_process(payload)
        
    def calculate_batch(self, calculations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Esegue un batch di calcoli per ottimizzare l'invocazione di Node.js."""
        if not calculations:
            return []
            
        payloads = []
        for calc_req in calculations:
            payload = self._build_payload(
                calc_req.get("gen", 9),
                calc_req["attacker_name"],
                calc_req["defender_name"],
                calc_req["move_name"],
                calc_req.get("attacker_opts"),
                calc_req.get("defender_opts"),
                calc_req.get("move_opts"),
                calc_req.get("field_opts")
            )
            payloads.append(payload)
            
        return self._run_node_process(payloads)

    def _build_payload(self, gen, attacker_name, defender_name, move_name, attacker_opts, defender_opts, move_opts, field_opts):
        field_dict = asdict(field_opts) if field_opts else {}
        
        defender_side = {}
        if field_dict.get("isReflect"): defender_side["isReflect"] = True
        if field_dict.get("isLightScreen"): defender_side["isLightScreen"] = True
        if field_dict.get("isAuroraVeil"): defender_side["isAuroraVeil"] = True
        
        # Rimuoviamo i flag dalla root per pulizia (anche se non guasta)
        for key in ["isReflect", "isLightScreen", "isAuroraVeil"]:
            field_dict.pop(key, None)
            
        if defender_side:
            field_dict["defenderSide"] = defender_side
            
        return {
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
            "field": field_dict
        }
        
    def _run_node_process(self, payload: Union[Dict, List[Dict]]) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        proc = subprocess.Popen(
            ["node", self.bridge_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )

        stdout, stderr = proc.communicate(input=json.dumps(payload))

        if proc.returncode != 0:
            raise RuntimeError(f"Errore durante l'esecuzione del calcolatore: {stderr}")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Errore decodifica JSON da Node: {stdout}")
