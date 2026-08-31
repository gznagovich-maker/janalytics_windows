import random
import time
import re
from typing import List, Dict, Any, Tuple
from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions

class TeamOptimizer:
    def __init__(self, calc_instance: SmogonDamageCalc):
        self.calc = calc_instance
        self.damage_matrix = {} # [defender_idx][attacker_idx] = float (damage pct) - Difensiva (Meta attacca Pool)
        self.speed_matrix = {}  # [defender_idx][attacker_idx] = bool (True if defender is faster)
        
        self.offensive_damage_matrix = {} # [attacker_idx][defender_idx] = float (damage pct) - Offensiva (Pool attacca Meta)
        self.offensive_speed_matrix = {}
        
        self.pool_size = 0
        self.threats_size = 0
        
    def _parse_max_damage(self, res_dict: dict) -> float:
        desc = res_dict.get("description", "")
        max_dmg = 0.0
        match = re.search(r'\(.*?-\s*([0-9.]+)\%\)', desc)
        if match:
            try: max_dmg = float(match.group(1))
            except: pass
        else:
            match_single = re.search(r'\(\s*([0-9.]+)\%\s*\)', desc)
            if match_single:
                try: max_dmg = float(match_single.group(1))
                except: pass
                
        if "guaranteed 1HKO" in res_dict.get("koChance", "").lower() and max_dmg == 0:
            max_dmg = 100.0
        return max_dmg

    def build_matrices(self, pool: List[Dict[str, Any]], meta_threats: List[Dict[str, Any]], progress_callback=None):
        """
        Pre-calcola le matrici di Danno e Speed (Sia Difensive che Offensive).
        """
        self.pool_size = len(pool)
        self.threats_size = len(meta_threats)
        self.damage_matrix = {i: {} for i in range(self.pool_size)}
        self.speed_matrix = {i: {} for i in range(self.pool_size)}
        
        self.offensive_damage_matrix = {i: {} for i in range(self.pool_size)}
        self.offensive_speed_matrix = {i: {} for i in range(self.pool_size)}
        self.is_mega = {i: False for i in range(self.pool_size)}
        
        batch_requests = []
        mapping_info = [] # (p_idx, t_idx, is_offensive)
        
        # 1. Matrice Difensiva (Meta attacca Pool)
        for t_idx, threat in enumerate(meta_threats):
            t_opts = PokemonOptions(**threat.get("options", {}))
            moves = threat.get("moves", [])
            if not moves: continue
                
            for p_idx, defender in enumerate(pool):
                d_opts = PokemonOptions(**defender.get("options", {}))
                
                # Check se è Mega
                if "-Mega" in defender["name"]:
                    self.is_mega[p_idx] = True
                    
                for move in moves:
                    batch_requests.append({
                        "attacker_name": threat["name"],
                        "defender_name": defender["name"],
                        "move_name": move,
                        "attacker_opts": t_opts,
                        "defender_opts": d_opts,
                        "field_opts": FieldOptions(gameType="Doubles")
                    })
                    mapping_info.append((p_idx, t_idx, False))

        # 2. Matrice Offensiva (Pool attacca Meta)
        for p_idx, attacker in enumerate(pool):
            a_opts = PokemonOptions(**attacker.get("options", {}))
            moves = attacker.get("moves", [])
            if not moves: continue
                
            for t_idx, threat in enumerate(meta_threats):
                t_opts = PokemonOptions(**threat.get("options", {}))
                for move in moves:
                    batch_requests.append({
                        "attacker_name": attacker["name"],
                        "defender_name": threat["name"],
                        "move_name": move,
                        "attacker_opts": a_opts,
                        "defender_opts": t_opts,
                        "field_opts": FieldOptions(gameType="Doubles")
                    })
                    mapping_info.append((p_idx, t_idx, True))

        total_requests = len(batch_requests)
        chunk_size = 100
        for i in range(0, total_requests, chunk_size):
            chunk_req = batch_requests[i:i+chunk_size]
            chunk_map = mapping_info[i:i+chunk_size]
            
            results = self.calc.calculate_batch(chunk_req)
            
            for (p_idx, t_idx, is_offensive), res in zip(chunk_map, results):
                if res.get("success", False):
                    calc_res = res["result"]
                    max_dmg = self._parse_max_damage(calc_res)
                    
                    att_spe = calc_res.get("attackerSpe", 0)
                    def_spe = calc_res.get("defenderSpe", 0)
                    
                    if is_offensive:
                        # Pool attacca Meta
                        curr_max = self.offensive_damage_matrix[p_idx].get(t_idx, 0.0)
                        if max_dmg > curr_max:
                            self.offensive_damage_matrix[p_idx][t_idx] = max_dmg
                        self.offensive_speed_matrix[p_idx][t_idx] = (att_spe > def_spe)
                    else:
                        # Meta attacca Pool
                        curr_max = self.damage_matrix[p_idx].get(t_idx, 0.0)
                        if max_dmg > curr_max:
                            self.damage_matrix[p_idx][t_idx] = max_dmg
                        self.speed_matrix[p_idx][t_idx] = (def_spe > att_spe)
                    
            if progress_callback:
                progress_callback(min(100, int((i + chunk_size) / total_requests * 100)))

        # Fill missing values just in case
        for p_idx in range(self.pool_size):
            for t_idx in range(self.threats_size):
                if t_idx not in self.damage_matrix[p_idx]:
                    self.damage_matrix[p_idx][t_idx] = 0.0
                    self.speed_matrix[p_idx][t_idx] = True
                if t_idx not in self.offensive_damage_matrix[p_idx]:
                    self.offensive_damage_matrix[p_idx][t_idx] = 0.0
                    self.offensive_speed_matrix[p_idx][t_idx] = True

    def evaluate_team(self, team_indices: List[int]) -> float:
        """
        Calcola il Punteggio combinato (Vulnerabilità - Offensiva).
        Valore più basso = team migliore.
        """
        if not team_indices:
            return 999999.0
            
        mega_count = sum(1 for p_idx in team_indices if self.is_mega.get(p_idx, False))
        mega_penalty = 0.0
        if mega_count > 2:
            mega_penalty = 99999.0 * (mega_count - 2) # Penalità inaccettabile
            
        vulnerabilita = 0.0
        offensiva = 0.0
        
        # Itera su ogni threat del meta
        for t_idx in range(self.threats_size):
            min_damage_taken = 999999.0
            max_damage_dealt = 0.0
            
            for p_idx in team_indices:
                # 1. Calcolo Difensivo (Vulnerabilità)
                danno_subito = self.damage_matrix[p_idx].get(t_idx, 0.0)
                is_faster = self.speed_matrix[p_idx].get(t_idx, False)
                
                if is_faster:
                    danno_base_subito = danno_subito
                else:
                    danno_base_subito = danno_subito * 2.0
                    
                if danno_base_subito < 33.0: k_def = 1.0
                elif 33.0 <= danno_base_subito < 50.0: k_def = 1.5
                else: k_def = 10.0
                    
                danno_finale_subito = danno_base_subito * k_def
                if danno_finale_subito < min_damage_taken:
                    min_damage_taken = danno_finale_subito
                    
                # 2. Calcolo Offensivo
                danno_fatto = self.offensive_damage_matrix[p_idx].get(t_idx, 0.0)
                is_faster_off = self.offensive_speed_matrix[p_idx].get(t_idx, False)
                
                # Se attacchiamo per primi ha più valore
                danno_base_fatto = danno_fatto * (1.5 if is_faster_off else 1.0)
                
                if danno_base_fatto > max_damage_dealt:
                    max_damage_dealt = danno_base_fatto
                    
            vulnerabilita += min_damage_taken
            offensiva += max_damage_dealt
            
        # Punteggio finale da MINIMIZZARE
        return vulnerabilita - offensiva + mega_penalty

    def hill_climb_generate(self, restarts: int = 10, progress_callback=None) -> Tuple[List[int], float]:
        best_overall_team = []
        best_overall_score = float('inf')
        all_indices = list(range(self.pool_size))
        
        for r in range(restarts):
            current_team = random.sample(all_indices, min(6, self.pool_size))
            current_score = self.evaluate_team(current_team)
            
            improved = True
            while improved:
                improved = False
                external_pool = [i for i in all_indices if i not in current_team]
                
                best_swap_score = current_score
                best_swap_in = -1
                best_swap_out_idx = -1
                
                for i in range(len(current_team)):
                    original_member = current_team[i]
                    for candidate in external_pool:
                        current_team[i] = candidate
                        new_score = self.evaluate_team(current_team)
                        
                        if new_score < best_swap_score:
                            best_swap_score = new_score
                            best_swap_in = candidate
                            best_swap_out_idx = i
                            
                        current_team[i] = original_member
                        
                if best_swap_out_idx != -1:
                    current_team[best_swap_out_idx] = best_swap_in
                    current_score = best_swap_score
                    improved = True
                    
            if current_score < best_overall_score:
                best_overall_score = current_score
                best_overall_team = list(current_team)
                
            if progress_callback:
                progress_callback(int((r + 1) / restarts * 100))
                
        return best_overall_team, best_overall_score

    def hill_climb_optimize(self, initial_team_indices: List[int], max_iter: int = 500, progress_callback=None) -> Tuple[List[int], float, List[int]]:
        current_team = list(initial_team_indices)
        current_score = self.evaluate_team(current_team)
        
        all_indices = list(range(self.pool_size))
        
        iteration = 0
        improved = True
        
        while improved and iteration < max_iter:
            improved = False
            external_pool = [i for i in all_indices if i not in current_team]
            
            best_swap_score = current_score
            best_swap_in = -1
            best_swap_out_idx = -1
            
            for i in range(len(current_team)):
                original_member = current_team[i]
                for candidate in external_pool:
                    current_team[i] = candidate
                    new_score = self.evaluate_team(current_team)
                    
                    if new_score < best_swap_score:
                        best_swap_score = new_score
                        best_swap_in = candidate
                        best_swap_out_idx = i
                        
                    current_team[i] = original_member
                    
            if best_swap_out_idx != -1:
                current_team[best_swap_out_idx] = best_swap_in
                current_score = best_swap_score
                improved = True
                
            iteration += 1
            if progress_callback:
                progress_callback(min(100, int(iteration / max_iter * 100)))
                
        return current_team, current_score, []

    def optimize_evs_for_team(self, team_builds: List[Dict[str, Any]], meta_threats: List[Dict[str, Any]], progress_callback=None) -> List[Dict[str, Any]]:
        """
        Fase 2: Ottimizzazione EV Spreads.
        Crea 6 varianti di EV per ciascun Pokémon del team, calcola una mini-matrice, e sceglie il miglior mix.
        """
        ev_presets = [
            {"hp": 4, "atk": 252, "def": 0, "spa": 0, "spd": 0, "spe": 252},     # Fast Phys Sweeper
            {"hp": 4, "atk": 0, "def": 0, "spa": 252, "spd": 0, "spe": 252},     # Fast Spec Sweeper
            {"hp": 252, "atk": 252, "def": 0, "spa": 0, "spd": 4, "spe": 0},     # Bulky Phys Attacker
            {"hp": 252, "atk": 0, "def": 0, "spa": 252, "spd": 4, "spe": 0},     # Bulky Spec Attacker
            {"hp": 252, "atk": 0, "def": 252, "spa": 0, "spd": 4, "spe": 0},     # Phys Wall
            {"hp": 252, "atk": 0, "def": 4, "spa": 0, "spd": 252, "spe": 0},     # Spec Wall
        ]
        
        # Costruiamo un sub-pool di 36 elementi (6 pokemon * 6 spread)
        sub_pool = []
        for p_idx, member in enumerate(team_builds):
            for s_idx, spread in enumerate(ev_presets):
                variant = dict(member)
                variant["options"] = dict(member.get("options", {}))
                variant["options"]["evs"] = spread
                sub_pool.append(variant)
                
        # Usiamo un'istanza temporanea dell'ottimizzatore per sfruttare evaluate_team
        temp_opt = TeamOptimizer(self.calc)
        temp_opt.build_matrices(sub_pool, meta_threats, progress_callback=progress_callback)
        
        # Hill Climbing sugli EV
        # Iniziamo con un team causale (uno spread random per ogni pokemon)
        current_ev_team = [p_idx * 6 + random.randint(0, 5) for p_idx in range(6)]
        current_score = temp_opt.evaluate_team(current_ev_team)
        
        improved = True
        while improved:
            improved = False
            best_swap_score = current_score
            best_p_idx = -1
            best_spread_idx = -1
            
            for p_idx in range(6):
                original_variant = current_ev_team[p_idx]
                for s_idx in range(6):
                    candidate_variant = p_idx * 6 + s_idx
                    if candidate_variant == original_variant: continue
                        
                    current_ev_team[p_idx] = candidate_variant
                    new_score = temp_opt.evaluate_team(current_ev_team)
                    
                    if new_score < best_swap_score:
                        best_swap_score = new_score
                        best_p_idx = p_idx
                        best_spread_idx = candidate_variant
                        
                    current_ev_team[p_idx] = original_variant # revert
                    
            if best_p_idx != -1:
                current_ev_team[best_p_idx] = best_spread_idx
                current_score = best_swap_score
                improved = True
                
        # Ricostruiamo il team finale
        final_team = []
        for variant_idx in current_ev_team:
            final_team.append(sub_pool[variant_idx])
            
        return final_team, current_score
