"""
slot_analysis.py
================
Analisi per decidere QUALE slot del team sostituire e CON COSA, calcolate
sui replay linkati nel foglio (stesso pool delle altre tab della dashboard).

  1. dead_weight_index      — Pick Rate: chi resta in panchina (anello debole)
  2. ko_suffered_analysis   — KO subiti per tipo di mossa / killer (debolezze strutturali)
  3. negative_matchup_matrix— Win Rate condizionato ai Pokémon avversari (counter)
  4. switch_in_damage       — HP persi nel turno di ingresso (sinergia difensiva)
  5. ko_tradeoff            — KO a favore generati dal Pokémon da scartare
  +  evaluate_candidate     — verifica di un candidato sostitutivo

Funzioni pure (nessuna dipendenza Qt). Identità Pokémon: "Specie + Forma".
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from src.domain.sheet_dashboard.models import DashboardGame, KoEvent, SwitchInEvent
from src.domain.type_chart import TYPE_DATA, get_multiplier

UNKNOWN_TYPE = "Sconosciuto"
INDIRECT = "Danno indiretto"


def _id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _valid(games: List[DashboardGame]) -> List[DashboardGame]:
    return [g for g in games if g.summary is not None]


# ── Lookup DB (tipi mosse / specie) ───────────────────────────────

@lru_cache(maxsize=4096)
def move_type(move_name: str) -> str:
    if not move_name:
        return UNKNOWN_TYPE
    try:
        from database.connection import SessionLocal
        from database.models_v2 import MoveV2
        with SessionLocal() as s:
            m = s.get(MoveV2, _id(move_name))
            return m.type if m and m.type else UNKNOWN_TYPE
    except Exception:
        return UNKNOWN_TYPE


@lru_cache(maxsize=2048)
def species_types(species: str) -> Tuple[str, ...]:
    try:
        from database.connection import SessionLocal
        from database.models_v2 import PokemonSpeciesV2
        with SessionLocal() as s:
            p = s.get(PokemonSpeciesV2, _id(species))
            if p is None:
                p = s.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species).first()
            if p:
                return tuple(t for t in (p.type1, p.type2) if t)
    except Exception:
        pass
    return tuple()


def resisting_types(atk_type: str) -> Tuple[List[str], List[str]]:
    """Tipi difensivi che resistono / sono immuni a un tipo d'attacco."""
    res = [t for t, d in TYPE_DATA.items() if atk_type in d["resistances"]]
    imm = [t for t, d in TYPE_DATA.items() if atk_type in d["immunities"]]
    return res, imm


# ── 1. Dead Weight Index ──────────────────────────────────────────

@dataclass
class DeadWeightRow:
    pokemon: str
    in_team: int = 0
    brought: int = 0
    brought_wins: int = 0
    brought_decided: int = 0
    below_threshold: bool = False

    @property
    def pick_rate(self) -> float:
        return self.brought / self.in_team if self.in_team else 0.0

    @property
    def win_pct_brought(self) -> Optional[float]:
        return self.brought_wins / self.brought_decided if self.brought_decided else None


def dead_weight_index(games: List[DashboardGame], threshold: float = 0.25) -> Tuple[List[DeadWeightRow], Optional[str]]:
    rows: Dict[str, DeadWeightRow] = {}
    for g in _valid(games):
        me = g.summary.me
        brought = set(me.lead) | set(me.back)
        for p in set(me.team):
            r = rows.setdefault(p, DeadWeightRow(pokemon=p))
            r.in_team += 1
            if p in brought:
                r.brought += 1
                if g.won is not None:
                    r.brought_decided += 1
                    r.brought_wins += 1 if g.won else 0
    out = sorted(rows.values(), key=lambda r: (r.pick_rate, -r.in_team, r.pokemon))
    for r in out:
        r.below_threshold = r.pick_rate < threshold
    # Il candidato "dead weight" deve essere un membro stabile del team
    stable = [r for r in out if r.in_team >= max(1, max((x.in_team for x in out), default=0) // 2)]
    candidate = stable[0].pokemon if stable else (out[0].pokemon if out else None)
    return out, candidate


# ── 2. KO subiti ──────────────────────────────────────────────────

@dataclass
class KoRecord:
    game: DashboardGame
    event: KoEvent
    move_type: str


@dataclass
class KoSufferedStats:
    total: int = 0
    direct: int = 0
    indirect: int = 0
    by_type: List[Tuple[str, int, float]] = field(default_factory=list)       # (tipo, n, % sul totale)
    by_killer: List[Tuple[str, int, List[str]]] = field(default_factory=list) # (killer, n, mosse)
    by_victim: List[Tuple[str, int]] = field(default_factory=list)
    structural_types: List[str] = field(default_factory=list)
    structural_pair: Optional[Tuple[str, str, float]] = None
    required_resistances: Dict[str, Tuple[List[str], List[str]]] = field(default_factory=dict)
    records: List[KoRecord] = field(default_factory=list)


def ko_suffered_analysis(games: List[DashboardGame], structural_threshold: float = 0.40) -> KoSufferedStats:
    st = KoSufferedStats()
    type_c: Counter = Counter()
    killer_c: Counter = Counter()
    killer_moves: Dict[str, Counter] = defaultdict(Counter)
    victim_c: Counter = Counter()
    for g in _valid(games):
        for ko in g.summary.me.kos_suffered:
            st.total += 1
            victim_c[ko.victim] += 1
            if ko.indirect or not ko.move:
                st.indirect += 1
                t = INDIRECT
            else:
                st.direct += 1
                t = move_type(ko.move)
                if ko.killer:
                    killer_c[ko.killer] += 1
                    killer_moves[ko.killer][ko.move] += 1
            type_c[t] += 1
            st.records.append(KoRecord(game=g, event=ko, move_type=t))
    if not st.total:
        return st
    st.by_type = [(t, n, n / st.total) for t, n in type_c.most_common()]
    st.by_killer = [(k, n, [m for m, _ in killer_moves[k].most_common()]) for k, n in killer_c.most_common()]
    st.by_victim = victim_c.most_common()

    real = [(t, n, p) for t, n, p in st.by_type if t not in (INDIRECT, UNKNOWN_TYPE)]
    st.structural_types = [t for t, _, p in real if p >= structural_threshold]
    if not st.structural_types and len(real) >= 2:
        (t1, _, p1), (t2, _, p2) = real[0], real[1]
        if p1 + p2 >= structural_threshold:
            st.structural_pair = (t1, t2, p1 + p2)
    weak = st.structural_types or (list(st.structural_pair[:2]) if st.structural_pair else [])
    st.required_resistances = {t: resisting_types(t) for t in weak}
    return st


def weak_types(st: KoSufferedStats) -> List[str]:
    return st.structural_types or (list(st.structural_pair[:2]) if st.structural_pair else [])


# ── 3. Matrice matchup negativi ───────────────────────────────────

@dataclass
class MatchupRow:
    pokemon: str
    preview_games: int = 0
    preview_wins: int = 0
    brought_games: int = 0
    brought_wins: int = 0
    flagged: bool = False

    @property
    def preview_wr(self) -> Optional[float]:
        return self.preview_wins / self.preview_games if self.preview_games else None

    @property
    def brought_wr(self) -> Optional[float]:
        return self.brought_wins / self.brought_games if self.brought_games else None


def negative_matchup_matrix(games: List[DashboardGame], wr_threshold: float = 0.40,
                            min_games: int = 3) -> Tuple[List[MatchupRow], Optional[float]]:
    rows: Dict[str, MatchupRow] = {}
    decided = [g for g in _valid(games) if g.won is not None]
    overall = (sum(1 for g in decided if g.won) / len(decided)) if decided else None
    for g in decided:
        opp = g.summary.opp
        brought = set(opp.lead) | set(opp.back)
        for p in set(opp.team):
            r = rows.setdefault(p, MatchupRow(pokemon=p))
            r.preview_games += 1
            r.preview_wins += 1 if g.won else 0
            if p in brought:
                r.brought_games += 1
                r.brought_wins += 1 if g.won else 0
    out = [r for r in rows.values() if r.preview_games >= min_games]
    for r in out:
        r.flagged = r.preview_wr is not None and r.preview_wr < wr_threshold
    out.sort(key=lambda r: (r.preview_wr if r.preview_wr is not None else 1.0, -r.preview_games, r.pokemon))
    return out, overall


# ── 4. Switch-in e danni in entrata ───────────────────────────────

@dataclass
class SwitchRecord:
    game: DashboardGame
    event: SwitchInEvent


@dataclass
class SwitchRow:
    pokemon: str
    records: List[SwitchRecord] = field(default_factory=list)
    over_threshold: int = 0
    hit_types: Counter = field(default_factory=Counter)

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def avg_lost(self) -> float:
        return sum(r.event.hp_lost for r in self.records) / self.count if self.count else 0.0

    @property
    def pct_over(self) -> float:
        return self.over_threshold / self.count if self.count else 0.0


def switch_in_damage(games: List[DashboardGame], hp_threshold: float = 50.0,
                     core: Optional[str] = None) -> List[SwitchRow]:
    rows: Dict[str, SwitchRow] = {}
    for g in _valid(games):
        for ev in g.summary.me.switch_ins:
            if core and ev.replaced != core:
                continue
            r = rows.setdefault(ev.pokemon, SwitchRow(pokemon=ev.pokemon))
            r.records.append(SwitchRecord(game=g, event=ev))
            if ev.hp_lost > hp_threshold:
                r.over_threshold += 1
            for _att, mv in ev.hits:
                r.hit_types[move_type(mv)] += 1
    return sorted(rows.values(), key=lambda r: (-r.pct_over, -r.avg_lost, r.pokemon))


# ── 5. Trade-off dei KO ───────────────────────────────────────────

@dataclass
class KoTargetRow:
    target: str
    count: int
    moves: List[str]
    exclusive: bool
    other_killers: List[str] = field(default_factory=list)


def my_kos(games: List[DashboardGame]) -> List[Tuple[DashboardGame, KoEvent]]:
    """KO a favore: KO subiti dall'avversario con killer del mio lato."""
    out = []
    for g in _valid(games):
        for ko in g.summary.opp.kos_suffered:
            if ko.killer and not ko.indirect:
                out.append((g, ko))
    return out


def ko_tradeoff(games: List[DashboardGame], pokemon: str) -> Tuple[List[KoTargetRow], int, Counter]:
    kos = my_kos(games)
    totals = Counter(ko.killer for _, ko in kos)
    killers_by_target: Dict[str, set] = defaultdict(set)
    for _, ko in kos:
        killers_by_target[ko.victim].add(ko.killer)
    tgt_c: Counter = Counter()
    tgt_moves: Dict[str, Counter] = defaultdict(Counter)
    for _, ko in kos:
        if ko.killer == pokemon:
            tgt_c[ko.victim] += 1
            tgt_moves[ko.victim][ko.move] += 1
    rows = []
    for t, n in tgt_c.most_common():
        others = sorted(k for k in killers_by_target[t] if k != pokemon)
        rows.append(KoTargetRow(target=t, count=n, moves=[m for m, _ in tgt_moves[t].most_common()],
                                exclusive=not others, other_killers=others))
    return rows, totals.get(pokemon, 0), totals


# ── + Valutazione candidato ───────────────────────────────────────

@dataclass
class CandidateCheck:
    species: str
    types: Tuple[str, ...] = ()
    type_checks: List[Tuple[str, float]] = field(default_factory=list)        # (tipo debole, moltiplicatore)
    counter_damage: List[Tuple[str, Optional[str], float, str]] = field(default_factory=list)  # (bersaglio, mossa, max%, tier)
    target_damage: List[Tuple[str, Optional[str], float, str]] = field(default_factory=list)


def evaluate_candidate(paste: str, weak: List[str], counters: List[str], ko_targets: List[str]) -> List[CandidateCheck]:
    from src.domain.sheet_dashboard import meta_damage_calc as mdc
    members = mdc.parse_player_team(paste)
    out: List[CandidateCheck] = []

    def _threats(names: List[str]):
        return [mdc.TargetThreat(species=n, appearances=0, appearance_pct=0.0,
                                 nature="Serious", evs={"hp": 252, "atk": 0, "def": 4, "spa": 0, "spd": 4, "spe": 0})
                for n in dict.fromkeys(names)]

    for m in members:
        cc = CandidateCheck(species=m.species, types=species_types(m.species))
        if cc.types:
            cc.type_checks = [(t, get_multiplier(list(cc.types), t)) for t in weak]
        for names, dest in ((counters, cc.counter_damage), (ko_targets, cc.target_damage)):
            if not names or not m.moves:
                continue
            rep = mdc.calculate_damage_for_attacker(m, _threats(names))
            for r in rep.target_results:
                bm = r.best_move
                dest.append((r.threat.species, bm.move_name if bm else None, bm.max_pct if bm else 0.0, r.ko_tier))
        out.append(cc)
    return out
