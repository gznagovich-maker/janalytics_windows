"""
dashboard_stats.py
==================
Statistiche pure (nessuna dipendenza Qt/rete) calcolate sulla lista di
DashboardGame. Replicano la logica delle formule del template PASRS:

  - GameFilter            : filtri del tab "Game By Game" (AND tra i filtri)
  - usage_stats           : tab "Usage" (Win%, Lead Win%, Mega Win%, Leads)
  - matchup_stats         : tab "Matchup Stats" (Best/Worst, Attendance)
  - lead_pair_games       : dati del pop-up "team avversari per coppia lead"
  - native_move_usage     : fallback per "Move Usage" se il foglio non ha grafici

Tutti i Pokémon sono identificati dalla stringa canonica "Specie + Forma".
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from src.domain.sheet_dashboard.models import DashboardGame, MoveSlice, MoveUsageChart

ANY = "-any-"
NO_MEGA = "(nessuna)"

LeadPair = Tuple[str, str]


# ── Record W/L ────────────────────────────────────────────────────

@dataclass
class Record:
    wins: int = 0
    games: int = 0

    def add(self, won: Optional[bool]):
        self.games += 1
        if won:
            self.wins += 1

    @property
    def pct(self) -> Optional[float]:
        return (self.wins / self.games) if self.games else None

    def pct_text(self, decimals: int = 0) -> str:
        p = self.pct
        return "N/A" if p is None else f"{p * 100:.{decimals}f}%"


def lead_pair(lead: List[str]) -> Optional[LeadPair]:
    if len(lead) < 2:
        return None
    a, b = sorted(lead[:2])
    return (a, b)


# ── Filtri "Game By Game" ─────────────────────────────────────────

@dataclass
class GameFilter:
    result: str = ANY
    opp_pokemon: str = ANY
    my_lead: str = ANY
    my_back: str = ANY
    opp_lead: str = ANY
    opp_back: str = ANY
    my_mega: str = ANY
    opp_mega: str = ANY
    ots: str = ANY                    # "-any-" | "YES" | "NO"
    min_elo: Optional[int] = None

    def is_default(self) -> bool:
        return self == GameFilter()

    def matches(self, g: DashboardGame) -> bool:
        if self.result != ANY and g.result != self.result:
            return False
        if self.ots != ANY:
            if g.ots is None or g.ots != (self.ots == "YES"):
                return False
        if self.min_elo is not None:
            elo = g.opp_elo_value
            if elo is None or elo < self.min_elo:
                return False

        poke_filters = (self.opp_pokemon, self.my_lead, self.my_back,
                        self.opp_lead, self.opp_back, self.my_mega, self.opp_mega)
        if all(f == ANY for f in poke_filters):
            return True
        s = g.summary
        if s is None:
            return False
        if self.opp_pokemon != ANY and self.opp_pokemon not in s.opp.team:
            return False
        if self.my_lead != ANY and self.my_lead not in s.me.lead:
            return False
        if self.my_back != ANY and self.my_back not in s.me.back:
            return False
        if self.opp_lead != ANY and self.opp_lead not in s.opp.lead:
            return False
        if self.opp_back != ANY and self.opp_back not in s.opp.back:
            return False
        if self.my_mega != ANY and (s.me.mega or NO_MEGA) != self.my_mega:
            return False
        if self.opp_mega != ANY and (s.opp.mega or NO_MEGA) != self.opp_mega:
            return False
        return True


def apply_filter(games: List[DashboardGame], flt: GameFilter) -> List[DashboardGame]:
    return [g for g in games if flt.matches(g)]


def filter_options(games: List[DashboardGame]) -> Dict[str, List[str]]:
    """Valori disponibili per ogni combo-box dei filtri."""
    sets: Dict[str, set] = defaultdict(set)
    for g in games:
        s = g.summary
        if not s:
            continue
        sets["opp_pokemon"].update(s.opp.team)
        sets["my_lead"].update(s.me.lead)
        sets["my_back"].update(s.me.back)
        sets["opp_lead"].update(s.opp.lead)
        sets["opp_back"].update(s.opp.back)
        sets["my_mega"].add(s.me.mega or NO_MEGA)
        sets["opp_mega"].add(s.opp.mega or NO_MEGA)
    out = {k: [ANY] + sorted(v, key=str.lower) for k, v in sets.items()}
    out["result"] = [ANY, "Win", "Loss"]
    out["ots"] = [ANY, "YES", "NO"]
    for k in ("opp_pokemon", "my_lead", "my_back", "opp_lead", "opp_back", "my_mega", "opp_mega"):
        out.setdefault(k, [ANY])
    return out


# ── Usage ─────────────────────────────────────────────────────────

@dataclass
class PokemonUsage:
    pokemon: str
    brought: Record = field(default_factory=Record)
    lead: Record = field(default_factory=Record)
    mega: Optional[Record] = None


@dataclass
class UsageStats:
    total: Record = field(default_factory=Record)
    ots: Record = field(default_factory=Record)
    cts: Record = field(default_factory=Record)
    pokemon: List[PokemonUsage] = field(default_factory=list)
    common_leads: List[Tuple[LeadPair, Record]] = field(default_factory=list)
    best_leads: List[Tuple[LeadPair, Record]] = field(default_factory=list)


def my_team_order(games: List[DashboardGame]) -> List[str]:
    """Ordine dei Pokémon del giocatore: team preview più frequente, poi gli altri."""
    teams = Counter(tuple(g.summary.me.team) for g in games if g.summary and g.summary.me.team)
    order: List[str] = list(teams.most_common(1)[0][0]) if teams else []
    freq = Counter(k for g in games if g.summary for k in g.summary.me.team)
    for k, _ in freq.most_common():
        if k not in order:
            order.append(k)
    return order


def usage_stats(games: List[DashboardGame], top_n: int = 6) -> UsageStats:
    st = UsageStats()
    per: Dict[str, PokemonUsage] = {}
    leads: Dict[LeadPair, Record] = defaultdict(Record)

    for g in games:
        won = g.won
        if won is None:
            continue
        st.total.add(won)
        if g.ots is True:
            st.ots.add(won)
        elif g.ots is False:
            st.cts.add(won)
        s = g.summary
        if not s:
            continue
        for k in dict.fromkeys(s.me.lead + s.me.back):
            per.setdefault(k, PokemonUsage(k)).brought.add(won)
        for k in s.me.lead:
            per.setdefault(k, PokemonUsage(k)).lead.add(won)
        if s.me.mega:
            pu = per.setdefault(s.me.mega, PokemonUsage(s.me.mega))
            pu.mega = pu.mega or Record()
            pu.mega.add(won)
        pair = lead_pair(s.me.lead)
        if pair:
            leads[pair].add(won)

    order = my_team_order(games)
    st.pokemon = [per.get(k, PokemonUsage(k)) for k in order]
    st.pokemon += [v for k, v in per.items() if k not in order]

    items = list(leads.items())
    st.common_leads = sorted(items, key=lambda x: (-x[1].games, -x[1].wins, x[0]))[:top_n]
    st.best_leads = sorted(items, key=lambda x: (-(x[1].pct or 0), -x[1].wins, -x[1].games, x[0]))[:top_n]
    return st


# ── Pop-up lead ───────────────────────────────────────────────────

def lead_pair_games(games: List[DashboardGame], pair: LeadPair) -> List[DashboardGame]:
    """Tutti i game in cui la coppia (non ordinata) è stata la lead del giocatore."""
    target = tuple(sorted(pair))
    return [g for g in games if g.summary and lead_pair(g.summary.me.lead) == target]


# ── Matchup Stats ─────────────────────────────────────────────────

@dataclass
class MatchupEntry:
    """
    Formule del template (verificate sul foglio mock):
      Best/Worst  → "beat X of Y" : X = vittorie quando l'avversario lo ha portato,
                                     Y = game in cui l'avversario lo ha portato
      Attendance  → "seen X of Y" : X = game in cui è stato portato,
                                     Y = game contro team che lo contenevano
    """
    pokemon: str
    games: int = 0          # game contro team che lo contenevano (team preview)
    brought: int = 0        # game in cui l'avversario lo ha portato
    wins_brought: int = 0   # vittorie nei game in cui è stato portato
    wins_team: int = 0      # vittorie nei game in cui era in team

    @property
    def win_pct(self) -> float:
        return self.wins_brought / self.brought if self.brought else 0.0

    @property
    def attendance_pct(self) -> float:
        return self.brought / self.games if self.games else 0.0


@dataclass
class MatchupStats:
    best: List[MatchupEntry] = field(default_factory=list)
    worst: List[MatchupEntry] = field(default_factory=list)
    highest_attendance: List[MatchupEntry] = field(default_factory=list)
    lowest_attendance: List[MatchupEntry] = field(default_factory=list)
    all: Dict[str, MatchupEntry] = field(default_factory=dict)


def matchup_stats(games: List[DashboardGame], min_games: int = 4, top_n: int = 5) -> MatchupStats:
    """
    Soglia minima (come nel template, "seen at least a few times"):
      - Best/Worst     : Pokémon portato dall'avversario in >= min_games game
      - Attendance     : Pokémon presente nel team avversario in >= min_games game
    Parità: a pari percentuale vince il campione più ampio.
    """
    acc: Dict[str, MatchupEntry] = {}
    for g in games:
        s, won = g.summary, g.won
        if not s or won is None:
            continue
        brought = set(s.opp.lead) | set(s.opp.back)
        for k in dict.fromkeys(s.opp.team):
            e = acc.setdefault(k, MatchupEntry(k))
            e.games += 1
            e.wins_team += 1 if won else 0
            if k in brought:
                e.brought += 1
                e.wins_brought += 1 if won else 0

    ms = MatchupStats(all=acc)
    by_brought = [e for e in acc.values() if e.brought >= min_games]
    by_team = [e for e in acc.values() if e.games >= min_games]
    ms.best = sorted(by_brought, key=lambda e: (-e.win_pct, -e.brought, e.pokemon))[:top_n]
    ms.worst = sorted(by_brought, key=lambda e: (e.win_pct, -e.brought, e.pokemon))[:top_n]
    ms.highest_attendance = sorted(by_team, key=lambda e: (-e.attendance_pct, -e.games, e.pokemon))[:top_n]
    ms.lowest_attendance = sorted(by_team, key=lambda e: (e.attendance_pct, -e.games, e.pokemon))[:top_n]
    return ms


# ── Move Usage (fallback nativo) ──────────────────────────────────

def native_move_usage(games: List[DashboardGame]) -> List[MoveUsageChart]:
    per: Dict[str, Counter] = defaultdict(Counter)
    for g in games:
        if not g.summary:
            continue
        for k, c in g.summary.me.moves.items():
            per[k].update(c)
    charts = []
    for k in my_team_order(games):
        if per.get(k):
            charts.append(MoveUsageChart(
                pokemon=k,
                slices=[MoveSlice(m, float(n)) for m, n in per[k].most_common()],
                source="native",
            ))
    return charts

# ── Team Analysis ──

@dataclass
class TeamAnalysisEntry:
    group: Tuple[str, ...]
    games: int = 0
    wins: int = 0
    match_games: List['DashboardGame'] = field(default_factory=list)
    sub_entries: List['TeamAnalysisEntry'] = field(default_factory=list)

    @property
    def win_pct(self) -> float:
        return self.wins / self.games if self.games else 0.0

@dataclass
class TeamAnalysisCategory:
    best: List[TeamAnalysisEntry] = field(default_factory=list)
    worst: List[TeamAnalysisEntry] = field(default_factory=list)
    most_common: List[TeamAnalysisEntry] = field(default_factory=list)
    all_entries: List[TeamAnalysisEntry] = field(default_factory=list)

@dataclass
class TeamAnalysisStats:
    cores: TeamAnalysisCategory = field(default_factory=TeamAnalysisCategory)
    variants: TeamAnalysisCategory = field(default_factory=TeamAnalysisCategory)

def team_analysis_stats(games: List[DashboardGame], n_core: int = 2, m_dist: int = 2, min_apps: int = 2, top_n: int = 5) -> TeamAnalysisStats:
    from itertools import combinations
    cores_dict: Dict[Tuple[str, ...], TeamAnalysisEntry] = {}
    variants_dict: Dict[frozenset, TeamAnalysisEntry] = {}
    
    for g in games:
        if not g.summary or g.won is None:
            continue
            
        opp_brought = g.summary.opp.lead + g.summary.opp.back
        sp_brought = sorted(set(opp_brought))
        if len(sp_brought) >= n_core:
            for c in combinations(sp_brought, n_core):
                e = cores_dict.setdefault(c, TeamAnalysisEntry(group=c))
                e.games += 1
                e.wins += 1 if g.won else 0
                e.match_games.append(g)
                
        opp_team = g.summary.opp.team
        if opp_team:
            sp_team = sorted(set(opp_team))
            v_set = frozenset(sp_team)
            e = variants_dict.setdefault(v_set, TeamAnalysisEntry(group=tuple(sp_team)))
            e.games += 1
            e.wins += 1 if g.won else 0
            e.match_games.append(g)
            
    def _fill_category(source: Dict[Any, TeamAnalysisEntry]) -> TeamAnalysisCategory:
        cat = TeamAnalysisCategory()
        all_vals = list(source.values())
        filtered = [v for v in all_vals if v.games >= min_apps]
        target = filtered if filtered else all_vals
        cat.most_common = sorted(all_vals, key=lambda x: (-x.games, -x.win_pct, x.group))[:top_n]
        cat.best = sorted(target, key=lambda x: (-x.win_pct, -x.games, x.group))[:top_n]
        cat.worst = sorted(target, key=lambda x: (x.win_pct, -x.games, x.group))[:top_n]
        cat.all_entries = sorted(all_vals, key=lambda x: (-x.games, -x.win_pct, x.group))
        return cat
        
    st = TeamAnalysisStats()
    st.cores = _fill_category(cores_dict)
    
    merged_variants = {}
    v_list = list(variants_dict.values())
    v_list.sort(key=lambda x: x.games, reverse=True)
    assigned = set()
    for i, v in enumerate(v_list):
        if i in assigned: continue
        v_set_i = set(v.group)
        merged_e = TeamAnalysisEntry(group=v.group, games=v.games, wins=v.wins)
        merged_e.match_games.extend(v.match_games)
        merged_e.sub_entries.append(v)
        
        for j in range(i+1, len(v_list)):
            if j in assigned: continue
            v_set_j = set(v_list[j].group)
            intersect_len = len(v_set_i.intersection(v_set_j))
            dist = max(len(v_set_i), len(v_set_j)) - intersect_len
            if dist <= m_dist:
                merged_e.games += v_list[j].games
                merged_e.wins += v_list[j].wins
                merged_e.match_games.extend(v_list[j].match_games)
                merged_e.sub_entries.append(v_list[j])
                assigned.add(j)
        merged_variants[merged_e.group] = merged_e
        
    st.variants = _fill_category(merged_variants)
    return st
