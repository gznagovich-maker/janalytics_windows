"""
meta_damage_calc.py
===================
Calcolo del danno della squadra dell'utente sui Top N (es. 40) Pokémon più
utilizzati nei replay estratti dal Google Sheet.

Caratteristiche:
  - Estrazione dei difensori più frequenti (Specie + Forma) dai replay.
  - Risoluzione delle spread e statistiche difensive realistiche (VGC Lvl 50, standard 66/VGC).
  - Esecuzione batch ad alte prestazioni tramite SmogonDamageCalc (Node.js bridge).
  - Classificazione KO: 1HKO, 2HKO, 3+ HKO, velocità relativa (speed tier).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import re

from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions
from src.domain.sheet_dashboard.models import DashboardGame
from src.domain.team_builder_service import TeamMember, parse_pokepaste
from src.domain.gsheet_import_service import fetch_pokepaste_text


@dataclass
class TargetThreat:
    """Informazioni su un Pokémon del meta da affrontare."""
    species: str
    appearances: int
    appearance_pct: float
    nature: str = "Hardy"
    item: Optional[str] = None
    ability: Optional[str] = None
    evs: Dict[str, int] = field(default_factory=lambda: {"hp": 4, "def": 0, "spd": 0, "spe": 0})
    base_stats: Dict[str, int] = field(default_factory=dict)


@dataclass
class MoveDamageResult:
    """Risultato del calcolo di danno per una specifica mossa."""
    move_name: str
    category: str  # Physical, Special, Status
    min_damage: int
    max_damage: int
    min_pct: float
    max_pct: float
    ko_chance: Optional[str] = None
    description: str = ""


@dataclass
class TargetMatchupResult:
    """Risultato complessivo dell'attaccante contro un difensore specifico."""
    threat: TargetThreat
    best_move: Optional[MoveDamageResult] = None
    all_moves: List[MoveDamageResult] = field(default_factory=list)
    speed_tier: str = "Speed Tie"  # "Piu Veloce", "Piu Lento", "Speed Tie"
    attacker_spe: int = 0
    defender_spe: int = 0
    ko_tier: str = "3+ HKO"  # "1HKO", "2HKO", "3+ HKO"


@dataclass
class TeamMemberDamageReport:
    """Report completo dei danni di un singolo membro della squadra vs il meta."""
    attacker: TeamMember
    target_results: List[TargetMatchupResult] = field(default_factory=list)
    ohko_count: int = 0
    twohko_count: int = 0
    threehko_count: int = 0


def extract_top_meta_threats(
    games: List[DashboardGame],
    top_n: int = 40,
    db_path: Optional[str] = "janalytics.db"
) -> List[TargetThreat]:
    """
    Scansiona i replay per contare le comparse di ogni Pokémon avversario
    (Specie + Forma) e restituisce i primi top_n ordinati per frequenza.
    """
    total_valid_games = 0
    opp_pokemon_counter: Counter = Counter()

    for g in games:
        if not g.summary or not g.summary.opp or not g.summary.opp.team:
            continue
        total_valid_games += 1
        # In VGC ogni Pokémon nel team avversario compare al massimo 1 volta per partita
        for p in set(g.summary.opp.team):
            if p:
                opp_pokemon_counter[p] += 1

    if total_valid_games == 0:
        return []

    top_species = opp_pokemon_counter.most_common(top_n)
    
    # Recupera le statistiche base dal DB SQLite o imposta fallback
    calc = SmogonDamageCalc(db_path=db_path)
    
    threats: List[TargetThreat] = []
    for species, count in top_species:
        pct = (count / total_valid_games) * 100.0
        db_data = calc.fetch_pokemon_from_db(species)
        
        base_stats = {
            "hp": db_data.get("base_hp", 100),
            "atk": db_data.get("base_atk", 100),
            "def": db_data.get("base_def", 100),
            "spa": db_data.get("base_spa", 100),
            "spd": db_data.get("base_spd", 100),
            "spe": db_data.get("base_spe", 100),
        }
        
        # Standard defensive spread benchmark: 252 HP / 4 Def a Lvl 50
        evs = {"hp": 252, "atk": 0, "def": 4, "spa": 0, "spd": 4, "spe": 0}
        
        threats.append(TargetThreat(
            species=species,
            appearances=count,
            appearance_pct=pct,
            nature="Serious",
            item=None,
            ability=None,
            evs=evs,
            base_stats=base_stats
        ))

    return threats


def parse_player_team(paste_text_or_url: str) -> List[TeamMember]:
    """
    Estrae i membri del team da testo raw o scaricando l'URL di Pokepaste.
    """
    text = (paste_text_or_url or "").strip()
    if not text:
        return []

    if text.startswith("http://") or text.startswith("https://"):
        try:
            raw_text = fetch_pokepaste_text(text)
            return parse_pokepaste(raw_text)
        except Exception:
            return []

    return parse_pokepaste(text)


def calculate_damage_for_attacker(
    attacker: TeamMember,
    threats: List[TargetThreat],
    calc: Optional[SmogonDamageCalc] = None,
    field_opts: Optional[FieldOptions] = None
) -> TeamMemberDamageReport:
    """
    Esegue il calcolo batch di tutte le mosse dell'attaccante contro i difensori del meta.
    """
    if calc is None:
        calc = SmogonDamageCalc(db_path="janalytics.db")

    if field_opts is None:
        field_opts = FieldOptions(gameType="Doubles")

    report = TeamMemberDamageReport(attacker=attacker)
    if not threats or not attacker.moves:
        return report

    # Costruisci i parametri dell'attaccante
    attacker_evs = attacker.evs or {}
    attacker_opts = PokemonOptions(
        level=50,
        item=attacker.item if attacker.item else None,
        ability=attacker.ability if attacker.ability else None,
        nature=attacker.nature if attacker.nature else "Serious",
        evs=attacker_evs,
        teraType=attacker.tera_type if attacker.tera_type else None
    )

    batch_requests = []
    req_mapping = []  # (threat_idx, move_name)

    for t_idx, threat in enumerate(threats):
        defender_opts = PokemonOptions(
            level=50,
            item=threat.item,
            ability=threat.ability,
            nature=threat.nature,
            evs=threat.evs
        )

        for move in attacker.moves:
            if not move:
                continue
            batch_requests.append({
                "attacker_name": attacker.species,
                "defender_name": threat.species,
                "move_name": move,
                "attacker_opts": attacker_opts,
                "defender_opts": defender_opts,
                "field_opts": field_opts,
                "gen": 9
            })
            req_mapping.append((t_idx, move))

    # Esegui in batch tramite calc_bridge.js
    results = calc.calculate_batch(batch_requests)

    # Raggruppa i risultati per ciascun difensore
    threat_results_map: Dict[int, List[MoveDamageResult]] = {i: [] for i in range(len(threats))}
    speed_info_map: Dict[int, Tuple[int, int]] = {}

    for (t_idx, move_name), res in zip(req_mapping, results):
        if not res.get("success", False):
            continue
        calc_out = res["result"]
        dmg_raw = calc_out.get("damage", [0])
        if isinstance(dmg_raw, list) and dmg_raw:
            min_dmg = min(dmg_raw)
            max_dmg = max(dmg_raw)
        elif isinstance(dmg_raw, (int, float)):
            min_dmg = int(dmg_raw)
            max_dmg = int(dmg_raw)
        else:
            min_dmg = 0
            max_dmg = 0

        max_hp = calc_out.get("defenderMaxHP", 1) or 1
        min_pct = (min_dmg / max_hp) * 100.0
        max_pct = (max_dmg / max_hp) * 100.0

        if t_idx not in speed_info_map:
            speed_info_map[t_idx] = (
                calc_out.get("attackerSpe", 0),
                calc_out.get("defenderSpe", 0)
            )

        threat_results_map[t_idx].append(MoveDamageResult(
            move_name=move_name,
            category=calc_out.get("moveCategory", "Status"),
            min_damage=min_dmg,
            max_damage=max_dmg,
            min_pct=round(min_pct, 1),
            max_pct=round(max_pct, 1),
            ko_chance=calc_out.get("koChance"),
            description=calc_out.get("description", "")
        ))

    # Costruzione finale dei MatchupResult
    for t_idx, threat in enumerate(threats):
        moves_res = threat_results_map.get(t_idx, [])
        # Trova la mossa con il danno max più elevato
        best_m = max(moves_res, key=lambda m: m.max_pct, default=None)
        
        att_spe, def_spe = speed_info_map.get(t_idx, (0, 0))
        if att_spe > def_spe:
            speed_tier = "Piu Veloce"
        elif att_spe < def_spe:
            speed_tier = "Piu Lento"
        else:
            speed_tier = "Speed Tie"

        ko_tier = "3+ HKO"
        if best_m:
            if best_m.min_pct >= 100.0 or (best_m.ko_chance and ("OHKO" in best_m.ko_chance or "1HKO" in best_m.ko_chance)):
                ko_tier = "1HKO"
            elif best_m.min_pct >= 50.0 or best_m.max_pct >= 100.0:
                ko_tier = "2HKO"

        if ko_tier == "1HKO":
            report.ohko_count += 1
        elif ko_tier == "2HKO":
            report.twohko_count += 1
        else:
            report.threehko_count += 1

        report.target_results.append(TargetMatchupResult(
            threat=threat,
            best_move=best_m,
            all_moves=moves_res,
            speed_tier=speed_tier,
            attacker_spe=att_spe,
            defender_spe=def_spe,
            ko_tier=ko_tier
        ))

    return report
