import math
from typing import List, Dict, Any, Tuple
from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions

class OffenseOptimizer:
    def __init__(self, calc_instance: SmogonDamageCalc):
        self.calc = calc_instance

    def _calc_hp(self, base: int, iv: int, ev: int, level: int = 50) -> int:
        return math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + level + 10
        
    def _calc_stat(self, base: int, iv: int, ev: int, nature_mod: float = 1.0, level: int = 50) -> int:
        stat = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + 5
        return math.floor(stat * nature_mod)

    def _get_nature_modifiers(self, nature: str) -> Dict[str, float]:
        nature = nature.lower()
        mods = {"atk": 1.0, "spa": 1.0, "spe": 1.0}
        
        if nature in ["lonely", "brave", "adamant", "naughty"]: mods["atk"] = 1.1
        elif nature in ["bold", "timid", "modest", "calm"]: mods["atk"] = 0.9
        
        if nature in ["modest", "mild", "quiet", "rash"]: mods["spa"] = 1.1
        elif nature in ["adamant", "impish", "jolly", "careful"]: mods["spa"] = 0.9
        
        return mods

    def get_max_val(self, obj):
        if isinstance(obj, list):
            if not obj: return 0
            return max(self.get_max_val(x) for x in obj)
        return obj if isinstance(obj, (int, float)) else 0

    def optimize_pokemon_offense(
        self, 
        target_pokemon: Dict[str, Any], 
        defenders: List[Dict[str, Any]], 
        budget: int = 66,
        progress_callback=None,
        screens: dict = None,
        is_static_mode: bool = False
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]], str]:
        
        base_atk = target_pokemon.get("baseStats", {}).get("atk", 100)
        base_spa = target_pokemon.get("baseStats", {}).get("spa", 100)
        
        nature = target_pokemon.get("options", {}).get("nature", "Serious")
        nature_mods = self._get_nature_modifiers(nature)
        atk_mod = nature_mods["atk"]
        spa_mod = nature_mods["spa"]

        is_champions = budget <= 66
        
        if is_static_mode:
            target_evs = target_pokemon.get("options", {}).get("evs", {})
            valid_atk_steps = [target_evs.get("atk", target_evs.get("Atk", 0))]
            valid_spa_steps = [target_evs.get("spa", target_evs.get("SpA", 0))]
        else:
            if is_champions:
                valid_ev_steps = list(range(0, 33)) # 0..32
            else:
                valid_ev_steps = [0, 4] + list(range(12, 253, 8))
            valid_atk_steps = valid_ev_steps
            valid_spa_steps = valid_ev_steps
            
        def get_std_ev(ev: int) -> int:
            if not is_champions: return ev
            return 0 if ev == 0 else (ev * 8) - 4

        batch_requests = []
        mapping_info = [] # (d_idx, move, stat_type, ev_val)
        
        our_moves = target_pokemon.get("moves", [])
        our_base_opts = target_pokemon.get("options", {})
        
        for d_idx, defender in enumerate(defenders):
            d_opts = PokemonOptions(**defender.get("options", {}))
            
            for move in our_moves:
                for ev_val in valid_atk_steps:
                    std_ev = get_std_ev(ev_val)
                    
                    # Simulate ATK scaling (Physical)
                    a_opts_phys = PokemonOptions(
                        nature=nature,
                        item=our_base_opts.get("item"),
                        ability=our_base_opts.get("ability"),
                        evs={"hp": 0, "def": 0, "spd": 0, "spa":0, "atk": std_ev, "spe":0}
                    )
                    batch_requests.append({
                        "attacker_name": target_pokemon["name"],
                        "defender_name": defender["name"],
                        "move_name": move,
                        "attacker_opts": a_opts_phys,
                        "defender_opts": d_opts,
                        "field_opts": FieldOptions(
                            gameType="Doubles",
                            isReflect=screens.get("isReflect", False) if screens else False,
                            isLightScreen=screens.get("isLightScreen", False) if screens else False,
                            isAuroraVeil=screens.get("isAuroraVeil", False) if screens else False
                        )
                    })
                    mapping_info.append((d_idx, move, "atk", ev_val))
                    
                for ev_val in valid_spa_steps:
                    std_ev = get_std_ev(ev_val)
                    
                    # Simulate SPA scaling (Special)
                    a_opts_spec = PokemonOptions(
                        nature=nature,
                        item=our_base_opts.get("item"),
                        ability=our_base_opts.get("ability"),
                        evs={"hp": 0, "def": 0, "spd": 0, "spa": std_ev, "atk":0, "spe":0}
                    )
                    batch_requests.append({
                        "attacker_name": target_pokemon["name"],
                        "defender_name": defender["name"],
                        "move_name": move,
                        "attacker_opts": a_opts_spec,
                        "defender_opts": d_opts,
                        "field_opts": FieldOptions(
                            gameType="Doubles",
                            isReflect=screens.get("isReflect", False) if screens else False,
                            isLightScreen=screens.get("isLightScreen", False) if screens else False,
                            isAuroraVeil=screens.get("isAuroraVeil", False) if screens else False
                        )
                    })
                    mapping_info.append((d_idx, move, "spa", ev_val))

        total_reqs = len(batch_requests)
        
        phys_dmg_map = {} # phys_dmg_map[(d_idx, move)][atk_ev] = max_dmg_pct
        spec_dmg_map = {} # spec_dmg_map[(d_idx, move)][spa_ev] = max_dmg_pct
        move_categories = {} # move -> "Physical" or "Special" or "Status"
        
        chunk_size = 200
        for i in range(0, total_reqs, chunk_size):
            chunk_req = batch_requests[i:i+chunk_size]
            chunk_map = mapping_info[i:i+chunk_size]
            
            results = self.calc.calculate_batch(chunk_req)
            for (d_idx, move, stat_type, ev_val), res in zip(chunk_map, results):
                if res.get("success", False):
                    calc_res = res["result"]
                    category = calc_res.get("moveCategory", "Status")
                    move_categories[move] = category
                    
                    dmg_raw = calc_res.get("damage", [0])
                    max_dmg = self.get_max_val(dmg_raw)
                    min_dmg = min(dmg_raw) if isinstance(dmg_raw, list) and dmg_raw else (dmg_raw if isinstance(dmg_raw, (int, float)) else 0)
                    
                    d_max_hp = calc_res.get("defenderMaxHP", 1)
                    max_pct_dmg = (max_dmg / d_max_hp) * 100 if d_max_hp > 0 else 0
                    min_pct_dmg = (min_dmg / d_max_hp) * 100 if d_max_hp > 0 else 0
                        
                    if stat_type == "atk":
                        if (d_idx, move) not in phys_dmg_map: phys_dmg_map[(d_idx, move)] = {}
                        phys_dmg_map[(d_idx, move)][ev_val] = (min_pct_dmg, max_pct_dmg)
                    else:
                        if (d_idx, move) not in spec_dmg_map: spec_dmg_map[(d_idx, move)] = {}
                        spec_dmg_map[(d_idx, move)][ev_val] = (min_pct_dmg, max_pct_dmg)
                        
            if progress_callback:
                progress_callback(min(60, int((i + chunk_size) / total_reqs * 60)))

        # 2. Ottimizzazione delle spread
        if progress_callback: progress_callback(70)
        
        best_spread = {"atk": 0, "spa": 0, "total": 0}
        max_ohko = -1
        max_2hko = -1
        min_ev_spent = 9999
        max_total_dmg = -1
        
        for atk_ev in valid_atk_steps:
            for spa_ev in valid_spa_steps:
                if atk_ev + spa_ev <= budget or is_static_mode:
                    total_ohko = 0
                    total_2hko = 0
                    total_dmg = 0
                    
                    for d_idx, defender in enumerate(defenders):
                        d_max_pct = 0
                        for move in our_moves:
                            cat = move_categories.get(move, "Status")
                            if cat == "Physical":
                                dmg = phys_dmg_map.get((d_idx, move), {}).get(atk_ev, (0, 0))[1]
                            elif cat == "Special":
                                dmg = spec_dmg_map.get((d_idx, move), {}).get(spa_ev, (0, 0))[1]
                            else:
                                dmg = 0
                            
                            if dmg > d_max_pct:
                                d_max_pct = dmg
                                
                        total_dmg += d_max_pct
                        if d_max_pct >= 100:
                            total_ohko += 1
                        elif d_max_pct >= 50:
                            total_2hko += 1
                            
                    # Valutazione euristica "Cacciatore di KO"
                    ev_spent = atk_ev + spa_ev
                    is_better = False
                    
                    if total_ohko > max_ohko:
                        is_better = True
                    elif total_ohko == max_ohko:
                        if total_2hko > max_2hko:
                            is_better = True
                        elif total_2hko == max_2hko:
                            if ev_spent < min_ev_spent:
                                is_better = True
                            elif ev_spent == min_ev_spent:
                                if total_dmg > max_total_dmg:
                                    is_better = True
                                    
                    if is_better:
                        max_ohko = total_ohko
                        max_2hko = total_2hko
                        min_ev_spent = ev_spent
                        max_total_dmg = total_dmg
                        best_spread = {"atk": atk_ev, "spa": spa_ev, "total": ev_spent, "max_ohko": max_ohko}

        best_spread["final_atk"] = self._calc_stat(base_atk, 31, get_std_ev(best_spread["atk"]), atk_mod)
        best_spread["final_spa"] = self._calc_stat(base_spa, 31, get_std_ev(best_spread["spa"]), spa_mod)
        best_spread["nature"] = nature
        
        if is_static_mode:
            status_msg = f"Calcolo Statico completato! OHKO su {best_spread.get('max_ohko', 0)}/{len(defenders)} bersagli. EV totali: {best_spread['total']}."
        else:
            status_msg = f"Ottimizzazione riuscita! OHKO garantiti: {best_spread.get('max_ohko', 0)} su {len(defenders)} bersagli. EV usate: {best_spread['total']}."

        # 3. Generazione Report
        if progress_callback: progress_callback(90)
        report = self._generate_damage_report(best_spread, our_moves, move_categories, phys_dmg_map, spec_dmg_map, defenders, target_pokemon, screens)
        
        if progress_callback: progress_callback(100)
        return best_spread, report, status_msg

    def _generate_damage_report(self, best_spread, our_moves, move_categories, phys_dmg_map, spec_dmg_map, defenders, target_pokemon, screens):
        report = []
        
        for d_idx, defender in enumerate(defenders):
            d_opts = defender.get("options", {})
            defender_nature = d_opts.get("nature", "Serious")
            defender_item = d_opts.get("item", "Nessuno")
            if not defender_item: defender_item = "Nessuno"
            
            # Find the best move against this defender
            best_move = None
            best_cat = None
            max_pct = -1
            min_pct = -1
            
            for move in our_moves:
                cat = move_categories.get(move, "Status")
                if cat == "Physical":
                    pct_tuple = phys_dmg_map.get((d_idx, move), {}).get(best_spread["atk"], (0, 0))
                elif cat == "Special":
                    pct_tuple = spec_dmg_map.get((d_idx, move), {}).get(best_spread["spa"], (0, 0))
                else:
                    pct_tuple = (0, 0)
                    
                if pct_tuple[1] > max_pct:
                    max_pct = pct_tuple[1]
                    min_pct = pct_tuple[0]
                    best_move = move
                    best_cat = cat
                    
            if not best_move:
                continue
                
            # Calcolo dei KO per la sensitivity
            def get_ko_tier(pct_dmg):
                if pct_dmg >= 100: return 1
                if pct_dmg >= 50: return 2
                return 3
                
            base_tier = get_ko_tier(max_pct)
            
            # Sensitivity Analysis (Perdite e Guadagni)
            sensitivity = {}
            # Valutiamo le perdite (-1, -2, -3) e i guadagni (+1, +2, +3)
            for offset in [-3, -2, -1, 1, 2, 3]:
                drop_pct = -1
                test_ev = -1
                if best_cat == "Physical":
                    test_ev = best_spread["atk"] + offset
                elif best_cat == "Special":
                    test_ev = best_spread["spa"] + offset
                
                # Le EV devono restare nei limiti del sistema 0-32
                if 0 <= test_ev <= 32:
                    if best_cat == "Physical":
                        drop_pct = phys_dmg_map.get((d_idx, best_move), {}).get(test_ev, (0, 0))[1]
                    elif best_cat == "Special":
                        drop_pct = spec_dmg_map.get((d_idx, best_move), {}).get(test_ev, (0, 0))[1]
                        
                    new_tier = get_ko_tier(drop_pct)
                    
                    if offset < 0 and new_tier > base_tier:
                        # Peggioramento
                        sensitivity[f"{offset}"] = new_tier
                    elif offset > 0 and new_tier < base_tier:
                        # Miglioramento
                        sensitivity[f"+{offset}"] = new_tier
                    
            d_evs = defender.get("options", {}).get("evs", {})
            d_hp = d_evs.get("hp", 0)
            d_def = d_evs.get("def", 0)
            d_spd = d_evs.get("spd", 0)
            
            # Speed Tier comparison (Base Speed)
            attacker_base_spe = target_pokemon.get("baseStats", {}).get("spe", 0)
            defender_base_spe = defender.get("baseStats", {}).get("spe", 0)
            if attacker_base_spe > defender_base_spe:
                speed_tier = "Più Lento"   # target is slower than us
            elif attacker_base_spe < defender_base_spe:
                speed_tier = "Più Veloce"  # target is faster than us
            else:
                speed_tier = "Speed Tie"
            
            defender_ability = defender.get("options", {}).get("ability", "Sconosciuta")
            if not defender_ability:
                defender_ability = "Sconosciuta"
            
            report.append({
                "defender": defender["name"],
                "defender_nature": defender_nature,
                "defender_item": defender_item,
                "defender_evs": f"{d_hp} / {d_def} / {d_spd}",
                "defender_ability": defender_ability,
                "move": best_move,
                "category": best_cat,
                "damage_pct": max_pct,
                "min_pct": min_pct,
                "ko": max_pct >= 100,
                "ko_tier": base_tier,
                "sensitivity": sensitivity,
                "attacker_base_spe": attacker_base_spe,
                "defender_base_spe": defender_base_spe,
                "speed_tier": speed_tier
            })
            
        # Raggruppa i risultati per facilitare la UI
        structured_report = {
            "1HKO": [r for r in report if r["ko_tier"] == 1],
            "2HKO": [r for r in report if r["ko_tier"] == 2],
            "3HKO+": [r for r in report if r["ko_tier"] >= 3],
            "Sensitivity": {
                "Loss_1HKO": [r for r in report if r["ko_tier"] == 1 and any(k.startswith('-') for k in r["sensitivity"].keys())],
                "Loss_2HKO": [r for r in report if r["ko_tier"] == 2 and any(k.startswith('-') for k in r["sensitivity"].keys())],
                "Gain_1HKO": [r for r in report if r["ko_tier"] == 2 and any(k.startswith('+') and v == 1 for k, v in r["sensitivity"].items())],
                "Gain_2HKO": [r for r in report if r["ko_tier"] == 3 and any(k.startswith('+') and v == 2 for k, v in r["sensitivity"].items())]
            }
        }
            
        return structured_report
