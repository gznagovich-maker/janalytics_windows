"""
Test offline della Sheet Dashboard (stdlib unittest).

Esecuzione:
    venv\\Scripts\\python.exe -m unittest tests.test_sheet_dashboard -v

Le fixture provengono dal foglio mock PASRS (usato SOLO per studiarne la
struttura) e da un log Showdown reale.
"""

import os
import unittest
from pathlib import Path

from src.domain.sheet_dashboard import dashboard_stats as ds
from src.domain.sheet_dashboard import sheet_mapper as sm
from src.domain.sheet_dashboard.models import DashboardGame, SheetGameRow
from src.domain.sheet_dashboard.replay_resolver import (
    canonical_species, match_id_from_slug, orient, parse_log, replay_slug_from_url,
)
from src.domain.sheet_dashboard.sheet_client import find_tab, parse_spreadsheet_url
from src.domain.sheet_dashboard.models import SheetTab

FIX = Path(__file__).parent / "fixtures" / "sheet_dashboard"


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


SYNTHETIC_LOG = """\
|player|p1|Alice|1|1300
|player|p2|Bob|2|1250
|tier|[Gen 9] VGC Test
|poke|p1|Urshifu-*, L50|
|poke|p1|Palafin, L50|
|poke|p1|Indeedee-F, L50|
|poke|p1|Charizard, L50|
|poke|p2|Ogerpon-Hearthflame, L50|
|poke|p2|Incineroar, L50|
|poke|p2|Amoonguss, L50|
|poke|p2|Rillaboom, L50|
|showteam|p2|Ogerpon||HearthflameMask|MoldBreaker|IvyCudgel|Adamant|||||50|
|start
|switch|p1a: Fish|Urshifu-Rapid-Strike, L50|100/100
|switch|p1b: Dolphin|Palafin, L50|100/100
|switch|p2a: Ogerpon|Ogerpon-Hearthflame, L50|100/100
|switch|p2b: Cat|Incineroar, L50|100/100
|turn|1
|detailschange|p2a: Ogerpon|Ogerpon-Hearthflame-Tera, L50
|move|p1a: Fish|Surging Strikes|p2a: Ogerpon
|move|p1a: Fish|Surging Strikes|p2a: Ogerpon|[from]lockedmove
|switch|p1b: Zard|Charizard, L50|100/100
|detailschange|p1b: Zard|Charizard-Mega-Y, L50
|-mega|p1b: Zard|Charizard|Charizardite Y
|switch|p1a: Dolphin|Palafin-Hero, L50|100/100
|switch|p2b: Shroom|Amoonguss, L50|100/100
|turn|2
|win|Alice
"""


class TestSheetClient(unittest.TestCase):
    def test_parse_url_variants(self):
        sid = "14ZIWtlIc2em_Bo38jtwjU4LIyJ6WDdh-ZySk2il818w"
        self.assertEqual(parse_spreadsheet_url(f"https://docs.google.com/spreadsheets/d/{sid}/edit?gid=1#gid=1"), sid)
        self.assertEqual(parse_spreadsheet_url(f"https://docs.google.com/spreadsheets/d/{sid}/htmlview"), sid)
        self.assertEqual(parse_spreadsheet_url(sid), sid)
        with self.assertRaises(ValueError):
            parse_spreadsheet_url("https://example.com/foo")

    def test_find_tab_case_insensitive(self):
        tabs = [SheetTab("Game By Game", "1"), SheetTab("Move Usage", "2"), SheetTab("Usage", "3")]
        self.assertEqual(find_tab(tabs, "game by game").gid, "1")
        self.assertEqual(find_tab(tabs, "Usage").gid, "3")   # match esatto prima del 'contains'


class TestSheetMapper(unittest.TestCase):
    def test_home(self):
        names, paste = sm.parse_home(sm.csv_to_grid(_read("Home.csv")))
        self.assertEqual(names, ["jirkunow"])
        self.assertTrue(paste.startswith("https://pokepast.es/"))

    def test_replay_entries(self):
        rows = sm.parse_replay_entries(sm.csv_to_grid(_read("Replay_Entries.csv")))
        self.assertGreaterEqual(len(rows), 34)
        self.assertEqual(rows[0].game_no, 1)
        self.assertIn("replay.pokemonshowdown.com", rows[0].replay_url)
        self.assertEqual(rows[0].result, "Loss")

    def test_game_by_game_and_merge(self):
        html = ('<table><tr><td>1</td><td>Loss</td><td><a href="https://www.google.com/url?q='
                'https://replay.pokemonshowdown.com/gen9x-111&amp;sa=D">Replay</a></td></tr></table>')
        links = sm.extract_html_row_links(html)
        self.assertEqual(links, {1: "https://replay.pokemonshowdown.com/gen9x-111"})
        gbg = sm.parse_game_by_game(sm.csv_to_grid(_read("Game_By_Game.csv")), links)
        self.assertEqual(gbg[0].game_no, 1)
        self.assertEqual(gbg[0].opponent, "dcccxxiii")
        self.assertTrue(gbg[0].ots)
        self.assertEqual(gbg[2].elo_you, "1108 -> 1131")
        self.assertEqual(gbg[2].elo_opp, "1084")
        merged = sm.merge_games(sm.parse_replay_entries(sm.csv_to_grid(_read("Replay_Entries.csv"))), gbg)
        self.assertEqual(merged[0].opponent, "dcccxxiii")

    def test_move_usage_charts(self):
        charts = sm.parse_move_usage(_read("Move_Usage.hv.html"), sm.csv_to_grid(_read("Move_Usage.csv")))
        self.assertEqual([c.pokemon for c in charts],
                         ["Raichu", "Garchomp", "Gholdengo", "Volcarona", "Rillaboom", "Basculegion"])
        raichu = {s.move: s.count for s in charts[0].slices}
        self.assertIn("Zap Cannon", raichu)
        self.assertTrue(all(s.color for s in charts[0].slices))

    def test_matchup_numbers(self):
        nums = sm.parse_matchup_numbers(sm.csv_to_grid(_read("Matchup_Stats.csv")))
        self.assertEqual(len(nums["Best Matchups"]), 5)
        self.assertEqual(nums["Best Matchups"][0], (4, 4))


class TestReplayResolver(unittest.TestCase):
    def test_slug_and_match_id(self):
        url = "https://replay.pokemonshowdown.com/gen9championsvgc2026regmcbo3-2695223934-axwrdgc1oind80kqgxr5raj454wqlabpw"
        slug = replay_slug_from_url(url)
        self.assertTrue(slug.endswith("pw"))
        self.assertEqual(match_id_from_slug(slug), "gen9championsvgc2026regmcbo3-2695223934")
        self.assertEqual(match_id_from_slug("gen9x-123"), "gen9x-123")

    def test_canonical_species(self):
        self.assertEqual(canonical_species("Garchomp-Mega-Z, L50, F"), "Garchomp")
        self.assertEqual(canonical_species("Ogerpon-Hearthflame-Tera, L50"), "Ogerpon-Hearthflame")
        self.assertEqual(canonical_species("Indeedee-F, L50"), "Indeedee-F")

    def test_real_log(self):
        p = parse_log(_read("game1.log"), "g1")
        s = orient(p, ["jirkunow"])
        self.assertIsNotNone(s)
        self.assertEqual(s.me.name, "jirkunow")
        self.assertEqual(s.me.lead, ["Gholdengo", "Garchomp"])
        self.assertEqual(s.opp.lead, ["Garchomp", "Rillaboom"])
        self.assertEqual(s.opp.mega, "Garchomp")
        self.assertFalse(s.won)
        self.assertTrue(s.opp.showteam)

    def test_species_form_identity(self):
        p = parse_log(SYNTHETIC_LOG, "syn")
        a, b = p.sides["p1"], p.sides["p2"]
        # Wildcard risolta con la forma reale, forma di battaglia non duplicata
        self.assertEqual(a.team, ["Urshifu-Rapid-Strike", "Palafin", "Indeedee-F", "Charizard"])
        self.assertEqual(a.lead, ["Urshifu-Rapid-Strike", "Palafin"])
        self.assertEqual(a.back, ["Charizard"])
        self.assertEqual(a.mega, "Charizard")
        self.assertEqual(a.moves["Urshifu-Rapid-Strike"]["Surging Strikes"], 1)   # [from]lockedmove escluso
        self.assertEqual(b.team[0], "Ogerpon-Hearthflame")
        self.assertEqual(b.back, ["Amoonguss"])
        self.assertTrue(b.showteam and not a.showteam)
        self.assertTrue(orient(p, ["alice"]).won)


class TestStats(unittest.TestCase):
    def _games(self):
        g1 = parse_log(SYNTHETIC_LOG, "a")
        games = []
        for i, (res, elo) in enumerate([("Win", "1250"), ("Loss", "1400"), ("Win", "")], start=1):
            s = orient(g1, ["Alice"])
            games.append(DashboardGame(row=SheetGameRow(i, f"https://replay.pokemonshowdown.com/x-{i}",
                                                        result=res, opponent="Bob", ots=True, elo_opp=elo),
                                       replay_id=f"x-{i}", match_id=f"x-{i}", summary=s))
        return games

    def test_filters(self):
        games = self._games()
        self.assertEqual(len(ds.apply_filter(games, ds.GameFilter(result="Win"))), 2)
        self.assertEqual(len(ds.apply_filter(games, ds.GameFilter(opp_lead="Incineroar"))), 3)
        self.assertEqual(len(ds.apply_filter(games, ds.GameFilter(opp_lead="Amoonguss"))), 0)
        self.assertEqual(len(ds.apply_filter(games, ds.GameFilter(my_mega="Charizard"))), 3)
        # ELO mancante nel foglio → fallback al rating del log (1250)
        self.assertEqual([g.game_no for g in ds.apply_filter(games, ds.GameFilter(min_elo=1300))], [2])
        opts = ds.filter_options(games)
        self.assertIn("Urshifu-Rapid-Strike", opts["my_lead"])

    def test_usage_and_leads(self):
        games = self._games()
        u = ds.usage_stats(games)
        self.assertEqual((u.total.wins, u.total.games), (2, 3))
        pair = ("Palafin", "Urshifu-Rapid-Strike")
        self.assertEqual(u.common_leads[0][0], pair)
        self.assertEqual(len(ds.lead_pair_games(games, ("Urshifu-Rapid-Strike", "Palafin"))), 3)

    def test_matchup(self):
        games = self._games()
        ms = ds.matchup_stats(games, min_games=3)
        amoon = ms.all["Amoonguss"]
        self.assertEqual((amoon.wins_brought, amoon.brought, amoon.games), (2, 3, 3))
        self.assertEqual(ms.all["Rillaboom"].brought, 0)


if __name__ == "__main__":
    unittest.main()
