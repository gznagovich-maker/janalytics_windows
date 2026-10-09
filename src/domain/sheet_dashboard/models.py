"""
models.py
=========
Dataclass di dominio della Sheet Dashboard.

Vincolo: l'identità di un Pokémon è SEMPRE la stringa canonica "Specie + Forma"
(es. "Urshifu-Rapid-Strike", "Indeedee-F", "Ogerpon-Hearthflame"), prodotta da
`replay_resolver.canonical_species`. La Mega NON è una forma distinta: viene
tracciata come flag separato (campo `mega`).
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Dati estratti dal Google Sheet ────────────────────────────────

@dataclass
class SheetTab:
    """Tab (foglio) del documento Google Sheets."""
    name: str
    gid: str


@dataclass
class SheetGameRow:
    """Riga di gioco come riportata dal foglio (Replay Entries / Game By Game)."""
    game_no: int
    replay_url: str
    result: Optional[str] = None      # "Win" | "Loss" | None
    opponent: str = ""
    ots: Optional[bool] = None
    elo_you: str = ""                 # es. "1108 -> 1131" | "pending"
    elo_opp: str = ""                 # es. "1084"
    notes: str = ""


@dataclass
class MoveSlice:
    move: str
    count: float
    color: Optional[str] = None       # colore della fetta definito nel foglio


@dataclass
class MoveUsageChart:
    """Grafico a torta "Move Usage" per un singolo Pokémon."""
    pokemon: str                      # etichetta come nel foglio
    slices: List[MoveSlice] = field(default_factory=list)
    source: str = "sheet"             # "sheet" | "native"


@dataclass
class SheetData:
    """Tutto ciò che è stato letto dal Google Sheet."""
    spreadsheet_id: str
    title: str = ""
    player_names: List[str] = field(default_factory=list)
    team_paste: str = ""
    games: List[SheetGameRow] = field(default_factory=list)
    move_usage: List[MoveUsageChart] = field(default_factory=list)
    # Numeri "grezzi" dai tab Usage / Matchup Stats (solo per verifica coerenza)
    sheet_usage_numbers: Dict[str, List[str]] = field(default_factory=dict)
    sheet_matchup_numbers: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ── Dati estratti dai log dei replay ──────────────────────────────

@dataclass
class SideData:
    """Dati di un lato (p1/p2) estratti da un log Showdown."""
    slot: str
    name: str = ""
    rating: Optional[int] = None
    team: List[str] = field(default_factory=list)     # team preview (6), Specie+Forma
    lead: List[str] = field(default_factory=list)     # 2 lead
    back: List[str] = field(default_factory=list)     # back rivelati
    mega: Optional[str] = None                        # chiave del Pokémon megaevoluto
    mega_forme: Optional[str] = None                  # es. "Garchomp-Mega-Z"
    showteam: bool = False                            # team sheet aperto (OTS)
    moves: Dict[str, Counter] = field(default_factory=dict)  # chiave -> Counter(mossa)


@dataclass
class ParsedLog:
    """Log Showdown parsato in forma neutra (non ancora orientato sul giocatore)."""
    replay_id: str
    format: str = ""
    winner: Optional[str] = None
    sides: Dict[str, SideData] = field(default_factory=dict)


@dataclass
class GameSummary:
    """Log orientato: "me" = il giocatore del foglio, "opp" = l'avversario."""
    me: SideData
    opp: SideData
    won: Optional[bool]
    format: str = ""


@dataclass
class DashboardGame:
    """Riga del foglio arricchita con l'analisi nativa del replay."""
    row: SheetGameRow
    replay_id: str                    # slug completo (inclusa eventuale password)
    match_id: str                     # id usato nel DB interno
    summary: Optional[GameSummary] = None
    error: str = ""

    # ---- helper di presentazione ----
    @property
    def game_no(self) -> int:
        return self.row.game_no

    @property
    def result(self) -> Optional[str]:
        if self.row.result in ("Win", "Loss"):
            return self.row.result
        if self.summary and self.summary.won is not None:
            return "Win" if self.summary.won else "Loss"
        return None

    @property
    def won(self) -> Optional[bool]:
        r = self.result
        return None if r is None else r == "Win"

    @property
    def opponent(self) -> str:
        if self.row.opponent:
            return self.row.opponent
        return self.summary.opp.name if self.summary else ""

    @property
    def ots(self) -> Optional[bool]:
        if self.row.ots is not None:
            return self.row.ots
        return self.summary.opp.showteam if self.summary else None

    @property
    def opp_elo_value(self) -> Optional[int]:
        """ELO numerico dell'avversario (foglio → fallback rating del log)."""
        import re
        m = re.search(r"\d{3,4}", self.row.elo_opp or "")
        if m:
            return int(m.group(0))
        if self.summary and self.summary.opp.rating:
            return self.summary.opp.rating
        return None


@dataclass
class DashboardData:
    """Risultato completo del caricamento della dashboard."""
    sheet: SheetData
    games: List[DashboardGame] = field(default_factory=list)
    my_names: List[str] = field(default_factory=list)
