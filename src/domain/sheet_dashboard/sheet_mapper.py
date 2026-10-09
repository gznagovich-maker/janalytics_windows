"""
sheet_mapper.py
===============
Mapping dei tab del template PASRS verso i DTO di dominio.

Strategia: i parser usano ANCORE TESTUALI ("Game", "Result", "Replay Links",
"Best Matchups", ...) invece di coordinate fisse, così restano robusti se
l'utente sposta/aggiunge colonne nella propria copia del template.

Limite noto del template: i Pokémon nei tab Usage / Matchup Stats /
Game By Game sono formule IMAGE() servite tramite proxy Google, quindi la loro
identità NON è ricavabile dal foglio. Viene ricostruita nativamente dai log
dei replay (vedi replay_resolver).
"""

import csv
import html as html_lib
import io
import json
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

from src.domain.sheet_dashboard.models import (
    MoveSlice, MoveUsageChart, SheetGameRow,
)

Grid = List[List[str]]


# ── Utility griglia ───────────────────────────────────────────────

def csv_to_grid(csv_text: str) -> Grid:
    # Normalizza i fine riga: un CR spurio creerebbe righe vuote e
    # disallineerebbe gli indici di riga rispetto alle ancore posObj dei grafici.
    text = (csv_text or "").replace("\r", "")
    return [[(c or "").strip() for c in row] for row in csv.reader(io.StringIO(text))]


def _cell(grid: Grid, r: int, c: int) -> str:
    if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
        return grid[r][c]
    return ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _find_cells(grid: Grid, predicate) -> List[Tuple[int, int]]:
    return [(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v and predicate(v)]


def _int(s: str) -> Optional[int]:
    s = (s or "").strip()
    return int(s) if s.isdigit() else None


def unwrap_google_redirect(url: str) -> str:
    """https://www.google.com/url?q=<REAL>&sa=... → <REAL>."""
    url = html_lib.unescape(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.endswith("google.com") and parsed.path == "/url":
        q = urllib.parse.parse_qs(parsed.query).get("q")
        if q:
            return q[0]
    return url


def _is_replay_url(url: str) -> bool:
    return "replay.pokemonshowdown.com" in (url or "") or "pokemonshowdown.com/replay" in (url or "")


# ── Home ──────────────────────────────────────────────────────────

def parse_home(grid: Grid) -> Tuple[List[str], str]:
    """Restituisce (nickname Showdown, URL pokepaste) dal tab Home."""
    names: List[str] = []
    paste = ""
    for r, row in enumerate(grid):
        joined = " ".join(row).lower()
        if "showdown name" in joined:
            label_c = next(c for c, v in enumerate(row) if "showdown name" in v.lower())
            values = [v for v in row[label_c + 1:] if v]
            if values:
                names = [n.strip() for n in re.split(r"[,;/]", values[0]) if n.strip()]
        if "pokepaste" in joined and not paste:
            for v in row:
                if v.startswith("http"):
                    paste = v
                    break
    return names, paste


# ── Replay Entries ────────────────────────────────────────────────

def parse_replay_entries(grid: Grid) -> List[SheetGameRow]:
    """Lista master dei game: numero progressivo + URL replay (+ W/L, note)."""
    notes_col = None
    for r, c in _find_cells(grid, lambda v: _norm(v) == "notes"):
        notes_col = c
        break

    rows: List[SheetGameRow] = []
    for row in grid:
        url_c = next((c for c, v in enumerate(row) if v.startswith("http") and _is_replay_url(v)), None)
        if url_c is None:
            continue
        game_no = None
        for c in range(url_c - 1, -1, -1):
            game_no = _int(row[c])
            if game_no is not None:
                break
        if game_no is None:
            game_no = len(rows) + 1
        result = None
        for v in row[url_c + 1:]:
            if v.upper() in ("W", "WIN"):
                result = "Win"
                break
            if v.upper() in ("L", "LOSS"):
                result = "Loss"
                break
        notes = _cell([row], 0, notes_col) if notes_col is not None else ""
        rows.append(SheetGameRow(game_no=game_no, replay_url=row[url_c], result=result, notes=notes))
    return rows


# ── Game By Game ──────────────────────────────────────────────────

def extract_html_row_links(html: str) -> Dict[int, str]:
    """
    Dal render htmlview estrae {numero game: URL replay} leggendo gli href
    (gli hyperlink "Replay" non sono presenti nell'export CSV).
    """
    links: Dict[int, str] = {}
    for tr in re.split(r"<tr[\s>]", html)[1:]:
        hrefs = [unwrap_google_redirect(h) for h in re.findall(r'href="([^"]+)"', tr)]
        replay = next((h for h in hrefs if _is_replay_url(h)), None)
        if not replay:
            continue
        texts = [html_lib.unescape(re.sub(r"<[^>]+>", "", td)).strip()
                 for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        game_no = next((_int(t) for t in texts if _int(t) is not None), None)
        if game_no is not None and game_no not in links:
            links[game_no] = replay
    return links


def parse_game_by_game(grid: Grid, html_links: Optional[Dict[int, str]] = None) -> List[SheetGameRow]:
    """Righe del tab Game By Game: risultato, avversario, OTS, ELO, link replay."""
    html_links = html_links or {}
    header = None
    for r, row in enumerate(grid):
        n = [_norm(v) for v in row]
        if "game" in n and "result" in n:
            header = r
            break
    if header is None:
        return []

    hrow = grid[header]
    n_h = [_norm(v) for v in hrow]
    game_c = n_h.index("game")
    result_c = n_h.index("result")

    # OTS / ELO nelle righe di intestazione superiori
    ots_c = elo_c = None
    for r in range(max(0, header - 4), header):
        for c, v in enumerate(grid[r]):
            if _norm(v) == "ots":
                ots_c = c
            if _norm(v) == "elo":
                elo_c = c
    elo_you_c = elo_opp_c = None
    if elo_c is not None:
        for c in range(elo_c, len(hrow)):
            if _norm(hrow[c]) == "you" and elo_you_c is None:
                elo_you_c = c
            elif _norm(hrow[c]) == "opp" and elo_opp_c is None:
                elo_opp_c = c

    rows: List[SheetGameRow] = []
    for r in range(header + 1, len(grid)):
        row = grid[r]
        game_no = _int(_cell(grid, r, game_c))
        if game_no is None:
            continue
        result = _cell(grid, r, result_c)
        result = result if result in ("Win", "Loss") else None
        opponent = ""
        for c in range(result_c + 1, min(len(row), result_c + 4)):
            if row[c].lower() == "vs" and c + 1 < len(row):
                opponent = row[c + 1]
                break
        ots_raw = _cell(grid, r, ots_c).upper() if ots_c is not None else ""
        ots = True if ots_raw == "YES" else False if ots_raw == "NO" else None
        rows.append(SheetGameRow(
            game_no=game_no,
            replay_url=html_links.get(game_no, ""),
            result=result,
            opponent=opponent,
            ots=ots,
            elo_you=_cell(grid, r, elo_you_c) if elo_you_c is not None else "",
            elo_opp=_cell(grid, r, elo_opp_c) if elo_opp_c is not None else "",
        ))
    return rows


def merge_games(entries: List[SheetGameRow], gbg: List[SheetGameRow]) -> List[SheetGameRow]:
    """
    Replay Entries è la lista master (sempre completa, anche se l'utente ha
    filtrato Game By Game). Game By Game arricchisce con avversario, OTS, ELO.
    """
    by_no = {g.game_no: g for g in gbg}
    merged: List[SheetGameRow] = []
    if entries:
        for e in entries:
            g = by_no.get(e.game_no)
            if g:
                e.result = g.result or e.result
                e.opponent = g.opponent
                e.ots = g.ots
                e.elo_you = g.elo_you
                e.elo_opp = g.elo_opp
                if not e.replay_url:
                    e.replay_url = g.replay_url
            merged.append(e)
    else:
        merged = [g for g in gbg if g.replay_url]
    return sorted(merged, key=lambda x: x.game_no)


# ── Move Usage ────────────────────────────────────────────────────

def _decode_js_string(s: str) -> str:
    s = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace("\\/", "/").replace("\\'", "'")


def parse_move_usage(html: str, grid: Grid) -> List[MoveUsageChart]:
    """
    Estrae i grafici a torta dal tab "Move Usage".
    - dati e colori: `chartJson` embedded nell'htmlview
    - nome Pokémon: cella testuale più vicina SOPRA l'ancora del grafico
      (posizione da posObj(gid, 'embed_<id>', row, col, ...)).
    """
    positions: Dict[str, Tuple[int, int]] = {}
    for m in re.finditer(r"posObj\('\d+',\s*'embed_(\d+)',\s*(\d+),\s*(\d+)", html):
        positions[m.group(1)] = (int(m.group(2)), int(m.group(3)))

    charts: List[Tuple[Tuple[int, int], MoveUsageChart]] = []
    for m in re.finditer(r"chartData\['(\d+)'\]\s*=\s*\{'chartId'.*?'chartJson':\s*'((?:[^'\\]|\\.)*)'", html, re.S):
        chart_id = m.group(1)
        try:
            spec = json.loads(_decode_js_string(m.group(2)))
        except Exception:
            continue
        if spec.get("chartType") not in ("PieChart", None):
            continue
        options = spec.get("options", {}) or {}
        slices_opt = options.get("slices", {}) or {}
        slices: List[MoveSlice] = []
        for i, row in enumerate(spec.get("dataTable", {}).get("rows", [])):
            cells = row.get("c") or []
            if len(cells) < 2 or not cells[0] or cells[0].get("v") in (None, ""):
                continue
            value = cells[1].get("v") if cells[1] else None
            if not isinstance(value, (int, float)) or value <= 0:
                continue
            color = (slices_opt.get(str(i)) or {}).get("color")
            slices.append(MoveSlice(move=str(cells[0]["v"]), count=float(value), color=color))

        pos = positions.get(chart_id, (10 ** 6, 10 ** 6))
        label = options.get("title") or ""
        if not label and pos[0] < 10 ** 6:
            r, c = pos
            for rr in range(r - 1, -1, -1):
                if _cell(grid, rr, c):
                    label = _cell(grid, rr, c)
                    break
        if slices:
            charts.append((pos, MoveUsageChart(pokemon=label or f"Chart {chart_id}", slices=slices)))

    charts.sort(key=lambda x: x[0])
    return [c for _, c in charts]


# ── Usage / Matchup Stats (solo numeri, per verifica coerenza) ────

def parse_usage_numbers(grid: Grid) -> Dict[str, List[str]]:
    """Numeri principali del tab Usage, es. {'Win%': ['61.8%'], 'OTS Win%': ['62%']}."""
    out: Dict[str, List[str]] = {}
    for row in grid:
        for c, v in enumerate(row):
            if v in ("Win%", "OTS Win%", "CTS Win%") and c + 1 < len(row):
                out.setdefault(v, []).append(row[c + 1])
    return out


def parse_matchup_numbers(grid: Grid) -> Dict[str, List[Tuple[int, int]]]:
    """{'Best Matchups': [(4,4), (6,8), ...], ...} dai 4 riquadri del tab."""
    sections = ("Best Matchups", "Worst Matchups", "Highest Attendance", "Lowest Attendance")
    header = None
    for r, row in enumerate(grid):
        if any(v in sections for v in row):
            header = r
            break
    if header is None:
        return {}
    cols = {v: c for c, v in enumerate(grid[header]) if v in sections}
    out: Dict[str, List[Tuple[int, int]]] = {s: [] for s in cols}
    for r in range(header + 1, min(len(grid), header + 12)):
        row = grid[r]
        for sec, c0 in cols.items():
            for c in range(c0, min(len(row), c0 + 8)):
                if row[c] in ("beat", "seen") and c + 3 < len(row):
                    a, b = _int(row[c + 1]), _int(row[c + 3])
                    if a is not None and b is not None:
                        out[sec].append((a, b))
                    break
    return out
