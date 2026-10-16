"""
player_core_analysis.py
========================
Logica di dominio pura (nessuna dipendenza Qt) per l'analisi statistica:
  1. Analisi dei Core da 4 del Player (tutte le combinazioni C(N, 4)):
     - Rilevamento automatico 'Mai giocato'
     - Per i core giocati: partite, W/L, Win Rate %, singoli Pokémon avversari
       sconfitti (con numero vittorie) e singoli Pokémon avversari affrontati
       nelle sconfitte (con numero sconfitte).
  2. Analisi dei Singoli Pokémon del Player:
     - Presenze, W/L, Win Rate %
     - Best Matchup: core da 4 avversari contro cui registra il maggior numero di vittorie
     - Worst Matchup: core da 4 avversari contro cui registra il maggior numero di sconfitte
"""

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from src.domain.sheet_dashboard.models import DashboardGame


@dataclass
class PlayerCoreEntry:
    """Rappresenta una combinazione da 4 Pokémon del giocatore."""
    core: Tuple[str, ...]
    games: int = 0
    wins: int = 0
    losses: int = 0
    wins_vs_opp_pokemon: Counter = field(default_factory=Counter)
    losses_vs_opp_pokemon: Counter = field(default_factory=Counter)
    match_games: List[DashboardGame] = field(default_factory=list)

    @property
    def played(self) -> bool:
        return self.games > 0

    @property
    def win_pct(self) -> Optional[float]:
        return (self.wins / self.games) if self.games > 0 else None

    @property
    def label(self) -> str:
        return " + ".join(self.core)


@dataclass
class SinglePokemonMatchup:
    """Analisi di un singolo Pokémon del player vs i core da 4 avversari."""
    pokemon: str
    total_games: int = 0
    total_wins: int = 0
    total_losses: int = 0
    best_matchups: List[Tuple[Tuple[str, ...], int]] = field(default_factory=list)
    worst_matchups: List[Tuple[Tuple[str, ...], int]] = field(default_factory=list)
    all_opp_4_wins: List[Tuple[Tuple[str, ...], int]] = field(default_factory=list)
    all_opp_4_losses: List[Tuple[Tuple[str, ...], int]] = field(default_factory=list)

    @property
    def win_pct(self) -> Optional[float]:
        return (self.total_wins / self.total_games) if self.total_games > 0 else None


@dataclass
class PlayerCoreAnalysisReport:
    """Report completo aggregato."""
    player_team: List[str] = field(default_factory=list)
    cores_4: List[PlayerCoreEntry] = field(default_factory=list)
    pokemon_matchups: Dict[str, SinglePokemonMatchup] = field(default_factory=dict)


def compute_player_core_analysis(
    games: List[DashboardGame],
    team_hint: Optional[List[str]] = None,
) -> PlayerCoreAnalysisReport:
    """
    Esegue l'analisi sui game forniti.
    team_hint: lista facoltativa dei 6 Pokémon del player. Se omessa, viene
    dedotta dalla frequenza delle apparizioni nei log orientati sul giocatore.
    """
    report = PlayerCoreAnalysisReport()
    valid_games = [g for g in games if g.summary is not None and g.won is not None]
    if not valid_games:
        return report

    # 1. Rileva i Pokémon del team del giocatore
    if team_hint and len(team_hint) >= 4:
        player_team = sorted(team_hint)
    else:
        team_counts = Counter()
        for g in valid_games:
            if g.summary.me.team:
                team_counts.update(g.summary.me.team)
            else:
                team_counts.update(g.summary.me.lead + g.summary.me.back)
        # Prende i 6 più frequenti (o tutti quelli presenti se < 6)
        top_mons = [p for p, _ in team_counts.most_common(6)]
        player_team = sorted(top_mons)

    report.player_team = player_team
    if len(player_team) < 4:
        return report

    # 2. Genera tutte le combinazioni da 4 possibili
    all_cores = list(combinations(player_team, 4))
    core_map: Dict[Tuple[str, ...], PlayerCoreEntry] = {
        c: PlayerCoreEntry(core=c) for c in all_cores
    }

    for g in valid_games:
        me_brought = sorted(set(g.summary.me.lead + g.summary.me.back))
        opp_brought = sorted(set(g.summary.opp.lead + g.summary.opp.back))

        if len(me_brought) == 4:
            core_tuple = tuple(me_brought)
            if core_tuple in core_map:
                entry = core_map[core_tuple]
                entry.games += 1
                entry.match_games.append(g)
                if g.won:
                    entry.wins += 1
                    for opp_p in opp_brought:
                        entry.wins_vs_opp_pokemon[opp_p] += 1
                else:
                    entry.losses += 1
                    for opp_p in opp_brought:
                        entry.losses_vs_opp_pokemon[opp_p] += 1

    report.cores_4 = list(core_map.values())

    # 3. Analisi singoli Pokémon vs Core da 4 Avversari
    for p in player_team:
        p_games = [
            g for g in valid_games
            if p in (g.summary.me.lead + g.summary.me.back)
        ]
        total_w = sum(1 for g in p_games if g.won)
        total_l = sum(1 for g in p_games if not g.won)

        opp_4_wins: Counter = Counter()
        opp_4_losses: Counter = Counter()

        for g in p_games:
            opp_b = sorted(set(g.summary.opp.lead + g.summary.opp.back))
            if len(opp_b) == 4:
                opp_tuple = tuple(opp_b)
                if g.won:
                    opp_4_wins[opp_tuple] += 1
                else:
                    opp_4_losses[opp_tuple] += 1

        max_w = opp_4_wins.most_common(1)[0][1] if opp_4_wins else 0
        max_l = opp_4_losses.most_common(1)[0][1] if opp_4_losses else 0

        best = [
            (c, cnt) for c, cnt in opp_4_wins.most_common() if cnt == max_w
        ] if max_w > 0 else []

        worst = [
            (c, cnt) for c, cnt in opp_4_losses.most_common() if cnt == max_l
        ] if max_l > 0 else []

        report.pokemon_matchups[p] = SinglePokemonMatchup(
            pokemon=p,
            total_games=len(p_games),
            total_wins=total_w,
            total_losses=total_l,
            best_matchups=best,
            worst_matchups=worst,
            all_opp_4_wins=opp_4_wins.most_common(),
            all_opp_4_losses=opp_4_losses.most_common(),
        )

    return report
