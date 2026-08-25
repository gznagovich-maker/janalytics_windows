import requests
from bs4 import BeautifulSoup
from PySide6.QtCore import QThread, Signal
import time

from database.connection import SessionLocal
from database.models import MatchTeam, PokemonSet, TeamVariant
from src.analytics.archetypes import analizza_archetipo_team

def normalize_limitless_pokemon(name: str) -> str:
    name = name.lower()
    if name.startswith("alolan "): name = name.replace("alolan ", "") + "alola"
    elif name.startswith("galarian "): name = name.replace("galarian ", "") + "galar"
    elif name.startswith("hisuian "): name = name.replace("hisuian ", "") + "hisui"
    elif name.startswith("paldean "): name = name.replace("paldean ", "") + "paldea"
    elif name.startswith("eternal flower "): name = "floetteeternal"
    
    if " rotom" in name:
        name = "rotom" + name.replace(" rotom", "")
        
    if name == "urshifu rapid strike": name = "urshifurapidstrike"
    elif name == "urshifu single strike": name = "urshifu"
    elif name == "ogerpon hearthflame": name = "ogerponhearthflame"
    elif name == "ogerpon wellspring": name = "ogerponwellspring"
    elif name == "ogerpon cornerstone": name = "ogerponcornerstone"
    
    name = name.replace(" ", "").replace("-", "").replace(".", "").replace("'", "")
    
    if name == "mimikyubusted": name = "mimikyu"
    if name == "eiscuenoice": name = "eiscue"
    return name

def normalize_replay_pokemon(sp: str) -> str:
    sp = sp.lower()
    if sp == "floettemega": return "floetteeternal"
    if sp == "sinistchamasterpiece": return "sinistcha"
    if sp.endswith("megax"): return sp[:-5]
    if sp.endswith("megay"): return sp[:-5]
    if sp.endswith("mega"): return sp[:-4]
    return sp

def build_replay_core_dict(session):
    variants = session.query(TeamVariant).all()
    sets = session.query(PokemonSet).all()
    
    set_species = {s.id: normalize_replay_pokemon(s.species_id) for s in sets if s.species_id}
    
    variant_species = {}
    for v in variants:
        v_sp = set()
        for sid in v.pokemon_set_ids:
            if sid in set_species:
                v_sp.add(set_species[sid])
        if len(v_sp) == 6:
            variant_species[v.id] = frozenset(v_sp)
            
    match_teams = session.query(MatchTeam.id, MatchTeam.team_variant_id).all()
    
    replay_core_to_team_ids = {}
    for t_id, v_id in match_teams:
        if v_id in variant_species:
            fs = variant_species[v_id]
            if fs not in replay_core_to_team_ids:
                replay_core_to_team_ids[fs] = []
            replay_core_to_team_ids[fs].append(t_id)
            
    return replay_core_to_team_ids

class LimitlessFormatsWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            url = "https://play.limitlesstcg.com/api/games"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            games = response.json()
            formats = {}
            for g in games:
                if g.get('id') == 'VGC':
                    formats = g.get('formats', {})
                    break
            self.finished.emit(formats)
        except Exception as e:
            self.error.emit(str(e))

class MultiTournamentWorker(QThread):
    progress = Signal(int, int, str)
    partial_results = Signal(dict)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, regulation_filter="", count=5):
        super().__init__()
        self.regulation_filter = regulation_filter
        if self.regulation_filter == "tutti" or not self.regulation_filter:
            self.regulation_filter = ""
        self.count = count

    def run(self):
        try:
            self.progress.emit(0, 0, "Caricamento database replay locale in memoria...")
            session = SessionLocal()
            replay_cores = build_replay_core_dict(session)
            
            self.progress.emit(0, 0, "Ricerca tornei completati...")
            url = "https://play.limitlesstcg.com/api/tournaments"
            params = {'game': 'VGC', 'limit': max(50, self.count)}
            if self.regulation_filter:
                params['format'] = self.regulation_filter
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            tournaments_data = response.json()
            
            tournaments = []
            for idx, t in enumerate(tournaments_data):
                if idx >= self.count:
                    break
                tournaments.append({
                    'id': t.get('id'),
                    'date': t.get('date', ''),
                    'name': t.get('name', ''),
                    'organizer': str(t.get('organizerId', '')),
                    'players': t.get('players', 0),
                    'winner': '', 
                    'format': t.get('format', 'VGC')
                })
            
            if not tournaments:
                session.close()
                self.finished.emit({'tournaments': []})
                return
                
            global_pokemon_usage = {}
            global_team_usage = {}
            total_players_with_team = 0
            
            builds = {}
            
            for idx, t in enumerate(tournaments):
                self.progress.emit(idx, len(tournaments), f"Scaricamento teamlist API: {t['name']}...")
                s_url = f"https://play.limitlesstcg.com/api/tournaments/{t['id']}/standings"
                try:
                    s_resp = requests.get(s_url, timeout=10)
                    if s_resp.status_code == 200:
                        standings = s_resp.json()
                        if standings and isinstance(standings, list):
                            if t['winner'] == '' and len(standings) > 0:
                                t['winner'] = standings[0].get('name', '')
                            
                            for player in standings:
                                decklist = player.get('decklist')
                                if decklist and isinstance(decklist, list):
                                    team = []
                                    total_players_with_team += 1
                                    
                                    for p in decklist:
                                        pname = p.get('name')
                                        if not pname: continue
                                        team.append(pname)
                                        
                                        global_pokemon_usage[pname] = global_pokemon_usage.get(pname, 0) + 1
                                        
                                        if pname not in builds:
                                            builds[pname] = {'items': {}, 'abilities': {}, 'natures': {}, 'evs': {}, 'moves': {}, 'count': 0}
                                        
                                        b = builds[pname]
                                        b['count'] += 1
                                        
                                        item = p.get('item')
                                        if item: b['items'][item] = b['items'].get(item, 0) + 1
                                        
                                        ability = p.get('ability')
                                        if ability: b['abilities'][ability] = b['abilities'].get(ability, 0) + 1
                                        
                                        nature = p.get('nature')
                                        if nature: b['natures'][nature] = b['natures'].get(nature, 0) + 1
                                        
                                        evs = p.get('evs')
                                        if evs: b['evs'][evs] = b['evs'].get(evs, 0) + 1
                                        
                                        moves = p.get('attacks', [])
                                        for m in moves:
                                            b['moves'][m] = b['moves'].get(m, 0) + 1
                                            
                                    if len(team) == 6:
                                        team_key = tuple(sorted(team))
                                        global_team_usage[team_key] = global_team_usage.get(team_key, 0) + 1
                                        
                except Exception:
                    pass
                
                sorted_pkmn = sorted(global_pokemon_usage.items(), key=lambda x: x[1], reverse=True)
                
                # Calcola archetipi per le team core
                sorted_teams = sorted(global_team_usage.items(), key=lambda x: x[1], reverse=True)
                team_list_with_arch = []
                for team_tuple, count in sorted_teams:
                    norm_team = frozenset([normalize_limitless_pokemon(x) for x in team_tuple])
                    archetype_str = "Sconosciuto (Nessun replay locale)"
                    if norm_team in replay_cores:
                        arch_res = analizza_archetipo_team(list(norm_team), replay_cores[norm_team], session)
                        archetype_str = arch_res
                    team_list_with_arch.append((team_tuple, count, archetype_str))
                
                result = {
                    'tournaments': tournaments,
                    'pokemon_usage': sorted_pkmn,
                    'team_usage': team_list_with_arch,
                    'total_teams': total_players_with_team,
                    'builds': builds
                }
                self.partial_results.emit(result)
                time.sleep(0.5)
                
            self.progress.emit(len(tournaments), len(tournaments), "Completato!")
            session.close()
            
            sorted_pkmn = sorted(global_pokemon_usage.items(), key=lambda x: x[1], reverse=True)
            sorted_teams = sorted(global_team_usage.items(), key=lambda x: x[1], reverse=True)
            # Ricalcola una volta finale per sicurezza
            session = SessionLocal()
            team_list_with_arch = []
            for team_tuple, count in sorted_teams:
                norm_team = frozenset([normalize_limitless_pokemon(x) for x in team_tuple])
                archetype_str = "Sconosciuto (Nessun replay locale)"
                if norm_team in replay_cores:
                    arch_res = analizza_archetipo_team(list(norm_team), replay_cores[norm_team], session)
                    archetype_str = arch_res
                team_list_with_arch.append((team_tuple, count, archetype_str))
            session.close()
                
            result = {
                'tournaments': tournaments,
                'pokemon_usage': sorted_pkmn,
                'team_usage': team_list_with_arch,
                'total_teams': total_players_with_team,
                'builds': builds
            }
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(str(e))

class TournamentDetailWorker(QThread):
    progress = Signal(int, int, str)
    partial_results = Signal(dict)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, tournament_id):
        super().__init__()
        self.tournament_id = tournament_id

    def run(self):
        try:
            self.progress.emit(0, 0, "Caricamento database replay locale in memoria...")
            session = SessionLocal()
            replay_cores = build_replay_core_dict(session)
            
            self.progress.emit(0, 0, "Caricamento teamlist API in corso...")
            url = f"https://play.limitlesstcg.com/api/tournaments/{self.tournament_id}/standings"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            standings = response.json()
            
            players = []
            pokemon_usage = {}
            team_usage = {}
            total_players_with_team = 0
            builds = {}
            
            for player in standings:
                name = player.get('name', '')
                country = player.get('country', '')
                placing = player.get('placing', 0)
                if placing is None:
                    placing = 9999
                decklist = player.get('decklist')
                
                team = []
                has_list = False
                
                if decklist and isinstance(decklist, list):
                    has_list = True
                    total_players_with_team += 1
                    
                    for p in decklist:
                        pname = p.get('name')
                        if not pname: continue
                        team.append(pname)
                        
                        pokemon_usage[pname] = pokemon_usage.get(pname, 0) + 1
                        
                        if pname not in builds:
                            builds[pname] = {'items': {}, 'abilities': {}, 'natures': {}, 'evs': {}, 'moves': {}, 'count': 0}
                        
                        b = builds[pname]
                        b['count'] += 1
                        
                        item = p.get('item')
                        if item: b['items'][item] = b['items'].get(item, 0) + 1
                        
                        ability = p.get('ability')
                        if ability: b['abilities'][ability] = b['abilities'].get(ability, 0) + 1
                        
                        nature = p.get('nature')
                        if nature: b['natures'][nature] = b['natures'].get(nature, 0) + 1
                        
                        evs = p.get('evs')
                        if evs: b['evs'][evs] = b['evs'].get(evs, 0) + 1
                        
                        moves = p.get('attacks', [])
                        for m in moves:
                            b['moves'][m] = b['moves'].get(m, 0) + 1
                            
                    if len(team) == 6:
                        team_key = tuple(sorted(team))
                        team_usage[team_key] = team_usage.get(team_key, 0) + 1
                
                players.append({
                    'placing': str(placing),
                    'name': name,
                    'country': country,
                    'team': team,
                    'has_list': has_list
                })
            
            sorted_pkmn = sorted(pokemon_usage.items(), key=lambda x: x[1], reverse=True)
            sorted_teams = sorted(team_usage.items(), key=lambda x: x[1], reverse=True)
            
            team_list_with_arch = []
            for team_tuple, count in sorted_teams:
                norm_team = frozenset([normalize_limitless_pokemon(x) for x in team_tuple])
                archetype_str = "Sconosciuto (Nessun replay locale)"
                if norm_team in replay_cores:
                    arch_res = analizza_archetipo_team(list(norm_team), replay_cores[norm_team], session)
                    archetype_str = arch_res
                team_list_with_arch.append((team_tuple, count, archetype_str))
            
            result = {
                'id': self.tournament_id,
                'players': players,
                'pokemon_usage': sorted_pkmn,
                'team_usage': team_list_with_arch,
                'total_teams': total_players_with_team,
                'builds': builds
            }
            
            self.progress.emit(100, 100, "Completato!")
            session.close()
            self.finished.emit(result)
            
        except Exception as e:
            self.error.emit(str(e))
