import json
import os
import re
from typing import List, Dict, Any
from typing import List, Dict, Any
from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions

def normalize_evs(evs: Dict[str, int]) -> Dict[str, int]:
    """Se in Modalità Champions (somma <= 66), scala a Standard (0-252) e assicura chiavi lowercase."""
    if not evs:
        return evs
        
    lower_evs = {k.lower(): v for k, v in evs.items()}
        
    total_evs = sum(lower_evs.values())
    if total_evs <= 66:
        # È in scala Champions (0-32). Convertiamo a Standard (0-252).
        standard_evs = {}
        for stat, val in lower_evs.items():
            if val == 0:
                standard_evs[stat] = 0
            else:
                standard_evs[stat] = (val * 8) - 4
        return standard_evs
    return lower_evs

def evs_to_champions(evs: Dict[str, int]) -> Dict[str, int]:
    """Scala da Standard (0-252) a Champions (0-32). Se già Champions, lascia invariati."""
    if not evs: return {}
    lower_evs = {k.lower(): v for k, v in evs.items()}
    total = sum(lower_evs.values())
    if total <= 66: return lower_evs
    return {k: (v + 4) // 8 if v > 0 else 0 for k, v in lower_evs.items()}

def convert_desc_to_champions(desc: str) -> str:
    """
    Sostituisce i valori EV standard (0-252) nella descrizione di Smogon
    con i rispettivi valori in scala Champions (0-32).
    """
    def replacer(match):
        val = int(match.group(1))
        champ_val = (val + 4) // 8 if val > 0 else 0
        return f"{champ_val}{match.group(2)}"
        
    # Cerchiamo pattern come "252+ Atk" o "252 HP"
    return re.sub(r'\b(\d+)([+-]?\s+(?:HP|Atk|Def|SpA|SpD|Spe))\b', replacer, desc)

class BatchDamageAnalyzer:
    def __init__(self, calc_instance: SmogonDamageCalc):
        self.calc = calc_instance

    def extract_max_damage_percent(self, description: str) -> float:
        """Estrae la percentuale massima di danno dalla descrizione di Smogon."""
        # Esempio: "252+ Atk Choice Band Urshifu-Rapid-Strike Surging Strikes (3 hits) vs. 252 HP / 252+ Def Amoonguss: 108-129 (48.8 - 58.3%)"
        match = re.search(r'\(.*?-\s*([0-9.]+)\%\)', description)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        # Gestisci il caso in cui il danno sia esatto (non un range) o OHKO
        match_single = re.search(r'\(\s*([0-9.]+)\%\s*\)', description)
        if match_single:
            try:
                return float(match_single.group(1))
            except ValueError:
                pass
        
        return 0.0

    def analyze_defensive_matchups(self, team: List[Dict[str, Any]], meta_threats: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Calcola i danni subiti dal team contro le mosse delle meta threats.
        Ritorna un dizionario raggruppato per il pokemon difensore del team.
        """
        batch_requests = []
        
        for member in team:
            # Normalizza EVs per l'engine Smogon (usiamo una copia per non sporcare il dict originale)
            m_opts = dict(member.get("options", {}))
            m_opts["evs"] = normalize_evs(m_opts.get("evs", {}))
            member_opts = PokemonOptions(**m_opts)
            
            for threat in meta_threats:
                t_opts = dict(threat.get("options", {}))
                t_opts["evs"] = normalize_evs(t_opts.get("evs", {}))
                threat_opts = PokemonOptions(**t_opts)
                for move in threat.get("common_moves", threat.get("moves", [])):
                    batch_requests.append({
                        "attacker_name": threat["name"],
                        "defender_name": member["name"],
                        "move_name": move,
                        "attacker_opts": threat_opts,
                        "defender_opts": member_opts,
                        "field_opts": FieldOptions(gameType="Doubles"),
                        "context": {
                            "defender": member["name"], 
                            "attacker": threat["name"], 
                            "attacker_nature": threat_opts.nature,
                            "attacker_item": threat_opts.item,
                            "move": move
                        }
                    })

        results = self.calc.calculate_batch(batch_requests)
        
        analysis = {member["name"]: [] for member in team}
        for req, res in zip(batch_requests, results):
            if res.get("success", False):
                calc_res = res["result"]
                ko_chance = calc_res.get("koChance", "").lower()
                desc = calc_res.get("description", "")
                
                is_guaranteed_ohko = "ohko" in ko_chance or "1hko" in ko_chance
                max_dmg_pct = self.extract_max_damage_percent(desc)
                
                # Convertiamo gli EVs nel testo alla modalità Champions
                champ_desc = convert_desc_to_champions(desc)
                
                # Filtra: OHKO garantito oppure HP residui < 20% (cioè danno massimo > 80%)
                if is_guaranteed_ohko or max_dmg_pct > 80.0:
                    analysis[req["context"]["defender"]].append({
                        "attacker": req["context"]["attacker"],
                        "nature": req["context"]["attacker_nature"],
                        "item": req["context"]["attacker_item"],
                        "move": req["context"]["move"],
                        "damage_min": calc_res["minDamage"],
                        "damage_max": calc_res["maxDamage"],
                        "ko_chance": ko_chance,
                        "description": champ_desc,
                        "is_ohko": is_guaranteed_ohko,
                        "damage_pct": max_dmg_pct
                    })
        return analysis

    def _get_move_categories(self) -> Dict[str, str]:
        """Restituisce una mappa {Nome Mossa: Physical/Special} tramite SQLAlchemy (compatibile PG e SQLite)."""
        categories = {}
        try:
            from database.connection import SessionLocal
            from database.models_v2 import MoveV2
            with SessionLocal() as session:
                rows = session.query(MoveV2.name, MoveV2.category).all()
                for name, category in rows:
                    if name and category:
                        categories[name] = category
        except Exception:
            pass
        return categories

    def _allocate_evs_team(self, base_evs: Dict[str, int], incoming_move_cat: str) -> Dict[str, Dict[str, int]]:
        total = sum(base_evs.values())
        if total >= 508 or total == 66: # Pieno (Standard o Champions)
            return {"Build Esatta": base_evs}
            
        evs = {k: v for k, v in base_evs.items()}
        for k in ["hp", "atk", "def", "spa", "spd", "spe"]:
            if k not in evs: evs[k] = 0
            
        remaining = 508 - total if total > 66 or total == 0 else 66 - total
        limit = 252 if remaining > 66 else 32
        
        def_stat = "def" if incoming_move_cat.lower() == "physical" else "spd"
        can_add = min(limit - evs[def_stat], remaining)
        evs[def_stat] += can_add
        remaining -= can_add
        
        if remaining > 0:
            can_add = min(limit - evs["hp"], remaining)
            evs["hp"] += can_add
            remaining -= can_add
            
        if remaining > 0:
            can_add = min(limit - evs["spe"], remaining)
            evs["spe"] += can_add
            remaining -= can_add
            
        return {"Build Adattata": evs}

    def _allocate_evs_format(self, incoming_move_cat: str) -> Dict[str, Dict[str, int]]:
        def_stat = "def" if incoming_move_cat.lower() == "physical" else "spd"
        
        max_def = {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 1}
        max_def[def_stat] = 32
        
        min_def = {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 32}
        min_def[def_stat] = 0
        
        return {
            "Difese al Massimo": max_def,
            "Difese al Minimo": min_def
        }

    def perform_full_analysis(self, team: List[Dict[str, Any]], meta_threats: List[Dict[str, Any]]):
        """Esegue analisi difensiva, offensiva e calcola gli switch ideali."""
        # 1. Analisi Difensiva (Grezza e Filtrata)
        raw_def, def_results = self._run_defensive(team, meta_threats)
        
        # 2. Analisi Offensiva (Grezza e Filtrata)
        raw_off, off_results = self._run_offensive(team, meta_threats)
        
        # 3. Analisi Switch
        switch_results = self._calculate_switches(raw_def, raw_off, team)
        
        # 4. Associa i Top 2 Switch all'Analisi Difensiva
        for defender_name, threats in def_results.items():
            for t in threats:
                matching_switches = [
                    s for s in switch_results 
                    if s["target"] == defender_name and s["attacker"] == t["attacker"] and s["move"] == t["move"]
                ]
                t["top_switches"] = matching_switches[:2]
        
        return def_results, off_results, switch_results

    def _run_defensive(self, team, meta_threats):
        batch_requests = []
        for threat in meta_threats:
            # Normalizza EVs threat
            t_opts = dict(threat.get("options", {}))
            t_opts["evs"] = normalize_evs(t_opts.get("evs", {}))
            threat_opts = PokemonOptions(**t_opts)
            
            for member in team:
                m_opts = dict(member.get("options", {}))
                m_opts["evs"] = normalize_evs(m_opts.get("evs", {}))
                member_opts = PokemonOptions(**m_opts)
                for move in threat.get("common_moves", threat.get("moves", [])):
                    batch_requests.append({
                        "attacker_name": threat["name"],
                        "defender_name": member["name"],
                        "move_name": move,
                        "attacker_opts": threat_opts,
                        "defender_opts": member_opts,
                        "field_opts": FieldOptions(gameType="Doubles"),
                        "context": {
                            "defender": member["name"], 
                            "attacker": threat["name"], 
                            "attacker_nature": threat_opts.nature,
                            "attacker_item": threat_opts.item,
                            "move": move
                        }
                    })

        results = self.calc.calculate_batch(batch_requests)
        
        filtered = {member["name"]: [] for member in team}
        raw_map = {} # (Attacker, Defender, Move) -> dict with damage and speeds
        
        for req, res in zip(batch_requests, results):
            if res.get("success", False):
                calc_res = res["result"]
                ko_chance = calc_res.get("koChance", "").lower()
                desc = calc_res.get("description", "")
                
                is_guaranteed_ohko = "ohko" in ko_chance or "1hko" in ko_chance
                max_dmg_pct = self.extract_max_damage_percent(desc)
                champ_desc = convert_desc_to_champions(desc)
                
                ctx = req["context"]
                key = (ctx["attacker"], ctx["defender"], ctx["move"])
                raw_map[key] = {
                    "dmg": max_dmg_pct,
                    "attacker_spe": calc_res.get("attackerSpe", 0),
                    "defender_spe": calc_res.get("defenderSpe", 0)
                }
                
                if is_guaranteed_ohko or max_dmg_pct > 80.0:
                    filtered[ctx["defender"]].append({
                        "attacker": ctx["attacker"],
                        "nature": ctx["attacker_nature"],
                        "item": ctx["attacker_item"],
                        "move": ctx["move"],
                        "damage_min": calc_res["minDamage"],
                        "damage_max": calc_res["maxDamage"],
                        "ko_chance": ko_chance,
                        "description": champ_desc,
                        "is_ohko": is_guaranteed_ohko,
                        "damage_pct": max_dmg_pct
                    })
        return raw_map, filtered

    def _run_offensive(self, team, meta_threats):
        move_categories = self._get_move_categories()
        batch_requests = []
        for member in team:
            m_opts = member.get("options", {})
            m_opts["evs"] = normalize_evs(m_opts.get("evs", {}))
            member_opts = PokemonOptions(**m_opts)
            for move in member.get("moves", []):
                move_cat = move_categories.get(move, "Physical")
                if move_cat.lower() == "status": continue
                for threat in meta_threats:
                    source = threat.get("source", "format")
                    t_opts = threat.get("options", {})
                    base_evs = normalize_evs(t_opts.get("evs", {}))
                    
                    if source == "team":
                        threat_variants = self._allocate_evs_team(base_evs, move_cat)
                    else:
                        threat_variants = self._allocate_evs_format(move_cat)
                        
                    for scenario_name, evs_variant in threat_variants.items():
                        variant_opts = t_opts.copy()
                        variant_opts["evs"] = evs_variant
                        threat_opts = PokemonOptions(**variant_opts)
                        
                        batch_requests.append({
                            "attacker_name": member["name"],
                            "defender_name": threat["name"],
                            "move_name": move,
                            "attacker_opts": member_opts,
                            "defender_opts": threat_opts,
                            "field_opts": FieldOptions(gameType="Doubles"),
                            "context": {
                                "attacker": member["name"],
                                "defender": threat["name"],
                                "move": move,
                                "scenario": scenario_name,
                                "nature": threat_opts.nature,
                                "item": threat_opts.item
                            }
                        })
                        
        results = self.calc.calculate_batch(batch_requests)
        filtered = {member["name"]: [] for member in team}
        raw_map = {} # (Attacker, Defender) -> max_dmg_pct across all scenarios/moves
        
        for req, res in zip(batch_requests, results):
            if res.get("success", False):
                calc_res = res["result"]
                ko_chance = calc_res.get("koChance", "")
                desc = calc_res.get("description", "")
                
                is_ohko = "ohko" in ko_chance.lower() or "1hko" in ko_chance.lower()
                max_dmg_pct = self.extract_max_damage_percent(desc)
                
                ctx = req["context"]
                key = (ctx["attacker"], ctx["defender"])
                if key not in raw_map or max_dmg_pct > raw_map[key]:
                    raw_map[key] = max_dmg_pct
                
                if is_ohko or max_dmg_pct > 80.0:
                    filtered[ctx["attacker"]].append({
                        "defender": ctx["defender"],
                        "move": ctx["move"],
                        "scenario": ctx["scenario"],
                        "nature": ctx["nature"],
                        "item": ctx["item"],
                        "damage_min": calc_res["minDamage"],
                        "damage_max": calc_res["maxDamage"],
                        "ko_chance": ko_chance,
                        "description": convert_desc_to_champions(desc),
                        "is_ohko": is_ohko,
                        "damage_pct": max_dmg_pct
                    })
        return raw_map, filtered

    def _calculate_switches(self, raw_def: dict, raw_off: dict, team: list):
        """Calcola lo switch ottimale basato sul Net Advantage Score."""
        switch_table = []
        team_names = [m["name"] for m in team]
        
        # Filtriamo le hit critiche guardando i dati in raw_def
        critical_hits = [(k, v) for k, v in raw_def.items() if v.get("dmg", 0.0) > 80.0]
        
        for (attacker, target, move), target_data in critical_hits:
            dmg_on_target = target_data["dmg"]
            pressione_target = raw_off.get((target, attacker), 0.0)
            
            switches_for_hit = []
            
            for switch in team_names:
                if switch == target: continue
                
                switch_def_data = raw_def.get((attacker, switch, move), {"dmg": 0.0, "attacker_spe": 0, "defender_spe": 0})
                dmg_switch = switch_def_data["dmg"]
                attacker_spe = switch_def_data["attacker_spe"]
                switch_spe = switch_def_data["defender_spe"]
                
                pressione_switch = raw_off.get((switch, attacker), 0.0)
                
                outspeeds_attacker = switch_spe > attacker_spe
                
                if outspeeds_attacker:
                    dmg_true_survival = dmg_switch
                else:
                    dmg_true_survival = dmg_switch * 2.0
                    
                if dmg_switch < 33.0:
                    k = 1.0
                elif 33.0 <= dmg_switch < 50.0:
                    k = 1.5
                else:
                    k = 10.0
                    
                score = pressione_switch - (dmg_true_survival * k)
                efficienza = pressione_switch / (dmg_switch + 10.0)
                
                switches_for_hit.append({
                    "attacker": attacker,
                    "move": move,
                    "target": target,
                    "switch": switch,
                    "dmg_target": dmg_on_target,
                    "dmg_switch": dmg_switch,
                    "press_target": pressione_target,
                    "press_switch": pressione_switch,
                    "score": score,
                    "efficienza": efficienza,
                    "outspeeds": outspeeds_attacker
                })
                
            # Sort switches for this hit by score descending
            switches_for_hit.sort(key=lambda x: x["score"], reverse=True)
            switch_table.extend(switches_for_hit)
                
        switch_table.sort(key=lambda x: x["score"], reverse=True)
        return switch_table

    def analyze_single_move_vs_meta(self, attacker_name: str, attacker_opts: PokemonOptions, move_name: str, meta_threats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calcola i danni di una singola mossa contro il meta, simulando bersagli Max Def e Min Def."""
        move_categories = self._get_move_categories()
        move_cat = move_categories.get(move_name, "Physical")
        
        if move_cat.lower() == "status":
            return []
            
        batch_requests = []
        for threat in meta_threats:
            t_opts = threat.get("options", {})
            threat_variants = self._allocate_evs_format(move_cat)
            
            for scenario_name, evs_variant in threat_variants.items():
                variant_opts = t_opts.copy()
                variant_opts["evs"] = evs_variant
                defender_opts = PokemonOptions(**variant_opts)
                
                batch_requests.append({
                    "attacker_name": attacker_name,
                    "defender_name": threat["name"],
                    "move_name": move_name,
                    "attacker_opts": attacker_opts,
                    "defender_opts": defender_opts,
                    "field_opts": FieldOptions(gameType="Doubles"),
                    "context": {
                        "defender": threat["name"],
                        "scenario": scenario_name
                    }
                })
                
        results = self.calc.calculate_batch(batch_requests)
        
        # Raggruppa i risultati per Defender
        analysis_map = {}
        
        for req, res in zip(batch_requests, results):
            if res.get("success", False):
                calc_res = res["result"]
                desc = calc_res.get("description", "")
                max_dmg_pct = self.extract_max_damage_percent(desc)
                
                ctx = req["context"]
                defender = ctx["defender"]
                scenario = ctx["scenario"]
                
                if defender not in analysis_map:
                    analysis_map[defender] = {"name": defender, "max_def": 0.0, "min_def": 0.0}
                    
                if scenario == "Difese al Massimo":
                    analysis_map[defender]["max_def"] = max_dmg_pct
                elif scenario == "Difese al Minimo":
                    analysis_map[defender]["min_def"] = max_dmg_pct
                    
        return list(analysis_map.values())

