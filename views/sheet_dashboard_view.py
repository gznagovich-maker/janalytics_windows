"""
sheet_dashboard_view.py
=======================
Dashboard di analisi che integra un Google Sheet PASRS (URL fornito
dall'utente a runtime) con l'analisi nativa dei replay di JAnalytics.

Sezioni (QTabWidget):
  1. Move Usage      — grafici a torta per Pokémon (dati dal foglio "Move Usage")
  2. Matchup Stats   — Best / Worst Matchups, Highest / Lowest Attendance
  3. Usage           — Win%, Lead Win%, Mega Win%, Leads; click su una coppia
                       lead → pop-up con i team avversari affrontati
  4. Game By Game    — tabella dei game con i filtri del foglio; il link
                       "Replay" apre il visualizzatore INTERNO dell'app

Architettura: View (QWidget) + ViewModel (QObject) + worker QThread.
Identità Pokémon sempre "Specie + Forma" (vedi replay_resolver).
"""

from typing import Dict, List, Optional

from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import QMargins, QObject, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFrame, QGraphicsOpacityEffect,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from config.theme import Fonts, Palette, Spacing
from src.domain.sheet_dashboard import dashboard_stats as ds
from src.domain.sheet_dashboard.dashboard_worker import ReplayImportWorker, SheetDashboardWorker
from src.domain.sheet_dashboard.models import DashboardData, DashboardGame, MoveUsageChart
from src.utils.icon_utils import get_pokemon_icon_path

# ── Stili condivisi ───────────────────────────────────────────────

_CARD_QSS = (
    f"QFrame#dashCard {{ background-color: {Palette.BG_SURFACE_ELEVATED};"
    f" border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 8px; }}"
)
_TITLE_QSS = (
    f"font-size: {Fonts.SIZE_LARGE}; font-weight: {Fonts.WEIGHT_SEMI}; color: {Palette.PRIMARY};"
    " background: transparent; border: none;"
)
_MUTED_QSS = f"color: {Palette.TEXT_MUTED}; font-size: {Fonts.SIZE_SMALL}; background: transparent; border: none;"
_TEXT_QSS = f"color: {Palette.TEXT_PRIMARY}; font-size: {Fonts.SIZE_BASE}; background: transparent; border: none;"
_TABLE_QSS = (
    f"QTableWidget {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY};"
    f" gridline-color: {Palette.BORDER_COLOR}; border: 1px solid {Palette.BORDER_LIGHT};"
    f" border-radius: 6px; font-size: {Fonts.SIZE_BASE}; }}"
    f"QTableWidget::item {{ padding: 2px 6px; }}"
    f"QTableWidget::item:selected {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; }}"
    f"QHeaderView::section {{ background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_MUTED};"
    f" border: none; border-bottom: 1px solid {Palette.BORDER_LIGHT}; padding: 6px;"
    f" font-size: {Fonts.SIZE_SMALL}; font-weight: {Fonts.WEIGHT_SEMI}; }}"
)
_COMBO_QSS = (
    f"QComboBox, QSpinBox, QLineEdit {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY};"
    f" border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 4px; padding: 4px 8px; min-height: 22px; }}"
    f"QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {Palette.PRIMARY}; }}"
)
_BTN_QSS = (
    f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.PRIMARY};"
    f" border: 1px solid {Palette.PRIMARY_DIM}; border-radius: 4px; padding: 5px 12px; }}"
    f"QPushButton:hover {{ color: {Palette.PRIMARY_BRIGHT}; border-color: {Palette.PRIMARY}; }}"
    f"QPushButton:pressed {{ background-color: {Palette.PRIMARY_DIM}; color: {Palette.TEXT_PRIMARY}; }}"
    f"QPushButton:disabled {{ color: {Palette.TEXT_MUTED}; border-color: {Palette.BORDER_LIGHT}; }}"
)

ROW_H = 50


def _pct_color(p: Optional[float]) -> str:
    if p is None:
        return Palette.TEXT_MUTED
    if p >= 0.6:
        return Palette.SUCCESS_BRIGHT
    if p < 0.45:
        return Palette.DANGER_BRIGHT
    return Palette.TEXT_PRIMARY


def _card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("dashCard")
    f.setStyleSheet(_CARD_QSS)
    return f


def _label(text: str, qss: str = _TEXT_QSS) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(qss)
    return lbl


# ── Sprite ────────────────────────────────────────────────────────

class _SpriteCache:
    _cache: Dict[tuple, QPixmap] = {}

    @classmethod
    def get(cls, species: str, size: int) -> Optional[QPixmap]:
        key = (species, size)
        if key not in cls._cache:
            path = get_pokemon_icon_path(species) if species else None
            pm = QPixmap(path) if path else QPixmap()
            cls._cache[key] = pm.scaled(
                size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            ) if not pm.isNull() else QPixmap()
        pm = cls._cache[key]
        return None if pm.isNull() else pm


class PokemonSprite(QLabel):
    """
    Sprite di un Pokémon con evidenziazione opzionale:
      mode="lead"  → bordo + sfondo PRIMARY (lead avversaria)
      mode="back"  → bordo SECONDARY (back avversario)
      mode="dim"   → opacità ridotta (non portato)
    """

    def __init__(self, species: str, size: int = 36, mode: str = "", show_tooltip: bool = True):
        super().__init__()
        box = size + 8
        self.setFixedSize(box, box)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = _SpriteCache.get(species, size)
        if pm:
            self.setPixmap(pm)
        else:
            self.setText(species[:3] if species else "—")
            self.setStyleSheet(_MUTED_QSS)
        if show_tooltip and species:
            self.setToolTip(species)

        border, bg = "transparent", "transparent"
        if mode == "lead":
            border, bg = Palette.PRIMARY, "rgba(196,154,60,0.22)"
        elif mode == "back":
            border, bg = Palette.SECONDARY, "rgba(133,119,168,0.14)"
        if mode in ("lead", "back"):
            self.setStyleSheet(f"QLabel {{ border: 2px solid {border}; border-radius: 6px; background: {bg}; }}")
        elif pm:
            self.setStyleSheet("QLabel { background: transparent; border: none; }")
        if mode == "dim":
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.35)
            self.setGraphicsEffect(eff)


def sprite_row(species: List[str], size: int = 30, modes: Optional[Dict[str, str]] = None,
               separator_after: Optional[int] = None) -> QFrame:
    w = QFrame()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 0, 2, 0)
    lay.setSpacing(2)
    for i, s in enumerate(species):
        lay.addWidget(PokemonSprite(s, size, (modes or {}).get(s, "")))
        if separator_after is not None and i == separator_after - 1 and i < len(species) - 1:
            sep = QFrame()
            sep.setFixedSize(1, size)
            sep.setStyleSheet(f"background: {Palette.BORDER_LIGHT};")
            lay.addWidget(sep)
    lay.addStretch()
    return w

def sprite_row_with_badges(lead: List[str], back: List[str], size: int = 28) -> QFrame:
    w = QFrame()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    
    if lead:
        lbl = _label("LEAD", f"font-size: 10px; font-weight: 700; color: {Palette.PRIMARY}; background: rgba(0,0,0,0.2); padding: 2px 4px; border-radius: 3px;")
        lay.addWidget(lbl)
        for s in lead: lay.addWidget(PokemonSprite(s, size))
            
    if back:
        if lead:
            sep = QFrame()
            sep.setFixedSize(1, size)
            sep.setStyleSheet(f"background: {Palette.BORDER_LIGHT}; margin: 0 4px;")
            lay.addWidget(sep)
            
        lbl = _label("BACK", f"font-size: 10px; font-weight: 700; color: {Palette.TEXT_MUTED}; background: rgba(0,0,0,0.2); padding: 2px 4px; border-radius: 3px;")
        lay.addWidget(lbl)
        for s in back: lay.addWidget(PokemonSprite(s, size))
            
    lay.addStretch()
    return w


def pokemon_with_name(species: str, size: int = 36) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 0, 4, 0)
    lay.setSpacing(6)
    lay.addWidget(PokemonSprite(species, size))
    lay.addWidget(_label(species))
    lay.addStretch()
    return w


# ── ViewModel ─────────────────────────────────────────────────────

class SheetDashboardViewModel(QObject):
    """Stato della dashboard: dati caricati + filtro Game By Game corrente."""
    data_changed = Signal()
    filter_changed = Signal()

    def __init__(self):
        super().__init__()
        self.data: Optional[DashboardData] = None
        self.filter = ds.GameFilter()

    def set_data(self, data: DashboardData):
        self.data = data
        self.filter = ds.GameFilter()
        self.data_changed.emit()

    def set_filter(self, flt: ds.GameFilter):
        if flt != self.filter:
            self.filter = flt
            self.filter_changed.emit()

    @property
    def games(self) -> List[DashboardGame]:
        return self.data.games if self.data else []

    def filtered_games(self) -> List[DashboardGame]:
        return ds.apply_filter(self.games, self.filter)

    def move_usage(self) -> List[MoveUsageChart]:
        if self.data and self.data.sheet.move_usage:
            return self.data.sheet.move_usage
        return ds.native_move_usage(self.games)


# ── 1. Move Usage ─────────────────────────────────────────────────

# ── 2. Matchup Stats ──────────────────────────────────────────────

class MatchupStatsTab(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, Spacing.SM, 0, 0)
        root.setSpacing(Spacing.MD)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(Spacing.LG)
        
        self.boxes = {
            "best": QVBoxLayout(),
            "worst": QVBoxLayout(),
            "high": QVBoxLayout(),
            "low": QVBoxLayout()
        }
        
        def _add_box(row: int, col: int, key: str, title: str):
            box = QFrame()
            box.setStyleSheet(_CARD_QSS)
            lay = QVBoxLayout(box)
            lay.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
            lay.setSpacing(Spacing.MD)
            lay.addWidget(_label(title, _TITLE_QSS))
            self.boxes[key] = QVBoxLayout()
            lay.addLayout(self.boxes[key])
            lay.addStretch()
            self.grid.addWidget(box, row, col)

        _add_box(0, 0, "best", "Migliori (Best Matchups)")
        _add_box(0, 1, "worst", "Peggiori (Worst Matchups)")
        _add_box(1, 0, "high", "Più visti (Highest Attendance)")
        _add_box(1, 1, "low", "Meno visti (Lowest Attendance)")
        
        scroll.setWidget(self.container)
        root.addWidget(scroll, 1)

    def set_games(self, games: List['DashboardGame']):
        ms = ds.matchup_stats(games, min_games=3)
        self._fill("best", [(e.pokemon, "beat", e.wins_brought, e.brought, e.win_pct) for e in ms.best])
        self._fill("worst", [(e.pokemon, "beat", e.wins_brought, e.brought, e.win_pct) for e in ms.worst])
        self._fill("high", [(e.pokemon, "seen", e.brought, e.games, e.attendance_pct) for e in ms.highest_attendance])
        self._fill("low", [(e.pokemon, "seen", e.brought, e.games, e.attendance_pct) for e in ms.lowest_attendance])

    def _fill(self, key: str, rows):
        box = self.boxes[key]
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not rows:
            box.addWidget(_label("Dati insufficienti.", _MUTED_QSS))
            return
        for species, verb, a, b, pct in rows:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(Spacing.SM)
            h.addWidget(PokemonSprite(species, 40))
            v = QVBoxLayout()
            v.setSpacing(0)
            v.addWidget(_label(species))
            v.addWidget(_label(f"{verb} {a} of {b} games", _MUTED_QSS))
            h.addLayout(v, 1)
            color = _pct_color(pct) if verb == "beat" else Palette.TEXT_PRIMARY
            h.addWidget(_label(f"({pct * 100:.0f}%)",
                               f"color: {color}; font-size: {Fonts.SIZE_MEDIUM}; font-weight: {Fonts.WEIGHT_SEMI};"
                               " background: transparent; border: none;"))
            box.addWidget(row)



def _make_table(headers: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setStyleSheet(_TABLE_QSS)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(ROW_H)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setShowGrid(False)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return t

def _record_item(rec: Optional[ds.Record]) -> QTableWidgetItem:
    if rec is None or not rec.games:
        it = QTableWidgetItem("—")
        it.setForeground(QColor(Palette.TEXT_MUTED))
    else:
        it = QTableWidgetItem(f"{rec.wins} of {rec.games}   {rec.pct_text()}")
        it.setForeground(QColor(_pct_color(rec.pct)))
    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return it


class PokemonStatsTab(QWidget):
    lead_clicked = Signal(tuple)       # LeadPair
    _FALLBACK_COLORS = ["#C49A3C", "#8577A8", "#607080", "#3D7A5A", "#8A3838", "#D4AA52", "#8A9DB0", "#5A5075"]

    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, Spacing.SM, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.container = QWidget()
        root = QVBoxLayout(self.container)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(Spacing.LG)
        
        # 1. Global Win% Header
        self.head_box = QFrame()
        self.head_box.setStyleSheet(_CARD_QSS)
        head_lay = QHBoxLayout(self.head_box)
        head_lay.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        self.lbl_filter = _label("", _MUTED_QSS)
        head_lay.addWidget(self.lbl_filter)
        head_lay.addStretch()
        self.stat_labels = {}
        for key, title in (("total", "Win%"), ("ots", "OTS Win%"), ("cts", "CTS Win%")):
            card = _card()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
            cl.addWidget(_label(title, _MUTED_QSS))
            val = _label("—", f"font-size: {Fonts.SIZE_DISPLAY}; font-weight: {Fonts.WEIGHT_BOLD}; color: {Palette.TEXT_PRIMARY}; background: transparent; border: none;")
            cl.addWidget(val)
            sub = _label("", _MUTED_QSS)
            cl.addWidget(sub)
            self.stat_labels[key] = (val, sub)
            head_lay.addWidget(card)
        root.addWidget(self.head_box)

        # 2. Pokemon Tables
        body = QHBoxLayout()
        body.setSpacing(Spacing.MD)
        left = QVBoxLayout()
        left.addWidget(_label("Win % · Lead Win % · Mega Win %", _TITLE_QSS))
        self.tbl_pokemon = _make_table(["Pokémon", "Win %", "Lead Win %", "Mega Win %"])
        self.tbl_pokemon.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            self.tbl_pokemon.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_pokemon.setMinimumHeight(400)
        left.addWidget(self.tbl_pokemon)
        body.addLayout(left, 5)

        right = QVBoxLayout()
        top_r = QHBoxLayout()
        top_r.addWidget(_label("Most Common Leads Win%", _TITLE_QSS))
        top_r.addStretch()
        self.chk_all = QCheckBox("Mostra tutte le lead")
        self.chk_all.setStyleSheet(_MUTED_QSS)
        self.chk_all.toggled.connect(lambda _: self._refresh_leads())
        top_r.addWidget(self.chk_all)
        right.addLayout(top_r)
        self.tbl_common = self._lead_table()
        self.tbl_common.setMinimumHeight(200)
        right.addWidget(self.tbl_common)
        right.addWidget(_label("Best Leads Win%", _TITLE_QSS))
        self.tbl_best = self._lead_table()
        self.tbl_best.setMinimumHeight(200)
        right.addWidget(self.tbl_best)
        right.addWidget(_label("Clicca su una coppia lead per vedere i team avversari affrontati.", _MUTED_QSS))
        body.addLayout(right, 6)
        root.addLayout(body)

        # 3. Move Usage
        moves_layout = QVBoxLayout()
        moves_layout.setSpacing(Spacing.SM)
        self.lbl_moves_title = _label("Move Usage", _TITLE_QSS)
        moves_layout.addWidget(self.lbl_moves_title)
        self.lbl_source = _label("", _MUTED_QSS)
        moves_layout.addWidget(self.lbl_source)
        
        self.moves_container = QWidget()
        self.moves_grid = QGridLayout(self.moves_container)
        self.moves_grid.setContentsMargins(0,0,0,0)
        self.moves_grid.setSpacing(Spacing.MD)
        moves_layout.addWidget(self.moves_container)
        
        root.addLayout(moves_layout)
        
        scroll.setWidget(self.container)
        main_layout.addWidget(scroll, 1)

        self._games: List['DashboardGame'] = []
        self._stats: Optional[ds.UsageStats] = None

    def _lead_table(self) -> QTableWidget:
        t = _make_table(["Lead", "Game", "Win %"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        t.setCursor(Qt.CursorShape.PointingHandCursor)
        t.cellClicked.connect(lambda r, _c, tbl=t: self._on_lead_row(tbl, r))
        return t

    def _on_lead_row(self, tbl: QTableWidget, row: int):
        it = tbl.item(row, 1)
        pair = it.data(Qt.ItemDataRole.UserRole) if it else None
        if pair:
            self.lead_clicked.emit(tuple(pair))

    def set_stats(self, games: List['DashboardGame'], total_games: int, stats: ds.UsageStats, charts: List['MoveUsageChart']):
        self._games = games
        self._stats = stats
        st = self._stats
        
        self.lbl_filter.setText(f"Statistiche secondo il filtro Game By Game: {len(games)} di {total_games} game.")
        for key, rec in (("total", st.total), ("ots", st.ots), ("cts", st.cts)):
            val, sub = self.stat_labels[key]
            val.setText(rec.pct_text(1 if key == "total" else 0))
            val.setStyleSheet(f"font-size: {Fonts.SIZE_DISPLAY}; font-weight: {Fonts.WEIGHT_BOLD}; color: {_pct_color(rec.pct)}; background: transparent; border: none;")
            sub.setText(f"{rec.wins} of {rec.games}" if rec.games else "")

        while self.moves_grid.count():
            item = self.moves_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not charts:
            self.lbl_source.setText("Nessun dato di utilizzo mosse disponibile.")
        else:
            native = charts[0].source == "native"
            self.lbl_source.setText("Fonte: calcolo nativo dai replay (il foglio non contiene grafici)." if native else "Fonte: grafici del foglio Move Usage.")
            for i, chart in enumerate(charts):
                self.moves_grid.addWidget(self._build_card(chart), i // 6, i % 6)

        t = self.tbl_pokemon
        t.setRowCount(0)
        for pu in st.pokemon:
            r = t.rowCount()
            t.insertRow(r)
            t.setCellWidget(r, 0, pokemon_with_name(pu.pokemon))
            t.setItem(r, 0, QTableWidgetItem(""))
            t.setItem(r, 1, _record_item(pu.brought))
            t.setItem(r, 2, _record_item(pu.lead))
            t.setItem(r, 3, _record_item(pu.mega))
        self._refresh_leads()

    def _build_card(self, chart: 'MoveUsageChart') -> QFrame:
        card = _card()
        card.setFixedSize(260, 290)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        header = QHBoxLayout()
        header.addWidget(PokemonSprite(chart.pokemon, 40))
        header.addWidget(_label(chart.pokemon, _TITLE_QSS))
        header.addStretch()
        total = sum(s.count for s in chart.slices)
        header.addWidget(_label(f"{int(total)} usi", _MUTED_QSS))
        lay.addLayout(header)

        from PySide6.QtCharts import QChart, QChartView, QPieSeries
        series = QPieSeries()
        for i, sl in enumerate(chart.slices):
            pct = sl.count / total * 100 if total else 0
            s = series.append(f"{sl.move}  {int(sl.count)}  ({pct:.0f}%)", sl.count)
            s.setBrush(QColor(sl.color or self._FALLBACK_COLORS[i % len(self._FALLBACK_COLORS)]))
            s.setBorderColor(QColor(Palette.BG_SURFACE_ELEVATED))
            s.setLabelColor(QColor(Palette.TEXT_PRIMARY))
            s.hovered.connect(lambda state, sl_=s: (sl_.setExploded(state), sl_.setLabelVisible(state)))
        series.setPieSize(0.78)

        qchart = QChart()
        qchart.addSeries(series)
        qchart.setBackgroundBrush(QBrush(QColor(Palette.BG_SURFACE_ELEVATED)))
        qchart.setBackgroundRoundness(0)
        qchart.setMargins(QMargins(0, 0, 0, 0))
        qchart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        legend = qchart.legend()
        legend.setAlignment(Qt.AlignmentFlag.AlignRight)
        legend.setLabelColor(QColor(Palette.TEXT_PRIMARY))
        legend.setFont(QFont("Segoe UI", 8))

        view = QChartView(qchart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(view)
        return card

    def _refresh_leads(self):
        if not self._stats:
            return
        n = None if self.chk_all.isChecked() else 6
        self._fill_leads(self.tbl_common, self._stats.common_leads[:n])
        self._fill_leads(self.tbl_best, self._stats.best_leads[:n])

    def _fill_leads(self, t: QTableWidget, rows):
        t.setRowCount(0)
        for pair, rec in rows:
            r = t.rowCount()
            t.insertRow(r)
            w = QWidget()
            w.setStyleSheet("background: transparent;")
            h = QHBoxLayout(w)
            h.setContentsMargins(4, 0, 4, 0)
            h.setSpacing(4)
            for s in pair:
                h.addWidget(PokemonSprite(s, 34))
            h.addWidget(_label(" + ".join(pair), _MUTED_QSS))
            h.addStretch()
            w.setToolTip("Clicca per vedere i team avversari affrontati con questa lead")
            t.setCellWidget(r, 0, w)
            t.setItem(r, 0, QTableWidgetItem(""))
            it = QTableWidgetItem(f"{rec.wins} of {rec.games} games")
            it.setData(Qt.ItemDataRole.UserRole, list(pair))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(r, 1, it)
            pct = QTableWidgetItem(rec.pct_text())
            pct.setForeground(QColor(_pct_color(rec.pct)))
            pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            t.setItem(r, 2, pct)


# ── Pop-up: team avversari per coppia lead ────────────────────────

class LeadOpponentsDialog(QDialog):
    replay_requested = Signal(object)      # DashboardGame

    def __init__(self, pair: tuple, games: List[DashboardGame], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Lead {pair[0]} + {pair[1]} — team avversari")
        self.setModal(True)
        self.resize(1000, 660)
        self.setStyleSheet(f"QDialog {{ background-color: {Palette.BG_APP}; }}" + _BTN_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        rec = ds.Record()
        for g in games:
            if g.won is not None:
                rec.add(g.won)
        head = QHBoxLayout()
        for s in pair:
            head.addWidget(PokemonSprite(s, 48))
        tv = QVBoxLayout()
        tv.addWidget(_label(f"{pair[0]} + {pair[1]}", _TITLE_QSS))
        tv.addWidget(_label(f"Usata come lead in {len(games)} game · {rec.wins} of {rec.games} vinti "
                            f"({rec.pct_text()})", _MUTED_QSS))
        head.addLayout(tv, 1)
        root.addLayout(head)

        legend = QHBoxLayout()
        legend.setSpacing(Spacing.MD)
        for mode, text in (("lead", "Lead avversaria"), ("back", "Back avversario"), ("dim", "Non portato")):
            chip = QHBoxLayout()
            box = QLabel()
            box.setFixedSize(16, 16)
            if mode == "lead":
                box.setStyleSheet(f"border: 2px solid {Palette.PRIMARY}; background: rgba(196,154,60,0.22); border-radius: 3px;")
            elif mode == "back":
                box.setStyleSheet(f"border: 2px solid {Palette.SECONDARY}; background: rgba(133,119,168,0.14); border-radius: 3px;")
            else:
                box.setStyleSheet(f"border: 1px dashed {Palette.TEXT_MUTED}; border-radius: 3px;")
            chip.addWidget(box)
            chip.addWidget(_label(text, _MUTED_QSS))
            legend.addLayout(chip)
        legend.addStretch()
        root.addLayout(legend)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cont = QWidget()
        vl = QVBoxLayout(cont)
        vl.setSpacing(Spacing.SM)
        for g in games:
            vl.addWidget(self._game_card(g))
        vl.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

        close = QPushButton("Chiudi")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    def _game_card(self, g: DashboardGame) -> QFrame:
        card = _card()
        h = QHBoxLayout(card)
        h.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        h.setSpacing(Spacing.MD)

        info = QVBoxLayout()
        info.setSpacing(2)
        res = g.result or "?"
        color = Palette.SUCCESS_BRIGHT if res == "Win" else Palette.DANGER_BRIGHT if res == "Loss" else Palette.TEXT_MUTED
        info.addWidget(_label(f"Game {g.game_no} · <span style='color:{color}; font-weight:600'>{res}</span>"))
        info.addWidget(_label(f"vs {g.opponent}", _MUTED_QSS))
        wrap = QWidget()
        wrap.setFixedWidth(170)
        wrap.setLayout(info)
        wrap.setStyleSheet("background: transparent;")
        h.addWidget(wrap)

        s = g.summary
        modes = {}
        for k in s.opp.team:
            modes[k] = "lead" if k in s.opp.lead else "back" if k in s.opp.back else "dim"
        team = list(s.opp.team) + [k for k in s.opp.lead + s.opp.back if k not in s.opp.team]
        h.addWidget(sprite_row(team, 40, modes), 1)

        mine = QVBoxLayout()
        mine.setSpacing(0)
        mine.addWidget(_label("Tuoi back", _MUTED_QSS))
        mine.addWidget(sprite_row(s.me.back, 24))
        h.addLayout(mine)

        btn = QPushButton("▶ Replay")
        btn.setToolTip("Apri nel visualizzatore replay interno")
        btn.setEnabled(bool(g.replay_id))
        btn.clicked.connect(lambda _=False, gg=g: self._open(gg))
        h.addWidget(btn)
        return card

    def _open(self, g: DashboardGame):
        self.replay_requested.emit(g)
        self.accept()


# ── 4. Game By Game ───────────────────────────────────────────────

class GameByGameTab(QWidget):
    filter_requested = Signal(object)      # ds.GameFilter
    replay_clicked = Signal(object)        # DashboardGame

    COLS = ["Game", "Result", "", "Opponent", "Replay", "Opposing Team",
            "Your Picks", "Their Picks", "Mega You", "Mega Opp", "OTS?", "ELO You", "ELO Opp"]

    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, Spacing.SM, 0, 0)
        root.setSpacing(Spacing.SM)

        # Pannello filtri (stesso layout logico del foglio)
        panel = _card()
        panel.setStyleSheet(_CARD_QSS + _COMBO_QSS + _BTN_QSS)
        grid = QGridLayout(panel)
        grid.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        grid.setHorizontalSpacing(Spacing.MD)
        grid.setVerticalSpacing(4)

        self.combos: Dict[str, QComboBox] = {}

        def combo(key: str) -> QComboBox:
            c = QComboBox()
            c.setMinimumWidth(130)
            c.currentIndexChanged.connect(self._emit_filter)
            self.combos[key] = c
            return c

        def group(title: str, col: int, span: int = 1):
            grid.addWidget(_label(title, f"color: {Palette.PRIMARY}; font-weight: {Fonts.WEIGHT_SEMI};"
                                         " background: transparent; border: none;"), 0, col, 1, span)

        group("Result", 0)
        grid.addWidget(combo("result"), 2, 0)
        group("Opposing Pokémon", 1)
        grid.addWidget(combo("opp_pokemon"), 2, 1)

        group("Player", 2, 2)
        grid.addWidget(_label("Lead", _MUTED_QSS), 1, 2)
        grid.addWidget(combo("my_lead"), 2, 2)
        grid.addWidget(_label("Back", _MUTED_QSS), 1, 3)
        grid.addWidget(combo("my_back"), 2, 3)

        group("Opponent", 4, 2)
        grid.addWidget(_label("Lead", _MUTED_QSS), 1, 4)
        grid.addWidget(combo("opp_lead"), 2, 4)
        grid.addWidget(_label("Back", _MUTED_QSS), 1, 5)
        grid.addWidget(combo("opp_back"), 2, 5)

        group("Mega", 6, 2)
        grid.addWidget(_label("You", _MUTED_QSS), 1, 6)
        grid.addWidget(combo("my_mega"), 2, 6)
        grid.addWidget(_label("Opp", _MUTED_QSS), 1, 7)
        grid.addWidget(combo("opp_mega"), 2, 7)

        group("OTS?", 8)
        grid.addWidget(combo("ots"), 2, 8)

        group("Min Elo", 9)
        self.spin_elo = QSpinBox()
        self.spin_elo.setRange(0, 3000)
        self.spin_elo.setSingleStep(50)
        self.spin_elo.setSpecialValueText("-any-")
        self.spin_elo.valueChanged.connect(self._emit_filter)
        grid.addWidget(self.spin_elo, 2, 9)

        self.btn_reset = QPushButton("Reset filtri")
        self.btn_reset.clicked.connect(self.reset_filters)
        grid.addWidget(self.btn_reset, 2, 10)
        root.addWidget(panel)

        self.lbl_count = _label("", _MUTED_QSS)
        root.addWidget(self.lbl_count)

        self.table = _make_table(self.COLS)
        hh = self.table.horizontalHeader()
        for c in range(len(self.COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.table, 1)

        self._games: List[DashboardGame] = []
        self._suspend = False

    # ---- filtri ----
    def set_options(self, options: Dict[str, List[str]]):
        self._suspend = True
        for key, c in self.combos.items():
            c.clear()
            c.addItems(options.get(key, [ds.ANY]))
        self.spin_elo.setValue(0)
        self._suspend = False

    def reset_filters(self):
        self._suspend = True
        for c in self.combos.values():
            c.setCurrentIndex(0)
        self.spin_elo.setValue(0)
        self._suspend = False
        self._emit_filter()

    def current_filter(self) -> ds.GameFilter:
        v = {k: (c.currentText() or ds.ANY) for k, c in self.combos.items()}
        return ds.GameFilter(min_elo=self.spin_elo.value() or None, **v)

    def _emit_filter(self, *_):
        if not self._suspend:
            self.filter_requested.emit(self.current_filter())

    # ---- tabella ----
    def set_games(self, games: List[DashboardGame], total: int):
        self._games = games
        self.lbl_count.setText(f"{len(games)} di {total} game · doppio click su una riga o "
                               f"\"Replay\" per aprire il visualizzatore interno")
        t = self.table
        t.setUpdatesEnabled(False)
        t.setRowCount(0)
        for g in games:
            r = t.rowCount()
            t.insertRow(r)
            self._set_text(r, 0, str(g.game_no), center=True)
            res = g.result or "?"
            it = self._set_text(r, 1, res, center=True)
            if res in ("Win", "Loss"):
                it.setForeground(QColor(Palette.SUCCESS_BRIGHT if res == "Win" else Palette.DANGER_BRIGHT))
                it.setBackground(QColor(61, 107, 80, 50) if res == "Win" else QColor(138, 56, 56, 50))
            self._set_text(r, 2, "vs", muted=True, center=True)
            self._set_text(r, 3, g.opponent)

            btn = QPushButton("▶ Replay")
            btn.setStyleSheet(_BTN_QSS)
            btn.setMinimumWidth(96)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Apri nel visualizzatore replay interno di JAnalytics")
            btn.setEnabled(bool(g.replay_id))
            btn.clicked.connect(lambda _=False, gg=g: self.replay_clicked.emit(gg))
            
            btn_wrap = QWidget()
            btn_lay = QVBoxLayout(btn_wrap)
            btn_lay.setContentsMargins(4, 4, 4, 4)
            btn_lay.setSpacing(0)
            btn_lay.addWidget(btn)
            t.setCellWidget(r, 4, btn_wrap)

            s = g.summary
            if s:
                t.setCellWidget(r, 5, sprite_row(s.opp.team, 28))
                w_mine = sprite_row_with_badges(s.me.lead[:2], s.me.back, 28)
                w_mine.setStyleSheet("background-color: rgba(61, 107, 80, 0.15); border-radius: 4px; margin: 2px;")
                t.setCellWidget(r, 6, w_mine)
                
                w_opp = sprite_row_with_badges(s.opp.lead[:2], s.opp.back, 28)
                w_opp.setStyleSheet("background-color: rgba(138, 56, 56, 0.15); border-radius: 4px; margin: 2px;")
                t.setCellWidget(r, 7, w_opp)
                
                t.setCellWidget(r, 8, sprite_row([s.me.mega], 28) if s.me.mega else self._dash())
                t.setCellWidget(r, 9, sprite_row([s.opp.mega], 28) if s.opp.mega else self._dash())
            else:
                self._set_text(r, 5, g.error or "Replay non analizzato", muted=True)
            ots = g.ots
            self._set_text(r, 10, "YES" if ots else "NO" if ots is False else "—", center=True)
            self._set_text(r, 11, g.row.elo_you or (str(s.me.rating) if s and s.me.rating else ""), center=True)
            self._set_text(r, 12, g.row.elo_opp or (str(s.opp.rating) if s and s.opp.rating else ""), center=True)
        t.setUpdatesEnabled(True)

    def _dash(self) -> QLabel:
        lbl = _label("—", _MUTED_QSS)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    def _set_text(self, r: int, c: int, text: str, muted: bool = False, center: bool = False) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        if muted:
            it.setForeground(QColor(Palette.TEXT_MUTED))
        if center:
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(r, c, it)
        return it

    def _on_double_click(self, row: int, _col: int):
        if 0 <= row < len(self._games):
            self.replay_clicked.emit(self._games[row])


# ── Vista principale ──────────────────────────────────────────────

class SheetDashboardView(QWidget):
    """Dashboard Google Sheet + analisi nativa. Emette replay_requested(match_id)."""
    replay_requested = Signal(str)

    _SETTINGS_KEY = "sheet_dashboard/last_url"

    def __init__(self, parent_main=None):
        super().__init__()
        self.parent_main = parent_main
        self.vm = SheetDashboardViewModel()
        self._worker: Optional[SheetDashboardWorker] = None
        self._import_worker: Optional[ReplayImportWorker] = None
        self._settings = QSettings("Jorkcorp", "JAnalytics")

        self._build_ui()
        self.vm.data_changed.connect(self._on_data_changed)
        self.vm.filter_changed.connect(self._on_filter_changed)

    # ---- UI ----
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.SM)

        bar = QHBoxLayout()
        bar.setSpacing(Spacing.SM)
        title = _label("Sheet Dashboard", f"font-size: {Fonts.SIZE_TITLE}; font-weight: {Fonts.WEIGHT_SEMI};"
                                          f" color: {Palette.PRIMARY}; background: transparent; border: none;")
        bar.addWidget(title)
        bar.addSpacing(Spacing.MD)
        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("Incolla l'URL del Google Sheet (https://docs.google.com/spreadsheets/d/...)")
        self.edit_url.setStyleSheet(_COMBO_QSS)
        self.edit_url.setText(str(self._settings.value(self._SETTINGS_KEY, "") or ""))
        self.edit_url.returnPressed.connect(self.load)
        bar.addWidget(self.edit_url, 1)
        self.btn_load = QPushButton("Carica")
        self.btn_load.setStyleSheet(_BTN_QSS)
        self.btn_load.clicked.connect(self.load)
        bar.addWidget(self.btn_load)
        root.addLayout(bar)

        status = QHBoxLayout()
        self.lbl_status = _label("Inserisci l'URL di un foglio PASRS pubblico e premi Carica.", _MUTED_QSS)
        self.lbl_status.setWordWrap(True)
        status.addWidget(self.lbl_status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(260)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        status.addWidget(self.progress)
        root.addLayout(status)

        self.tabs = QTabWidget()
        self.tab_matchup = MatchupStatsTab()
        self.tab_usage = PokemonStatsTab()
        self.tab_team = TeamAnalysisTab()
        self.tab_gbg = GameByGameTab()
        self.tabs.addTab(self.tab_matchup, "Matchup Stats")
        self.tabs.addTab(self.tab_usage, "Statistiche Pokémon")
        self.tabs.addTab(self.tab_team, "Team Analysis")
        self.tabs.addTab(self.tab_gbg, "Game By Game")
        self.tabs.setEnabled(False)
        root.addWidget(self.tabs, 1)

        self.tab_usage.lead_clicked.connect(self._show_lead_popup)
        self.tab_gbg.filter_requested.connect(self.vm.set_filter)
        self.tab_gbg.replay_clicked.connect(self.open_replay)
        self.tab_team.replay_requested.connect(self.open_replay)

    # ---- Caricamento ----
    def load(self):
        url = self.edit_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Sheet Dashboard", "Inserisci l'URL del Google Sheet.")
            return
        if self._worker and self._worker.isRunning():
            return
        self._settings.setValue(self._SETTINGS_KEY, url)
        self.btn_load.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.lbl_status.setText("Caricamento in corso...")
        self._worker = SheetDashboardWorker(url, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int, msg: str):
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)
        self.lbl_status.setText(msg)

    def _on_loaded(self, data: DashboardData):
        self.btn_load.setEnabled(True)
        self.progress.hide()
        ok = sum(1 for g in data.games if g.summary)
        parts = [f"{data.sheet.title or 'Foglio'} · giocatore: {', '.join(data.my_names) or '?'} · "
                 f"{len(data.games)} game ({ok} replay analizzati)"]
        parts += data.sheet.warnings
        failed = [g for g in data.games if g.error]
        if failed:
            parts.append(f"{len(failed)} replay con problemi (vedi Game By Game).")
        self.lbl_status.setText("  ·  ".join(parts))
        self.tabs.setEnabled(True)
        self.vm.set_data(data)

    def _on_failed(self, msg: str):
        self.btn_load.setEnabled(True)
        self.progress.hide()
        self.lbl_status.setText(f"Errore: {msg}")
        QMessageBox.critical(self, "Sheet Dashboard", msg)

    # ---- Reazioni al ViewModel ----
    def _on_data_changed(self):
        games = self.vm.games
        self.tab_matchup.set_games(games)
        self.tab_gbg.set_options(ds.filter_options(games))
        self._on_filter_changed()

    def _on_filter_changed(self):
        filtered = self.vm.filtered_games()
        total = len(self.vm.games)
        self.tab_gbg.set_games(filtered, total)
        
        st = ds.usage_stats(filtered, top_n=10**6)
        self.tab_usage.set_stats(filtered, total, st, self.vm.move_usage())
        self.tab_team.set_games(filtered)

    # ---- Pop-up lead ----
    def _show_lead_popup(self, pair: tuple):
        games = ds.lead_pair_games(self.vm.filtered_games(), pair)
        if not games:
            return
        dlg = LeadOpponentsDialog(pair, games, self)
        dlg.replay_requested.connect(self.open_replay)
        dlg.exec()

    # ---- Override link replay → visualizzatore interno ----
    def open_replay(self, game: DashboardGame):
        if not game.replay_id:
            QMessageBox.warning(self, "Replay", "Link replay non valido per questo game.")
            return
        if self._import_worker and self._import_worker.isRunning():
            return
        if self.parent_main and hasattr(self.parent_main, "show_loading"):
            self.parent_main.show_loading(f"Preparazione replay game {game.game_no}...")
        self._import_worker = ReplayImportWorker(game.replay_id, self)
        self._import_worker.finished_ok.connect(self._on_replay_ready)
        self._import_worker.failed.connect(self._on_replay_failed)
        self._import_worker.start()

    def _on_replay_ready(self, match_id: str):
        if self.parent_main and hasattr(self.parent_main, "hide_loading"):
            self.parent_main.hide_loading()
        self.replay_requested.emit(match_id)

    def _on_replay_failed(self, msg: str):
        if self.parent_main and hasattr(self.parent_main, "hide_loading"):
            self.parent_main.hide_loading()
        QMessageBox.critical(self, "Replay", f"Impossibile aprire il replay:\n{msg}")


class DummySession:
    def scalars(self, stmt):
        class DummyScalars:
            def unique(self):
                class DummyUnique:
                    def all(self):
                        return []
                return DummyUnique()
        return DummyScalars()

class VariantDrillDownDialog(QDialog):
    replay_requested = Signal(object)

    def __init__(self, entry: ds.TeamAnalysisEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dettaglio Sotto-Varianti")
        self.resize(850, 600)
        self.setStyleSheet(f"QDialog {{ background-color: {Palette.BG_APP}; }}" + _BTN_QSS + _TABLE_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        
        h = QHBoxLayout()
        for s in entry.group:
            h.addWidget(PokemonSprite(s, 40))
        h.addStretch()
        h.addWidget(_label(f"Variante Base: {entry.wins}/{entry.games} ({entry.win_pct*100:.0f}%)", _TITLE_QSS))
        root.addLayout(h)
        root.addSpacing(Spacing.MD)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.setSpacing(Spacing.MD)
        
        for sub in entry.sub_entries:
            box = QFrame()
            box.setStyleSheet(_CARD_QSS)
            box_lay = QVBoxLayout(box)
            
            top = QHBoxLayout()
            for s in sub.group:
                top.addWidget(PokemonSprite(s, 32))
            top.addStretch()
            color = _pct_color(sub.win_pct)
            top.addWidget(_label(f"Win Rate: {sub.wins}/{sub.games} ({sub.win_pct*100:.0f}%)", f"color: {color}; font-weight: {Fonts.WEIGHT_BOLD};"))
            box_lay.addLayout(top)
            
            replays_lay = QHBoxLayout()
            replays_lay.addWidget(_label("Replay:", _MUTED_QSS))
            for g in sub.match_games:
                btn = QPushButton(f"Game {g.game_no}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                # Formattazione condizionale
                if g.won:
                    btn.setStyleSheet("background-color: #2e7d32; color: white; border: none; padding: 4px 10px; border-radius: 4px;")
                else:
                    btn.setStyleSheet("background-color: #c62828; color: white; border: none; padding: 4px 10px; border-radius: 4px;")
                btn.clicked.connect(lambda _, g_obj=g: self.replay_requested.emit(g_obj))
                replays_lay.addWidget(btn)
            replays_lay.addStretch()
            box_lay.addLayout(replays_lay)
            
            lay.addWidget(box)
            
        lay.addStretch()
        scroll.setWidget(cont)
        root.addWidget(scroll, 1)

def _get_archetype_html(species_list) -> str:
    from src.analytics.archetypes import analizza_archetipo_team
    return analizza_archetipo_team(list(species_list), [], DummySession())

class TeamAnalysisTab(QWidget):
    replay_requested = Signal(object)
    
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, Spacing.SM, 0, 0)
        layout.setSpacing(Spacing.MD)
        
        # Controlli
        ctrl = QHBoxLayout()
        ctrl.addWidget(_label("Analisi Core N:"))
        self.spin_n = QSpinBox()
        self.spin_n.setRange(2, 6)
        self.spin_n.setValue(2)
        ctrl.addWidget(self.spin_n)
        
        ctrl.addSpacing(Spacing.LG)
        ctrl.addWidget(_label("Varianti Distanza M:"))
        self.spin_m = QSpinBox()
        self.spin_m.setRange(0, 6)
        self.spin_m.setValue(2)
        ctrl.addWidget(self.spin_m)
        
        ctrl.addSpacing(Spacing.LG)
        ctrl.addWidget(_label("Filtro Apparizioni minime:"))
        self.spin_apps = QSpinBox()
        self.spin_apps.setRange(1, 100)
        self.spin_apps.setValue(2)
        ctrl.addWidget(self.spin_apps)
        
        ctrl.addStretch()
        layout.addLayout(ctrl)
        
        self.spin_n.valueChanged.connect(self._recalc)
        self.spin_m.valueChanged.connect(self._recalc)
        self.spin_apps.valueChanged.connect(self._recalc)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.container = QWidget()
        root = QVBoxLayout(self.container)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(Spacing.LG)
        
        self.boxes_layout = QVBoxLayout()
        root.addLayout(self.boxes_layout)
        root.addStretch()
        
        scroll.setWidget(self.container)
        layout.addWidget(scroll)
        
        self._games: List['DashboardGame'] = []

    def set_games(self, games: List['DashboardGame']):
        self._games = games
        self._recalc()
        
    def _recalc(self, _val=None):
        while self.boxes_layout.count():
            item = self.boxes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        box = QFrame()
        box.setStyleSheet(_CARD_QSS)
        lay = QVBoxLayout(box)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog = QProgressBar()
        prog.setRange(0,0)
        prog.setFixedWidth(200)
        lay.addWidget(prog)
        lbl = _label("Calcolo in corso...", _MUTED_QSS)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        self.boxes_layout.addWidget(box)
        
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        QApplication.processEvents()
        QTimer.singleShot(50, self._do_calc)

    def _do_calc(self):
        st = ds.team_analysis_stats(self._games, 
                                    n_core=self.spin_n.value(), 
                                    m_dist=self.spin_m.value(), 
                                    min_apps=self.spin_apps.value())
                                    
        while self.boxes_layout.count():
            item = self.boxes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.boxes_layout.addWidget(self._build_section(f"Analisi Core ({self.spin_n.value()}-Pokemon)", st.cores))
        self.boxes_layout.addWidget(self._build_section(f"Analisi Varianti Team (Distanza-{self.spin_m.value()})", st.variants, show_all=True))

    def _build_section(self, title: str, cat: ds.TeamAnalysisCategory, show_all: bool = False) -> QWidget:
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0,0,0,0)
        lay.setSpacing(Spacing.MD)
        lay.addWidget(_label(title, _TITLE_QSS))
        
        grid = QGridLayout()
        grid.setSpacing(Spacing.MD)
        grid.setContentsMargins(0,0,0,0)
        
        grid.addWidget(self._build_col_box("Più Frequenti", cat.most_common), 0, 0)
        grid.addWidget(self._build_col_box("Miglior Win Rate", cat.best), 0, 1)
        grid.addWidget(self._build_col_box("Peggior Win Rate", cat.worst), 0, 2)
        
        lay.addLayout(grid)
        
        if show_all and cat.all_entries:
            box = QFrame()
            box.setStyleSheet(_CARD_QSS)
            box_lay = QVBoxLayout(box)
            box_lay.addWidget(_label("Tutte le Varianti Trovate", _TITLE_QSS))
            box_lay.addWidget(_label("Clicca su una riga per esplorare le sotto-varianti e i replay.", _MUTED_QSS))
            
            table = QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(["Formazione", "Archetipo", "Win Rate %", "Frequenza (Win/Game)"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(40)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setStyleSheet(_TABLE_QSS)
            table.setMinimumHeight(250)
            table.setCursor(Qt.CursorShape.PointingHandCursor)
            
            for e in cat.all_entries:
                r = table.rowCount()
                table.insertRow(r)
                # Formazione
                w = QWidget()
                w.setStyleSheet("background: transparent;")
                h = QHBoxLayout(w)
                h.setContentsMargins(4,0,4,0)
                for s in e.group:
                    h.addWidget(PokemonSprite(s, 32))
                h.addStretch()
                table.setCellWidget(r, 0, w)
                
                # Archetipo
                arch_html = _get_archetype_html(e.group)
                arch_lbl = QLabel(arch_html)
                arch_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arch_lbl.setStyleSheet("background: transparent;")
                table.setCellWidget(r, 1, arch_lbl)
                
                # Win Rate
                color = _pct_color(e.win_pct)
                pct_it = QTableWidgetItem(f"{e.win_pct*100:.0f}%")
                pct_it.setForeground(QColor(color))
                pct_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, 2, pct_it)
                
                # Frequenza
                freq_it = QTableWidgetItem(f"{e.wins} of {e.games}")
                freq_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                freq_it.setData(Qt.ItemDataRole.UserRole, e)
                table.setItem(r, 3, freq_it)
                
            table.itemClicked.connect(lambda it, tbl=table: self._on_variant_clicked(it))
            box_lay.addWidget(table)
            lay.addWidget(box)
            
        return container

    def _build_col_box(self, header: str, entries: List[ds.TeamAnalysisEntry]) -> QFrame:
        box = QFrame()
        box.setStyleSheet(_CARD_QSS)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        lay.addWidget(_label(header, _TITLE_QSS))
        
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Formazione", "Win Rate %", "Freq"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setStyleSheet(_TABLE_QSS)
        table.setMinimumHeight(200)
        
        if not entries:
            lay.addWidget(_label("—", _MUTED_QSS))
        else:
            for e in entries[:3]:
                r = table.rowCount()
                table.insertRow(r)
                w = QWidget()
                w.setStyleSheet("background: transparent;")
                h = QHBoxLayout(w)
                h.setContentsMargins(2,0,2,0)
                h.setSpacing(2)
                for s in e.group:
                    h.addWidget(PokemonSprite(s, 24))
                h.addStretch()
                table.setCellWidget(r, 0, w)
                
                color = _pct_color(e.win_pct)
                pct_it = QTableWidgetItem(f"{e.win_pct*100:.0f}%")
                pct_it.setForeground(QColor(color))
                pct_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, 1, pct_it)
                
                freq_it = QTableWidgetItem(f"{e.wins}/{e.games}")
                freq_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(r, 2, freq_it)
            lay.addWidget(table)
            
        return box

    def _on_variant_clicked(self, it: QTableWidgetItem):
        r = it.row()
        tbl = it.tableWidget()
        data_it = tbl.item(r, 3)
        if not data_it: return
        e = data_it.data(Qt.ItemDataRole.UserRole)
        if e:
            dlg = VariantDrillDownDialog(e, self)
            dlg.replay_requested.connect(self.replay_requested.emit)
            dlg.exec()
