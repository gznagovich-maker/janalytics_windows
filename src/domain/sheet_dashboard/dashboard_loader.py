"""
dashboard_loader.py
===================
Orchestrazione (senza Qt) del caricamento della Sheet Dashboard:

  1. URL → spreadsheet ID → tab (gid dinamici)
  2. Home / Replay Entries / Game By Game / Move Usage / Usage / Matchup Stats
  3. Download + parsing dei log dei replay (concorrente, con cache su disco)
  4. Orientamento sul giocatore del foglio (nickname dal tab Home)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from src.domain.sheet_dashboard import sheet_client as sc
from src.domain.sheet_dashboard import sheet_mapper as sm
from src.domain.sheet_dashboard.models import DashboardData, DashboardGame, ParsedLog, SheetData
from src.domain.sheet_dashboard.replay_resolver import (
    fetch_log, guess_player_names, match_id_from_slug, orient, parse_log, replay_slug_from_url,
)

ProgressCb = Callable[[int, int, str], None]


def load_sheet(url: str, progress: Optional[ProgressCb] = None) -> SheetData:
    cb = progress or (lambda *a: None)
    sid = sc.parse_spreadsheet_url(url)
    cb(0, 0, "Lettura dei tab del documento...")
    title, tabs = sc.fetch_title_and_tabs(sid)
    data = SheetData(spreadsheet_id=sid, title=title)

    home = sc.find_tab(tabs, "Home")
    if home:
        data.player_names, data.team_paste = sm.parse_home(sm.csv_to_grid(sc.fetch_csv(sid, home.gid)))

    cb(0, 0, "Lettura dei game (Replay Entries / Game By Game)...")
    entries = []
    re_tab = sc.find_tab(tabs, "Replay Entries")
    if re_tab:
        entries = sm.parse_replay_entries(sm.csv_to_grid(sc.fetch_csv(sid, re_tab.gid)))

    gbg = []
    gbg_tab = sc.find_tab(tabs, "Game By Game")
    if gbg_tab:
        gbg_grid = sm.csv_to_grid(sc.fetch_csv(sid, gbg_tab.gid))
        links = {}
        try:
            links = sm.extract_html_row_links(sc.fetch_htmlview(sid, gbg_tab.gid))
        except sc.SheetAccessError as e:
            data.warnings.append(f"Link replay di Game By Game non leggibili: {e}")
        gbg = sm.parse_game_by_game(gbg_grid, links)
    else:
        data.warnings.append("Tab 'Game By Game' non trovato.")

    data.games = sm.merge_games(entries, gbg)
    if not data.games:
        raise ValueError(
            "Nessun link replay trovato nel foglio (tab 'Replay Entries' / 'Game By Game')."
        )

    cb(0, 0, "Lettura dei grafici Move Usage...")
    mu_tab = sc.find_tab(tabs, "Move Usage")
    if mu_tab:
        try:
            data.move_usage = sm.parse_move_usage(
                sc.fetch_htmlview(sid, mu_tab.gid), sm.csv_to_grid(sc.fetch_csv(sid, mu_tab.gid))
            )
        except sc.SheetAccessError as e:
            data.warnings.append(f"Move Usage non leggibile: {e}")
    if not data.move_usage:
        data.warnings.append("Nessun grafico nel tab 'Move Usage': uso il calcolo nativo dai replay.")

    us_tab = sc.find_tab(tabs, "Usage")
    if us_tab and us_tab is not mu_tab:
        data.sheet_usage_numbers = sm.parse_usage_numbers(sm.csv_to_grid(sc.fetch_csv(sid, us_tab.gid)))
    mt_tab = sc.find_tab(tabs, "Matchup Stats")
    if mt_tab:
        data.sheet_matchup_numbers = sm.parse_matchup_numbers(sm.csv_to_grid(sc.fetch_csv(sid, mt_tab.gid)))
    return data


def load_dashboard(url: str, progress: Optional[ProgressCb] = None, workers: int = 8) -> DashboardData:
    cb = progress or (lambda *a: None)
    sheet = load_sheet(url, cb)

    games: List[DashboardGame] = []
    for row in sheet.games:
        try:
            slug = replay_slug_from_url(row.replay_url)
        except ValueError as e:
            games.append(DashboardGame(row=row, replay_id="", match_id="", error=str(e)))
            continue
        games.append(DashboardGame(row=row, replay_id=slug, match_id=match_id_from_slug(slug)))

    total = len(games)
    parsed: Dict[int, ParsedLog] = {}

    def work(idx: int):
        g = games[idx]
        return idx, parse_log(fetch_log(g.replay_id), g.replay_id)

    done = 0
    cb(0, total, f"Download di {total} replay...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(work, i): i for i, g in enumerate(games) if g.replay_id}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                _, p = fut.result()
                parsed[i] = p
            except Exception as e:
                games[i].error = f"Replay non scaricabile: {e}"
            done += 1
            cb(done, total, f"[{done}/{total}] Replay analizzati")

    my_names = list(sheet.player_names)
    if not my_names or not any(orient(p, my_names) for p in parsed.values()):
        guessed = guess_player_names(list(parsed.values()))
        if guessed:
            sheet.warnings.append(
                f"Nickname del giocatore non trovato nel tab Home: uso '{guessed[0]}'."
            )
        my_names = guessed

    for i, p in parsed.items():
        summary = orient(p, my_names)
        if summary is None:
            games[i].error = "Il giocatore del foglio non compare in questo replay."
        games[i].summary = summary

    # Pre-carica gli sprite (download sincrono) fuori dal thread UI
    cb(total, total, "Preparazione sprite...")
    try:
        from src.utils.icon_utils import get_pokemon_icon_path
        species = set()
        for g in games:
            if g.summary:
                species.update(g.summary.me.team + g.summary.opp.team)
        for chart in sheet.move_usage:
            species.add(chart.pokemon)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(get_pokemon_icon_path, species))
    except Exception:
        pass

    return DashboardData(sheet=sheet, games=games, my_names=my_names)
