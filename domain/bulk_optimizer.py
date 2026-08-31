import math
from typing import List, Dict, Any, Tuple
from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions

class BulkOptimizer:
    def __init__(self, calc_instance: SmogonDamageCalc):
        self.calc = calc_instance
        
        # I valid_evs verranno determinati dinamicamente in base al budget (Champions vs Standard)
        pass

    def _calc_hp(self, base: int, iv: int, ev: int, level: int = 50) -> int:
        return math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + level + 10
        
    def _calc_stat(self, base: int, iv: int, ev: int, nature_mod: float = 1.0, level: int = 50) -> int:
        stat = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100) + 5
        return math.floor(stat * nature_mod)

    def optimize_pokemon_bulk(
        self, 
        target_pokemon: Dict[str, Any], 
        meta_threats: List[Dict[str, Any]], 
        budget: int = 66,
        report_limit: int = 20,
        progress_callback=None,
        screens: dict = None
    ) -> Tuple[Dict[str, int], List[Dict[str, Any]], str]:
        """
        Esegue l'Algoritmo di Ottimizzazione Bulk (AOB).
        Ritorna:
        - spread ottimale (dict hp, def, spd)
        - table dei danni subiti dai meta threats con questa spread
        - un messaggio di log/status
        """
        base_hp = target_pokemon.get("baseStats", {}).get("hp", 100)
        base_def = target_pokemon.get("baseStats", {}).get("def", 100)
        base_spd = target_pokemon.get("baseStats", {}).get("spd", 100)
        
        nature = target_pokemon.get("options", {}).get("nature", "Serious")
        nature_mods = self._get_nature_modifiers(nature)
        def_mod = nature_mods["def"]
        spd_mod = nature_mods["spd"]

        is_champions = budget <= 66
        if is_champions:
            valid_ev_steps = list(range(0, 33)) # 0..32
        else:
            valid_ev_steps = [0, 4] + list(range(12, 253, 8))
            
        def get_std_ev(ev: int) -> int:
            if not is_champions: return ev
            return 0 if ev == 0 else (ev * 8) - 4

        # Preparazione Batch Requests per mappare i Danni in base agli EV
        batch_requests = []
        mapping_info = [] # (threat_idx, move_idx, stat_type, ev_val)
        
        for t_idx, threat in enumerate(meta_threats):
            t_opts = PokemonOptions(**threat.get("options", {}))
            moves = threat.get("moves", [])
            for m_idx, move in enumerate(moves):
                for ev_val in valid_ev_steps:
                    std_ev = get_std_ev(ev_val)
                    # Test Physical (vary DEF, fix SPD to 0)
                    d_opts_phys = PokemonOptions(
                        nature=nature,
                        evs={"hp": 0, "def": std_ev, "spd": 0, "spa":0, "atk":0, "spe":0}
                    )
                    batch_requests.append({
                        "attacker_name": threat["name"],
                        "defender_name": target_pokemon["name"],
                        "move_name": move,
                        "attacker_opts": t_opts,
                        "defender_opts": d_opts_phys,
                        "field_opts": FieldOptions(
                            gameType="Doubles",
                            isReflect=screens.get("isReflect", False) if screens else False,
                            isLightScreen=screens.get("isLightScreen", False) if screens else False,
                            isAuroraVeil=screens.get("isAuroraVeil", False) if screens else False
                        )
                    })
                    mapping_info.append((t_idx, m_idx, "def", ev_val))
                    
                    # Test Special (vary SPD, fix DEF to 0)
                    d_opts_spec = PokemonOptions(
                        nature=nature,
                        evs={"hp": 0, "def": 0, "spd": std_ev, "spa":0, "atk":0, "spe":0}
                    )
                    batch_requests.append({
                        "attacker_name": threat["name"],
                        "defender_name": target_pokemon["name"],
                        "move_name": move,
                        "attacker_opts": t_opts,
                        "defender_opts": d_opts_spec,
                        "field_opts": FieldOptions(
                            gameType="Doubles",
                            isReflect=screens.get("isReflect", False) if screens else False,
                            isLightScreen=screens.get("isLightScreen", False) if screens else False,
                            isAuroraVeil=screens.get("isAuroraVeil", False) if screens else False
                        )
                    })
                    mapping_info.append((t_idx, m_idx, "spd", ev_val))

        total_reqs = len(batch_requests)
        
        phys_dmg_map = {} # phys_dmg_map[(t_idx, m_idx)][def_ev] = max_dmg_absolute
        spec_dmg_map = {} # spec_dmg_map[(t_idx, m_idx)][spd_ev] = max_dmg_absolute
        move_categories = {} # (t_idx, m_idx) -> "Physical" or "Special" or "Status"
        
        # Batch Execution
        chunk_size = 200
        for i in range(0, total_reqs, chunk_size):
            chunk_req = batch_requests[i:i+chunk_size]
            chunk_map = mapping_info[i:i+chunk_size]
            
            results = self.calc.calculate_batch(chunk_req)
            for (t_idx, m_idx, stat_type, ev_val), res in zip(chunk_map, results):
                if res.get("success", False):
                    calc_res = res["result"]
                    category = calc_res.get("moveCategory", "Status")
                    move_categories[(t_idx, m_idx)] = category
                    
                    dmg_raw = calc_res.get("damage", [0])
                    
                    def get_max_val(obj):
                        if isinstance(obj, list):
                            if not obj: return 0
                            return max(get_max_val(x) for x in obj)
                        return obj if isinstance(obj, (int, float)) else 0
                        
                    max_dmg = get_max_val(dmg_raw)
                        
                    if stat_type == "def":
                        if (t_idx, m_idx) not in phys_dmg_map: phys_dmg_map[(t_idx, m_idx)] = {}
                        phys_dmg_map[(t_idx, m_idx)][ev_val] = max_dmg
                    else:
                        if (t_idx, m_idx) not in spec_dmg_map: spec_dmg_map[(t_idx, m_idx)] = {}
                        spec_dmg_map[(t_idx, m_idx)][ev_val] = max_dmg
                        
            if progress_callback:
                progress_callback(min(50, int((i + chunk_size) / total_reqs * 50)))

        # 2. Ottimizzazione delle spread (Fast Python Loop)
        if progress_callback: progress_callback(60)
        
        valid_candidates = []
        
        for hp_ev in valid_ev_steps:
            std_hp = get_std_ev(hp_ev)
            max_hp = self._calc_hp(base_hp, 31, std_hp)
            for def_ev in valid_ev_steps:
                for spd_ev in valid_ev_steps:
                    total_spent = hp_ev + def_ev + spd_ev
                    if total_spent > budget:
                        continue
                        
                    survives_all = True
                    max_pct_dmg = 0.0
                    
                    for (t_idx, m_idx), category in move_categories.items():
                        dmg = 0
                        if category == "Physical":
                            dmg = phys_dmg_map[(t_idx, m_idx)].get(def_ev, 0)
                        elif category == "Special":
                            dmg = spec_dmg_map[(t_idx, m_idx)].get(spd_ev, 0)
                            
                        if dmg >= max_hp:
                            survives_all = False
                            break
                            
                        pct = (dmg / max_hp) * 100 if max_hp > 0 else 100
                        if pct > max_pct_dmg:
                            max_pct_dmg = pct
                                
                    if survives_all:
                        valid_candidates.append({
                            "hp": hp_ev, "def": def_ev, "spd": spd_ev,
                            "total": total_spent,
                            "max_pct_dmg": max_pct_dmg
                        })
                        
        if progress_callback: progress_callback(90)
        
        status_msg = ""
        best_spread = {"hp": 252, "def": 252, "spd": 252} # default fallback
        
        if valid_candidates:
            def sort_key(c):
                b_def = self._calc_stat(base_def, 31, get_std_ev(c["def"]), def_mod)
                b_spd = self._calc_stat(base_spd, 31, get_std_ev(c["spd"]), spd_mod)
                hp_val = self._calc_hp(base_hp, 31, get_std_ev(c["hp"]))
                bulk_phys = hp_val * b_def
                bulk_spec = hp_val * b_spd
                combined_bulk = (bulk_phys * bulk_spec) / (bulk_phys + bulk_spec) if (bulk_phys + bulk_spec) > 0 else 0
                return (c["max_pct_dmg"], -combined_bulk)
                
            valid_candidates.sort(key=sort_key)
            best_spread = valid_candidates[0]
            status_msg = f"Ottimizzazione riuscita! Danno massimo: {best_spread['max_pct_dmg']:.1f}% spendendo {best_spread['total']} EVs."
        else:
            status_msg = "Attenzione: Nessuna spread garantisce la sopravvivenza a TUTTI gli attacchi. Applicato Euristica Bulk."
            best_spread = self._maximize_bulk_heuristic(budget, base_hp, base_def, base_spd, def_mod, spd_mod, valid_ev_steps, get_std_ev)

        best_spread["final_hp"] = self._calc_hp(base_hp, 31, get_std_ev(best_spread["hp"]))
        best_spread["final_def"] = self._calc_stat(base_def, 31, get_std_ev(best_spread["def"]), def_mod)
        best_spread["final_spd"] = self._calc_stat(base_spd, 31, get_std_ev(best_spread["spd"]), spd_mod)
        best_spread["nature"] = target_pokemon.get("options", {}).get("nature", "Serious")

        report = self._generate_damage_report(best_spread, move_categories, phys_dmg_map, spec_dmg_map, base_hp, meta_threats, get_std_ev, report_limit, budget, target_pokemon, screens)
        
        if progress_callback: progress_callback(100)
        return best_spread, report, status_msg

    def _maximize_bulk_heuristic(self, budget: int, base_hp: int, base_def: int, base_spd: int, def_mod: float, spd_mod: float, valid_ev_steps, get_std_ev) -> Dict[str, int]:
        best_spread = {"hp": valid_ev_steps[-1], "def": valid_ev_steps[-1], "spd": valid_ev_steps[-1]}
        max_combined_bulk = -1
        
        for hp_ev in valid_ev_steps:
            for def_ev in valid_ev_steps:
                for spd_ev in valid_ev_steps:
                    if hp_ev + def_ev + spd_ev <= budget:
                        b_def = self._calc_stat(base_def, 31, get_std_ev(def_ev), def_mod)
                        b_spd = self._calc_stat(base_spd, 31, get_std_ev(spd_ev), spd_mod)
                        hp_val = self._calc_hp(base_hp, 31, get_std_ev(hp_ev))
                        bulk_phys = hp_val * b_def
                        bulk_spec = hp_val * b_spd
                        combined_bulk = (bulk_phys * bulk_spec) / (bulk_phys + bulk_spec) if (bulk_phys + bulk_spec) > 0 else 0
                        
                        if combined_bulk > max_combined_bulk:
                            max_combined_bulk = combined_bulk
                            best_spread = {"hp": hp_ev, "def": def_ev, "spd": spd_ev, "total": hp_ev+def_ev+spd_ev}
        return best_spread

    def _generate_damage_report(self, best_spread, move_categories, phys_dmg_map, spec_dmg_map, base_hp, meta_threats, get_std_ev, report_limit, budget, target_pokemon, screens):
        report = []
        max_hp = self._calc_hp(base_hp, 31, get_std_ev(best_spread["hp"]))
        
        has_screens = screens and any(screens.values())
        no_screen_damages = {}
        
        if has_screens:
            def get_max_val(obj):
                if isinstance(obj, list):
                    if not obj: return 0
                    return max(get_max_val(x) for x in obj)
                return obj if isinstance(obj, (int, float)) else 0
                
            batch = []
            req_idx_map = {}
            for (t_idx, m_idx), category in move_categories.items():
                if category == "Status": continue
                threat = meta_threats[t_idx]
                move = threat["moves"][m_idx]
                t_opts = PokemonOptions(**threat.get("options", {}))
                d_opts = PokemonOptions(
                    nature=best_spread["nature"],
                    evs={"hp": get_std_ev(best_spread["hp"]), "def": get_std_ev(best_spread["def"]), "spd": get_std_ev(best_spread["spd"]), "spa":0, "atk":0, "spe":0}
                )
                batch.append({
                    "attacker_name": threat["name"],
                    "defender_name": target_pokemon["name"],
                    "move_name": move,
                    "attacker_opts": t_opts,
                    "defender_opts": d_opts,
                    "field_opts": FieldOptions(gameType="Doubles")
                })
                req_idx_map[len(batch) - 1] = (t_idx, m_idx)
                
            results = self.calc.calculate_batch(batch)
            for idx, res in enumerate(results):
                if res.get("success"):
                    dmg_raw = res["result"].get("damage", [0])
                    no_screen_damages[req_idx_map[idx]] = get_max_val(dmg_raw)
        
        for (t_idx, m_idx), category in move_categories.items():
            threat = meta_threats[t_idx]
            move_name = threat["moves"][m_idx]
            
            if category == "Physical":
                dmg = phys_dmg_map[(t_idx, m_idx)].get(best_spread["def"], 0)
            elif category == "Special":
                dmg = spec_dmg_map[(t_idx, m_idx)].get(best_spread["spd"], 0)
            else:
                continue
                
            t_opts = threat.get("options", {})
            attacker_nature = t_opts.get("nature", "Serious")
            attacker_item = t_opts.get("item", "Nessuno")
            if not attacker_item: attacker_item = "Nessuno"
            atk_stat = "atk" if category == "Physical" else "spa"
            attacker_ev = t_opts.get("evs", {}).get(atk_stat, 0)
            
            if budget <= 66 and attacker_ev > 0:
                attacker_ev = (attacker_ev + 4) // 8

            pct = (dmg / max_hp) * 100 if max_hp > 0 else 0
            
            dmg_no_screen = no_screen_damages.get((t_idx, m_idx), dmg)
            pct_no_screen = (dmg_no_screen / max_hp) * 100 if max_hp > 0 else 0
            
            report.append({
                "attacker": threat["name"],
                "attacker_nature": attacker_nature,
                "attacker_item": attacker_item,
                "attacker_ev": attacker_ev,
                "attacker_stat": atk_stat.upper(),
                "move": move_name,
                "category": category,
                "damage_abs": dmg,
                "damage_pct": pct,
                "damage_no_screen_pct": pct_no_screen,
                "ko": pct >= 100
            })
            
        report.sort(key=lambda x: x["damage_pct"], reverse=True)
        return report[:report_limit]

    def _get_nature_modifiers(self, nature: str) -> Dict[str, float]:
        nature = nature.lower()
        mods = {"def": 1.0, "spd": 1.0}
        if nature in ["bold", "impish", "lax", "relaxed"]: mods["def"] = 1.1
        elif nature in ["lonely", "mild", "gentle", "hasty"]: mods["def"] = 0.9
        if nature in ["calm", "gentle", "careful", "sassy"]: mods["spd"] = 1.1
        elif nature in ["naughty", "lax", "naive", "rash"]: mods["spd"] = 0.9
        return mods
