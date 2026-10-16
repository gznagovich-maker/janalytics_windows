"""
test_player_core_analysis.py
=============================
Test unitari per la logica di dominio dell'analisi dei Core da 4 e dei Singoli Pokémon.
"""

import unittest
from src.domain.sheet_dashboard.models import DashboardGame, GameSummary, SheetGameRow, SideData
from src.domain.sheet_dashboard.player_core_analysis import compute_player_core_analysis


def _mock_game(game_no: int, me_lead, me_back, opp_lead, opp_back, won: bool) -> DashboardGame:
    row = SheetGameRow(game_no=game_no, replay_url=f"https://replay/{game_no}")
    team = ["Basculegion", "Garchomp", "Gholdengo", "Raichu", "Rillaboom", "Volcarona"]
    me_side = SideData(slot="p1", name="Player", team=team, lead=me_lead, back=me_back)
    opp_side = SideData(slot="p2", name="Opponent", team=opp_lead + opp_back + ["Incineroar", "Kingambit"][:6-len(opp_lead+opp_back)],
                        lead=opp_lead, back=opp_back)
    summary = GameSummary(me=me_side, opp=opp_side, won=won)
    return DashboardGame(row=row, replay_id=f"rep-{game_no}", match_id=f"m-{game_no}", summary=summary)


class TestPlayerCoreAnalysis(unittest.TestCase):
    def test_core_analysis_combinations_and_unplayed(self):
        g1 = _mock_game(1, ["Basculegion", "Garchomp"], ["Gholdengo", "Rillaboom"],
                        ["Charizard", "Venusaur"], ["Blastoise", "Pikachu"], won=True)
        g2 = _mock_game(2, ["Basculegion", "Garchomp"], ["Gholdengo", "Rillaboom"],
                        ["Delphox", "Kingambit"], ["Garchomp", "Incineroar"], won=False)

        report = compute_player_core_analysis([g1, g2])
        self.assertEqual(len(report.player_team), 6)
        self.assertEqual(len(report.cores_4), 15)  # C(6, 4) = 15

        # Core played
        played_core = tuple(sorted(["Basculegion", "Garchomp", "Gholdengo", "Rillaboom"]))
        entry = next(c for c in report.cores_4 if c.core == played_core)
        self.assertTrue(entry.played)
        self.assertEqual(entry.games, 2)
        self.assertEqual(entry.wins, 1)
        self.assertEqual(entry.losses, 1)
        self.assertEqual(entry.win_pct, 0.5)
        self.assertEqual(entry.wins_vs_opp_pokemon["Charizard"], 1)
        self.assertEqual(entry.wins_vs_opp_pokemon["Venusaur"], 1)
        self.assertEqual(entry.losses_vs_opp_pokemon["Delphox"], 1)
        self.assertEqual(entry.losses_vs_opp_pokemon["Kingambit"], 1)

        # An unplayed core
        unplayed_core = tuple(sorted(["Basculegion", "Garchomp", "Raichu", "Volcarona"]))
        unplayed_entry = next(c for c in report.cores_4 if c.core == unplayed_core)
        self.assertFalse(unplayed_entry.played)
        self.assertEqual(unplayed_entry.games, 0)
        self.assertIsNone(unplayed_entry.win_pct)
        self.assertEqual(len(unplayed_entry.wins_vs_opp_pokemon), 0)

    def test_single_pokemon_best_worst(self):
        g1 = _mock_game(1, ["Basculegion", "Garchomp"], ["Gholdengo", "Rillaboom"],
                        ["A", "B"], ["C", "D"], won=True)
        g2 = _mock_game(2, ["Basculegion", "Garchomp"], ["Gholdengo", "Rillaboom"],
                        ["A", "B"], ["C", "D"], won=True)
        g3 = _mock_game(3, ["Basculegion", "Garchomp"], ["Gholdengo", "Rillaboom"],
                        ["E", "F"], ["G", "H"], won=False)

        report = compute_player_core_analysis([g1, g2, g3])
        basc = report.pokemon_matchups["Basculegion"]
        self.assertEqual(basc.total_games, 3)
        self.assertEqual(basc.total_wins, 2)
        self.assertEqual(basc.total_losses, 1)
        self.assertAlmostEqual(basc.win_pct, 2 / 3)

        self.assertEqual(len(basc.best_matchups), 1)
        best_core, best_w = basc.best_matchups[0]
        self.assertEqual(best_core, ("A", "B", "C", "D"))
        self.assertEqual(best_w, 2)

        self.assertEqual(len(basc.worst_matchups), 1)
        worst_core, worst_l = basc.worst_matchups[0]
        self.assertEqual(worst_core, ("E", "F", "G", "H"))
        self.assertEqual(worst_l, 1)


if __name__ == "__main__":
    unittest.main()
