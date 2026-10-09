"""
team_builder_engine.py
======================
Engine di calcolo per la sezione Team Builder.
Usa le build ESATTE fornite dall'utente (spread, item, abilità) senza alcuna ottimizzazione automatica.
Supporta:
 - Live Preview: chi fa 1HKO al selezionato, chi viene battuto in 1HKO dal selezionato
 - Report Bulk: danni subiti (1HKO/2HKO/3HKO+) per ogni Pokémon del team
 - Report Offence: danni inflitti (1HKO/2HKO/3HKO+) per ogni Pokémon del team
 - Report Best Switch: per ogni (Threat × Move) trova il miglior switch tra i 6 del team
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions
from domain.batch_analyzer import normalize_evs


def _pokemon_options_from_member(member: Dict[str, Any]) -> PokemonOptions:
    """Costruisce PokemonOptions dalle build dell'utente (nessuna modifica agli EVs tranne conversione Champions)."""
    opts = member.get("options", {})
    evs = normalize_evs(opts.get("evs") or {})
    return PokemonOptions(
        level=50,
        item=opts.get("item") or None,
        ability=opts.get("ability") or None,
        nature=opts.get("nature") or "Serious",
        evs=evs or None,
        ivs=opts.get("ivs") or None,
        teraType=opts.get("teraType") or None,
    )


def _extract_damage_range_pct(description: str) -> Tuple[float, float]:
    """Estrae (min%, max%) dal testo descrittivo di Smogon."""
    m = re.search(r'\(([\d.]+)\s*-\s*([\d.]+)%\)', description)
    if m:
        return float(m.group(1)), float(m.group(2))
    m2 = re.search(r'\(\s*([\d.]+)%\s*\)', description)
    if m2:
        v = float(m2.group(1))
        return v, v
    return 0.0, 0.0


def _ko_category(min_pct: float, max_pct: float) -> str:
    """Determina la categoria KO in base alla percentuale di danno."""
    if max_pct >= 100.0:
        return "1HKO"
    if max_pct >= 50.0:
        return "2HKO"
    return "3HKO+"


def _format_damage_range(description: str, min_pct: float, max_pct: float) -> str:
    """Formatta la stringa range danno leggibile."""
    return f"{min_pct:.1f}% - {max_pct:.1f}%"


class TeamBuilderEngine:
    """
    Motore di calcolo per la sezione Team Builder.
    Accetta team e roster come liste di dict nel formato:
        {
            "name": "Incineroar",
            "options": {
                "nature": "Jolly",
                "item": "Sitrus Berry",
                "ability": "Intimidate",
                "evs": {"HP": 252, "Atk": 4, "Spe": 252},
                "ivs": {"Atk": 0}  # opzionale
            },
            "moves": ["Fake Out", "Flare Blitz", "Parting Shot", "Throat Chop"]
        }
    """

    def __init__(self, calc: Optional[SmogonDamageCalc] = None):
        self.calc = calc or SmogonDamageCalc(db_path="janalytics.db")

    # ──────────────────────────────────────────────────────────────────────────
    # LIVE PREVIEW
    # ──────────────────────────────────────────────────────────────────────────

    def compute_live_preview(
        self,
        selected_member: Dict[str, Any],
        roster: List[Dict[str, Any]],
        field_opts: Optional[FieldOptions] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Calcola in batch:
          - kos: lista Pokémon del roster che il selezionato manda in 1HKO (con quale mossa)
          - threats: lista Pokémon del roster che mandano in 1HKO il selezionato (con quale mossa)

        Restituisce (kos, threats), ognuno è una lista di dict:
          { "pokemon": str, "move": str, "damage_range": str, "min_pct": float, "max_pct": float,
            "nature": str, "item": str, "description": str }
        """
        if field_opts is None:
            field_opts = FieldOptions(gameType="Doubles")

        selected_opts = _pokemon_options_from_member(selected_member)
        selected_moves = selected_member.get("moves", [])

        batch = []
        contexts = []

        # Richieste: selected → ogni Pokémon del roster (offesa)
        for roster_mon in roster:
            roster_opts = _pokemon_options_from_member(roster_mon)
            for move in selected_moves:
                if not move:
                    continue
                batch.append({
                    "attacker_name": selected_member["name"],
                    "defender_name": roster_mon["name"],
                    "move_name": move,
                    "attacker_opts": selected_opts,
                    "defender_opts": roster_opts,
                    "field_opts": field_opts,
                })
                contexts.append({"mode": "offense", "roster_mon": roster_mon, "move": move})

        # Richieste: ogni Pokémon del roster → selected (difesa)
        for roster_mon in roster:
            roster_opts = _pokemon_options_from_member(roster_mon)
            for move in roster_mon.get("moves", []):
                if not move:
                    continue
                batch.append({
                    "attacker_name": roster_mon["name"],
                    "defender_name": selected_member["name"],
                    "move_name": move,
                    "attacker_opts": roster_opts,
                    "defender_opts": selected_opts,
                    "field_opts": field_opts,
                })
                contexts.append({"mode": "defense", "roster_mon": roster_mon, "move": move})

        if not batch:
            return [], []

        try:
            results = self.calc.calculate_batch(batch)
        except Exception as e:
            print(f"[TeamBuilderEngine] Errore batch live preview: {e}")
            return [], []

        kos: List[Dict] = []
        threats: List[Dict] = []

        for req, res, ctx in zip(batch, results, contexts):
            if not res.get("success", False):
                continue
            calc_res = res["result"]
            desc = calc_res.get("description", "")
            min_pct, max_pct = _extract_damage_range_pct(desc)
            roster_mon = ctx["roster_mon"]
            move = ctx["move"]
            entry = {
                "pokemon": roster_mon["name"],
                "move": move,
                "damage_range": _format_damage_range(desc, min_pct, max_pct),
                "min_pct": min_pct,
                "max_pct": max_pct,
                "nature": roster_mon.get("options", {}).get("nature", ""),
                "item": roster_mon.get("options", {}).get("item", ""),
                "description": desc,
            }
            if ctx["mode"] == "offense" and max_pct >= 100.0:
                # selected manda in KO roster_mon
                kos.append(entry)
            elif ctx["mode"] == "defense" and max_pct >= 100.0:
                # roster_mon manda in KO selected
                threats.append(entry)

        # Deduplica per Pokémon (tieni il danno più alto)
        kos = _dedup_by_max_damage(kos)
        threats = _dedup_by_max_damage(threats)

        return kos, threats

    # ──────────────────────────────────────────────────────────────────────────
    # REPORT BULK (Danni subiti dal team)
    # ──────────────────────────────────────────────────────────────────────────

    def compute_bulk_report(
        self,
        team: List[Dict[str, Any]],
        roster: List[Dict[str, Any]],
        field_opts: Optional[FieldOptions] = None
    ) -> Dict[str, Dict[str, List[Dict]]]:
        """
        Per ogni membro del team, calcola tutti i danni subiti dal roster.
        Raggruppa in 1HKO, 2HKO, 3HKO+.
        Usa le spread ESATTE dell'utente.

        Ritorna: { "pokemon_name": { "1HKO": [...], "2HKO": [...], "3HKO+": [...] } }
        """
        if field_opts is None:
            field_opts = FieldOptions(gameType="Doubles")

        batch = []
        contexts = []

        for team_mon in team:
            team_opts = _pokemon_options_from_member(team_mon)
            for roster_mon in roster:
                roster_opts = _pokemon_options_from_member(roster_mon)
                for move in roster_mon.get("moves", []):
                    if not move:
                        continue
                    batch.append({
                        "attacker_name": roster_mon["name"],
                        "defender_name": team_mon["name"],
                        "move_name": move,
                        "attacker_opts": roster_opts,
                        "defender_opts": team_opts,
                        "field_opts": field_opts,
                    })
                    contexts.append({
                        "team_mon": team_mon["name"],
                        "roster_mon": roster_mon,
                        "move": move
                    })

        if not batch:
            return {}

        try:
            results = self.calc.calculate_batch(batch)
        except Exception as e:
            print(f"[TeamBuilderEngine] Errore batch bulk report: {e}")
            return {}

        report: Dict[str, Dict[str, List[Dict]]] = {
            m["name"]: {"1HKO": [], "2HKO": [], "3HKO+": []}
            for m in team
        }

        for req, res, ctx in zip(batch, results, contexts):
            if not res.get("success", False):
                continue
            calc_res = res["result"]
            desc = calc_res.get("description", "")
            min_pct, max_pct = _extract_damage_range_pct(desc)
            category = _ko_category(min_pct, max_pct)
            roster_mon = ctx["roster_mon"]
            entry = {
                "attacker": roster_mon["name"],
                "move": ctx["move"],
                "nature": roster_mon.get("options", {}).get("nature", ""),
                "item": roster_mon.get("options", {}).get("item", ""),
                "ability": roster_mon.get("options", {}).get("ability", ""),
                "evs": roster_mon.get("options", {}).get("evs", {}),
                "teraType": roster_mon.get("options", {}).get("teraType", ""),
                "moves": roster_mon.get("moves", []),
                "damage_range": _format_damage_range(desc, min_pct, max_pct),
                "min_pct": min_pct,
                "max_pct": max_pct,
                "description": desc,
            }
            target_name = ctx["team_mon"]
            if target_name in report:
                report[target_name][category].append(entry)

        # Ordina per max_pct decrescente dentro ogni categoria
        for mon_name in report:
            for cat in report[mon_name]:
                report[mon_name][cat].sort(key=lambda x: x["max_pct"], reverse=True)

        return report

    # ──────────────────────────────────────────────────────────────────────────
    # REPORT OFFENCE (Danni inflitti dal team)
    # ──────────────────────────────────────────────────────────────────────────

    def compute_offence_report(
        self,
        team: List[Dict[str, Any]],
        roster: List[Dict[str, Any]],
        field_opts: Optional[FieldOptions] = None
    ) -> Dict[str, Dict[str, List[Dict]]]:
        """
        Per ogni membro del team, calcola tutti i danni inflitti al roster.
        Raggruppa in 1HKO, 2HKO, 3HKO+.
        Usa le spread ESATTE dell'utente.

        Ritorna: { "pokemon_name": { "1HKO": [...], "2HKO": [...], "3HKO+": [...] } }
        """
        if field_opts is None:
            field_opts = FieldOptions(gameType="Doubles")

        batch = []
        contexts = []

        for team_mon in team:
            team_opts = _pokemon_options_from_member(team_mon)
            for move in team_mon.get("moves", []):
                if not move:
                    continue
                for roster_mon in roster:
                    roster_opts = _pokemon_options_from_member(roster_mon)
                    batch.append({
                        "attacker_name": team_mon["name"],
                        "defender_name": roster_mon["name"],
                        "move_name": move,
                        "attacker_opts": team_opts,
                        "defender_opts": roster_opts,
                        "field_opts": field_opts,
                    })
                    contexts.append({
                        "team_mon": team_mon["name"],
                        "roster_mon": roster_mon,
                        "move": move
                    })

        if not batch:
            return {}

        try:
            results = self.calc.calculate_batch(batch)
        except Exception as e:
            print(f"[TeamBuilderEngine] Errore batch offence report: {e}")
            return {}

        report: Dict[str, Dict[str, List[Dict]]] = {
            m["name"]: {"1HKO": [], "2HKO": [], "3HKO+": []}
            for m in team
        }

        for req, res, ctx in zip(batch, results, contexts):
            if not res.get("success", False):
                continue
            calc_res = res["result"]
            desc = calc_res.get("description", "")
            min_pct, max_pct = _extract_damage_range_pct(desc)
            category = _ko_category(min_pct, max_pct)
            roster_mon = ctx["roster_mon"]
            entry = {
                "defender": roster_mon["name"],
                "move": ctx["move"],
                "nature": roster_mon.get("options", {}).get("nature", ""),
                "item": roster_mon.get("options", {}).get("item", ""),
                "ability": roster_mon.get("options", {}).get("ability", ""),
                "evs": roster_mon.get("options", {}).get("evs", {}),
                "teraType": roster_mon.get("options", {}).get("teraType", ""),
                "moves": roster_mon.get("moves", []),
                "damage_range": _format_damage_range(desc, min_pct, max_pct),
                "min_pct": min_pct,
                "max_pct": max_pct,
                "description": desc,
            }
            attacker_name = ctx["team_mon"]
            if attacker_name in report:
                report[attacker_name][category].append(entry)

        # Ordina per max_pct decrescente
        for mon_name in report:
            for cat in report[mon_name]:
                report[mon_name][cat].sort(key=lambda x: x["max_pct"], reverse=True)

        return report

    # ──────────────────────────────────────────────────────────────────────────
    # REPORT BEST SWITCH
    # ──────────────────────────────────────────────────────────────────────────

    def compute_best_switch_report(
        self,
        team: List[Dict[str, Any]],
        roster: List[Dict[str, Any]],
        field_opts: Optional[FieldOptions] = None
    ) -> List[Dict[str, Any]]:
        """
        Per ogni (Threat × Move) che colpisce un membro del team:
          1. Calcola i danni sul Target originale
          2. Trova il Suggested Switch (membro del team con % danno minore, esclude il Target)
          3. Calcola i counter-pressure: Target → Threat e Switch → Threat

        Colonne output (una riga per ogni (Threat, Move, Target)):
          threat, move, target, damage_on_target (range str),
          suggested_switch, damage_on_switch (range str),
          pressure_from_target (range str), target_move (str),
          pressure_from_switch (range str), switch_move (str)
        """
        if field_opts is None:
            field_opts = FieldOptions(gameType="Doubles")

        rows: List[Dict[str, Any]] = []
        team_names = [m["name"] for m in team]
        team_by_name = {m["name"]: m for m in team}

        # ─── FASE 1: calcola danni di ogni Threat × Move su ogni membro del team ───
        threat_vs_team_batch = []
        threat_vs_team_ctx = []

        for roster_mon in roster:
            roster_opts = _pokemon_options_from_member(roster_mon)
            for move in roster_mon.get("moves", []):
                if not move:
                    continue
                for team_mon in team:
                    team_opts = _pokemon_options_from_member(team_mon)
                    threat_vs_team_batch.append({
                        "attacker_name": roster_mon["name"],
                        "defender_name": team_mon["name"],
                        "move_name": move,
                        "attacker_opts": roster_opts,
                        "defender_opts": team_opts,
                        "field_opts": field_opts,
                    })
                    threat_vs_team_ctx.append({
                        "threat": roster_mon,
                        "move": move,
                        "team_mon_name": team_mon["name"],
                    })

        if not threat_vs_team_batch:
            return []

        try:
            threat_vs_team_results = self.calc.calculate_batch(threat_vs_team_batch)
        except Exception as e:
            print(f"[TeamBuilderEngine] Errore batch best_switch fase 1: {e}")
            return []

        # Struttura: damage_map[(threat_name, move, team_mon_name)] = (min_pct, max_pct, desc)
        damage_map: Dict[Tuple, Tuple[float, float, str]] = {}
        for req, res, ctx in zip(threat_vs_team_batch, threat_vs_team_results, threat_vs_team_ctx):
            if not res.get("success", False):
                damage_map[(ctx["threat"]["name"], ctx["move"], ctx["team_mon_name"])] = (0.0, 0.0, "")
                continue
            calc_res = res["result"]
            desc = calc_res.get("description", "")
            min_pct, max_pct = _extract_damage_range_pct(desc)
            damage_map[(ctx["threat"]["name"], ctx["move"], ctx["team_mon_name"])] = (min_pct, max_pct, desc)

        # ─── FASE 2: pressure (team → threat) — ogni membro con ogni sua mossa vs ogni threat ───
        pressure_batch = []
        pressure_ctx = []

        for team_mon in team:
            team_opts = _pokemon_options_from_member(team_mon)
            for move in team_mon.get("moves", []):
                if not move:
                    continue
                for roster_mon in roster:
                    roster_opts = _pokemon_options_from_member(roster_mon)
                    pressure_batch.append({
                        "attacker_name": team_mon["name"],
                        "defender_name": roster_mon["name"],
                        "move_name": move,
                        "attacker_opts": team_opts,
                        "defender_opts": roster_opts,
                        "field_opts": field_opts,
                    })
                    pressure_ctx.append({
                        "team_mon_name": team_mon["name"],
                        "threat_name": roster_mon["name"],
                        "move": move,
                    })

        # pressure_map[(team_mon_name, threat_name, move)] = (min_pct, max_pct, desc)
        pressure_map: Dict[Tuple, Tuple[float, float, str]] = {}
        if pressure_batch:
            try:
                pressure_results = self.calc.calculate_batch(pressure_batch)
                for req, res, ctx in zip(pressure_batch, pressure_results, pressure_ctx):
                    if not res.get("success", False):
                        pressure_map[(ctx["team_mon_name"], ctx["threat_name"], ctx["move"])] = (0.0, 0.0, "")
                        continue
                    calc_res = res["result"]
                    desc = calc_res.get("description", "")
                    min_pct, max_pct = _extract_damage_range_pct(desc)
                    pressure_map[(ctx["team_mon_name"], ctx["threat_name"], ctx["move"])] = (min_pct, max_pct, desc)
            except Exception as e:
                print(f"[TeamBuilderEngine] Errore batch best_switch fase 2 (pressure): {e}")

        # ─── FASE 3: Costruisci le righe del report ───
        for roster_mon in roster:
            threat_name = roster_mon["name"]
            for move in roster_mon.get("moves", []):
                if not move:
                    continue
                for target_mon in team:
                    target_name = target_mon["name"]
                    key = (threat_name, move, target_name)
                    min_on_target, max_on_target, desc_target = damage_map.get(key, (0.0, 0.0, ""))

                    # Trova il Suggested Switch (esclude il Target stesso)
                    best_switch_name = None
                    best_switch_min = 999.0
                    best_switch_max = 999.0
                    best_switch_desc = ""

                    for switch_mon in team:
                        if switch_mon["name"] == target_name:
                            continue
                        sw_key = (threat_name, move, switch_mon["name"])
                        sw_min, sw_max, sw_desc = damage_map.get(sw_key, (0.0, 0.0, ""))
                        if sw_max < best_switch_max or (sw_max == best_switch_max and sw_min < best_switch_min):
                            best_switch_name = switch_mon["name"]
                            best_switch_min = sw_min
                            best_switch_max = sw_max
                            best_switch_desc = sw_desc

                    # Pressure from Target → Threat (miglior mossa)
                    target_best_move, target_pressure = _find_best_pressure(target_name, threat_name, target_mon.get("moves", []), pressure_map)
                    # Pressure from Switch → Threat (miglior mossa)
                    switch_best_move, switch_pressure = ("—", (0.0, 0.0, ""))
                    if best_switch_name:
                        switch_mon_data = team_by_name.get(best_switch_name)
                        switch_moves = switch_mon_data.get("moves", []) if switch_mon_data else []
                        switch_best_move, switch_pressure = _find_best_pressure(best_switch_name, threat_name, switch_moves, pressure_map)

                    rows.append({
                        "threat": threat_name,
                        "threat_build": roster_mon,
                        "move": move,
                        "target": target_name,
                        "damage_on_target": _format_damage_range(desc_target, min_on_target, max_on_target),
                        "min_on_target": min_on_target,
                        "max_on_target": max_on_target,
                        "suggested_switch": best_switch_name or "—",
                        "damage_on_switch": _format_damage_range(best_switch_desc, best_switch_min, best_switch_max) if best_switch_name else "—",
                        "min_on_switch": best_switch_min,
                        "max_on_switch": best_switch_max,
                        "pressure_from_target": _format_damage_range(target_pressure[2], target_pressure[0], target_pressure[1]),
                        "target_move": target_best_move,
                        "pressure_from_switch": _format_damage_range(switch_pressure[2], switch_pressure[0], switch_pressure[1]),
                        "switch_move": switch_best_move,
                    })

        # Ordina per max_on_target decrescente (le minacce maggiori prima)
        rows.sort(key=lambda r: r["max_on_target"], reverse=True)
        return rows


# ──────────────────────────────────────────────────────────────────────────────
# Helpers privati
# ──────────────────────────────────────────────────────────────────────────────

def _dedup_by_max_damage(entries: List[Dict]) -> List[Dict]:
    """Deduplica per Pokémon tenendo la entry con danno massimo più alto."""
    seen: Dict[str, Dict] = {}
    for e in entries:
        name = e["pokemon"]
        if name not in seen or e["max_pct"] > seen[name]["max_pct"]:
            seen[name] = e
    return sorted(seen.values(), key=lambda x: x["max_pct"], reverse=True)


def _find_best_pressure(
    attacker_name: str,
    defender_name: str,
    moves: List[str],
    pressure_map: Dict[Tuple, Tuple[float, float, str]]
) -> Tuple[str, Tuple[float, float, str]]:
    """Trova la mossa di attacker_name che infligge il danno maggiore a defender_name."""
    best_move = "—"
    best_result: Tuple[float, float, str] = (0.0, 0.0, "")
    for move in moves:
        if not move:
            continue
        key = (attacker_name, defender_name, move)
        result = pressure_map.get(key, (0.0, 0.0, ""))
        if result[1] > best_result[1]:
            best_move = move
            best_result = result
    return best_move, best_result
