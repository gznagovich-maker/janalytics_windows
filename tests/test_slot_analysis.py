"""
Test offline delle analisi di sostituzione slot (parser KO/switch + slot_analysis).

    venv\\Scripts\\python.exe -m unittest tests.test_slot_analysis -v
"""

import unittest
from pathlib import Path

from src.domain.sheet_dashboard import slot_analysis as sa
from src.domain.sheet_dashboard.models import DashboardGame, GameSummary, SheetGameRow, SideData
from src.domain.sheet_dashboard.replay_resolver import orient, parse_log

FIX = Path(__file__).parent / "fixtures" / "sheet_dashboard"

LOG = """\
|player|p1|Alice|1|1300
|player|p2|Bob|2|1250
|poke|p1|Goodra-Hisui, L50|
|poke|p1|Incineroar, L50|
|poke|p1|Rillaboom, L50|
|poke|p1|Amoonguss, L50|
|poke|p2|Urshifu-*, L50|
|poke|p2|Flutter Mane, L50|
|poke|p2|Landorus, L50|
|poke|p2|Tornadus, L50|
|start
|switch|p1a: Goodra|Goodra-Hisui, L50|100/100
|switch|p1b: Rilla|Rillaboom, L50|100/100
|switch|p2a: Fish|Urshifu-Rapid-Strike, L50|100/100
|switch|p2b: Lando|Landorus, L50|100/100
|turn|1
|switch|p1a: Cat|Incineroar, L50|200/200
|move|p2a: Fish|Close Combat|p1a: Cat
|-damage|p1a: Cat|60/200
|move|p2b: Lando|Sludge Bomb|p1b: Rilla
|-damage|p1b: Rilla|30/100 psn
|move|p1b: Rilla|U-turn|p2a: Fish
|-damage|p2a: Fish|70/100
|switch|p1b: Shroom|Amoonguss, L50|100/100|[from] U-turn
|-heal|p1a: Cat|80/200|[from] item: Leftovers
|upkeep
|turn|2
|move|p2a: Fish|Surging Strikes|p1a: Cat
|-damage|p1a: Cat|0 fnt
|faint|p1a: Cat
|move|p1b: Shroom|Spore|p2a: Fish
|upkeep
|switch|p1a: Goodra|Goodra-Hisui, L50|100/100
|turn|3
|move|p1a: Goodra|Draco Meteor|p2b: Lando
|-damage|p2b: Lando|0 fnt
|faint|p2b: Lando
|-damage|p1b: Shroom|0 fnt|[from] Sandstorm
|faint|p1b: Shroom
|upkeep
|win|Bob
"""


def _game(n, summary):
    return DashboardGame(row=SheetGameRow(game_no=n, replay_url="x"), replay_id=f"r{n}",
                         match_id=f"m{n}", summary=summary)


def _manual(n, my_team, my_lead, my_back, opp_team, won):
    return _game(n, GameSummary(
        me=SideData(slot="p1", team=my_team, lead=my_lead, back=my_back),
        opp=SideData(slot="p2", team=opp_team, lead=opp_team[:2], back=opp_team[2:4]),
        won=won))


class TestParserEvents(unittest.TestCase):
    def setUp(self):
        self.s = orient(parse_log(LOG, "t"), ["Alice"])

    def test_kos(self):
        mine = self.s.me.kos_suffered
        self.assertEqual(len(mine), 2)
        cat = next(k for k in mine if k.victim == "Incineroar")
        self.assertEqual((cat.killer, cat.move, cat.indirect), ("Urshifu-Rapid-Strike", "Surging Strikes", False))
        shroom = next(k for k in mine if k.victim == "Amoonguss")
        self.assertTrue(shroom.indirect)
        self.assertEqual(shroom.source, "Sandstorm")
        theirs = self.s.opp.kos_suffered
        self.assertEqual([(k.victim, k.killer, k.move) for k in theirs], [("Landorus", "Goodra-Hisui", "Draco Meteor")])

    def test_switch_ins(self):
        evs = self.s.me.switch_ins
        # Goodra rientra dopo un KO (sostituzione forzata) → non conta
        self.assertEqual([(e.pokemon, e.kind) for e in evs], [("Incineroar", "hard"), ("Amoonguss", "pivot")])
        inc = evs[0]
        self.assertEqual(inc.replaced, "Goodra-Hisui")
        self.assertAlmostEqual(inc.hp_lost, 70.0)          # Leftovers non maschera il danno
        self.assertEqual(inc.hits, [("Urshifu-Rapid-Strike", "Close Combat")])

    def test_real_log_still_parses(self):
        p = parse_log((FIX / "game1.log").read_text(encoding="utf-8"), "g1")
        self.assertTrue(any(s.kos_suffered for s in p.sides.values()))


class TestSlotAnalysis(unittest.TestCase):
    def setUp(self):
        team = ["Goodra-Hisui", "Incineroar", "Rillaboom", "Amoonguss", "Gholdengo", "Dondozo"]
        self.games = [
            _manual(1, team, ["Goodra-Hisui", "Incineroar"], ["Rillaboom", "Amoonguss"], ["Urshifu-Rapid-Strike", "Calyrex-Shadow", "A", "B"], False),
            _manual(2, team, ["Goodra-Hisui", "Gholdengo"], ["Rillaboom", "Amoonguss"], ["Urshifu-Rapid-Strike", "C", "D", "E"], False),
            _manual(3, team, ["Goodra-Hisui", "Incineroar"], ["Gholdengo", "Amoonguss"], ["Urshifu-Rapid-Strike", "Calyrex-Shadow", "F", "G"], True),
            _manual(4, team, ["Goodra-Hisui", "Incineroar"], ["Rillaboom", "Gholdengo"], ["H", "I", "J", "K"], True),
        ]
        self.games.append(_game(5, orient(parse_log(LOG, "t"), ["Alice"])))

    def test_dead_weight(self):
        rows, cand = sa.dead_weight_index(self.games[:4], threshold=0.25)
        self.assertEqual(rows[0].pokemon, "Dondozo")
        self.assertEqual(rows[0].pick_rate, 0.0)
        self.assertTrue(rows[0].below_threshold)
        self.assertEqual(cand, "Dondozo")
        goodra = next(r for r in rows if r.pokemon == "Goodra-Hisui")
        self.assertEqual(goodra.pick_rate, 1.0)
        self.assertEqual(goodra.win_pct_brought, 0.5)

    def test_matchups(self):
        rows, overall = sa.negative_matchup_matrix(self.games[:4], wr_threshold=0.40, min_games=2)
        ursh = next(r for r in rows if r.pokemon == "Urshifu-Rapid-Strike")
        self.assertEqual(ursh.preview_games, 3)
        self.assertAlmostEqual(ursh.preview_wr, 1 / 3)
        self.assertTrue(ursh.flagged)
        self.assertEqual(overall, 0.5)

    def test_ko_suffered(self):
        sa.move_type.cache_clear()
        st = sa.ko_suffered_analysis(self.games, structural_threshold=0.40)
        self.assertEqual((st.total, st.direct, st.indirect), (2, 1, 1))
        self.assertEqual(st.by_killer[0][0], "Urshifu-Rapid-Strike")
        types = {t for t, _, _ in st.by_type}
        self.assertIn(sa.INDIRECT, types)

    def test_switch_and_core_filter(self):
        rows = sa.switch_in_damage(self.games, hp_threshold=50.0)
        inc = next(r for r in rows if r.pokemon == "Incineroar")
        self.assertEqual((inc.count, inc.over_threshold), (1, 1))
        core_rows = sa.switch_in_damage(self.games, hp_threshold=50.0, core="Goodra-Hisui")
        self.assertEqual([r.pokemon for r in core_rows], ["Incineroar"])

    def test_ko_tradeoff(self):
        rows, total, _ = sa.ko_tradeoff(self.games, "Goodra-Hisui")
        self.assertEqual(total, 1)
        self.assertEqual((rows[0].target, rows[0].count, rows[0].exclusive), ("Landorus", 1, True))

    def test_resisting_types(self):
        res, imm = sa.resisting_types("Ground")
        self.assertIn("Grass", res)
        self.assertIn("Flying", imm)


if __name__ == "__main__":
    unittest.main()
