"""
Test per il modulo meta_damage_calc (calcolo danni squadra vs top 40 pokemon dei replay).
"""

import unittest
from src.domain.sheet_dashboard.meta_damage_calc import (
    extract_top_meta_threats, calculate_damage_for_attacker, parse_player_team
)
from src.domain.sheet_dashboard.models import DashboardGame, GameSummary, SideData, SheetGameRow
from src.domain.team_builder_service import TeamMember


SAMPLE_POKEPASTE = """
Flutter Mane @ Booster Energy  
Ability: Protosynthesis  
Level: 50  
Tera Type: Fairy  
EVs: 4 HP / 252 SpA / 252 Spe  
Timid Nature  
IVs: 0 Atk  
- Moonblast  
- Shadow Ball  
- Dazzling Gleam  
- Protect  

Chi-Yu @ Choice Specs  
Ability: Beads of Ruin  
Level: 50  
Tera Type: Fire  
EVs: 252 SpA / 4 SpD / 252 Spe  
Modest Nature  
- Heat Wave  
- Dark Pulse  
- Overheat  
- Snarl  
"""


class TestMetaDamageCalc(unittest.TestCase):
    def test_parse_player_team(self):
        members = parse_player_team(SAMPLE_POKEPASTE)
        self.assertEqual(len(members), 2)
        self.assertEqual(members[0].species, "Flutter Mane")
        self.assertEqual(members[0].item, "Booster Energy")
        self.assertIn("Moonblast", members[0].moves)
        self.assertEqual(members[1].species, "Chi-Yu")
        self.assertIn("Heat Wave", members[1].moves)

    def test_extract_threats_and_calculate_damage(self):
        games = []
        for i in range(10):
            g = DashboardGame(
                row=SheetGameRow(game_no=i+1, replay_url="https://replay.pokemonshowdown.com/test"),
                replay_id=f"test-{i}",
                match_id=f"test-{i}"
            )
            opp_team = ["Incineroar", "Rillaboom", "Urshifu-Rapid-Strike", "Ogerpon-Hearthflame"]
            if i % 2 == 0:
                opp_team.append("Amoonguss")
            g.summary = GameSummary(
                me=SideData(slot="p1", team=["Flutter Mane", "Chi-Yu"]),
                opp=SideData(slot="p2", team=opp_team),
                won=True
            )
            games.append(g)

        threats = extract_top_meta_threats(games, top_n=5)
        self.assertTrue(len(threats) >= 4)
        species_names = [t.species for t in threats]
        self.assertIn("Incineroar", species_names)
        self.assertIn("Rillaboom", species_names)

        # Verifica frequenza di comparse
        incin = next(t for t in threats if t.species == "Incineroar")
        self.assertEqual(incin.appearances, 10)
        self.assertEqual(incin.appearance_pct, 100.0)

        # Calcolo danni per Flutter Mane
        members = parse_player_team(SAMPLE_POKEPASTE)
        report = calculate_damage_for_attacker(members[0], threats)
        self.assertEqual(len(report.target_results), len(threats))
        self.assertEqual(report.ohko_count + report.twohko_count + report.threehko_count, len(threats))

        # Ogni risultato deve avere calcolato danno min/max e identificato la mossa migliore
        for res in report.target_results:
            self.assertIsNotNone(res.best_move)
            self.assertGreater(res.best_move.max_pct, 0.0)
            self.assertIn(res.ko_tier, ["1HKO", "2HKO", "3+ HKO"])
            self.assertIn(res.speed_tier, ["Piu Veloce", "Piu Lento", "Speed Tie"])


if __name__ == "__main__":
    unittest.main()
