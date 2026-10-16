"""
player_core_tab.py
===================
Tab "Analisi Core & Matchup" della Sheet Dashboard:
  Blocco 1: Analisi dei Core da 4 del Player (tutte le combinazioni C(N, 4))
            - Vittorie: singoli Pokémon avversari sconfitti con numero vittorie
            - Sconfitte: singoli Pokémon avversari contro cui ha perso con numero sconfitte
            - Inutilizzati: etichettati rigorosamente come 'Mai giocato'
  Blocco 2: Analisi dei Singoli Pokémon del Player
            - Best Matchup: Core da 4 avversari contro cui registra il maggior numero di vittorie
            - Worst Matchup: Core da 4 avversari contro cui registra il maggior numero di sconfitte

Stile e colori conformi al Design System Dark / Palette pastello.
"""

from typing import List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from config.theme import Fonts, Palette, Spacing
from src.domain.sheet_dashboard.models import DashboardGame
from src.domain.sheet_dashboard.player_core_analysis import (
    PlayerCoreAnalysisReport, PlayerCoreEntry, SinglePokemonMatchup,
    compute_player_core_analysis,
)
from src.utils.icon_utils import get_pokemon_icon_path
from views.sheet_dashboard_view import (
    _BTN_QSS, _CARD_QSS, _COMBO_QSS, _MUTED_QSS, _TABLE_QSS, _TEXT_QSS, _TITLE_QSS,
    PokemonSprite, _card, _label, _pct_color, pokemon_with_name,
)


def _item(text, color: Optional[str] = None, center: bool = True, bold: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    if center:
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    else:
        it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    if color:
        it.setForeground(QColor(color))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    return it


def _badge(text: str, color: str, bg: Optional[str] = None) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(2, 2, 2, 2)
    lbl = QLabel(text)
    bg_style = f"background-color: {bg};" if bg else "background-color: transparent;"
    lbl.setStyleSheet(
        f"color: {color}; border: 1px solid {color}; border-radius: 4px; padding: 2px 7px;"
        f" font-size: 11px; font-weight: 700; {bg_style}"
    )
    lay.addStretch()
    lay.addWidget(lbl)
    lay.addStretch()
    return w


def _core_icons_widget(core: Tuple[str, ...], size: int = 26) -> QWidget:
    """Mostra 4 icone Pokémon orizzontali compatte con tooltip del nome."""
    w = QWidget()
    w.setStyleSheet("background: transparent; border: none;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    for p in core:
        sp = PokemonSprite(p, size)
        sp.setToolTip(p)
        sp.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(sp)
    names_lbl = QLabel(" / ".join(core))
    names_lbl.setStyleSheet(f"color: {Palette.TEXT_PRIMARY}; font-size: {Fonts.SIZE_SMALL}; margin-left: 6px; background: transparent; border: none;")
    lay.addWidget(names_lbl)
    lay.addStretch()
    return w


class PlayerCoreTab(QWidget):
    """Tab per l'analisi dei Core da 4 e dei Singoli Pokémon vs Core da 4 Avversari."""
    replay_requested = Signal(object)

    def __init__(self):
        super().__init__()
        self._games: List[DashboardGame] = []
        self._report: Optional[PlayerCoreAnalysisReport] = None
        self._selected_pokemon: Optional[str] = None

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, Spacing.SM, 0, 0)
        root.setSpacing(Spacing.MD)

        # ── Barra controlli superiori ─────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(Spacing.MD)

        ctrl.addWidget(_label("Visualizza Sezione:", f"font-size: {Fonts.SIZE_BASE}; color: {Palette.TEXT_PRIMARY}; font-weight: {Fonts.WEIGHT_SEMI};"))
        self.combo_section = QComboBox()
        self.combo_section.addItems([
            "Entrambi i Blocchi",
            "1. Analisi Core da 4 (Player)",
            "2. Analisi Singoli Pokémon (Player)",
        ])
        self.combo_section.setStyleSheet(_COMBO_QSS)
        self.combo_section.currentIndexChanged.connect(self._on_section_filter_changed)
        ctrl.addWidget(self.combo_section)

        ctrl.addSpacing(Spacing.LG)
        ctrl.addWidget(_label("Filtro Core da 4:", _MUTED_QSS))
        self.combo_core_filter = QComboBox()
        self.combo_core_filter.addItems(["Tutti i Core (15)", "Solo Giocati", "Solo 'Mai giocato'"])
        self.combo_core_filter.setStyleSheet(_COMBO_QSS)
        self.combo_core_filter.currentIndexChanged.connect(self._render_cores_block)
        ctrl.addWidget(self.combo_core_filter)

        ctrl.addStretch()
        self.lbl_summary = _label("", _MUTED_QSS)
        ctrl.addWidget(self.lbl_summary)
        root.addLayout(ctrl)

        # ── Scroll Area Principale ────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.main_layout = QVBoxLayout(self.container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(Spacing.LG)

        # Contenitore Blocco 1
        self.box_block1 = QFrame()
        self.box_block1.setObjectName("dashCard")
        self.box_block1.setStyleSheet(_CARD_QSS)
        self.lay_block1 = QVBoxLayout(self.box_block1)
        self.lay_block1.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        self.lay_block1.setSpacing(Spacing.MD)
        self.main_layout.addWidget(self.box_block1)

        # Contenitore Blocco 2
        self.box_block2 = QFrame()
        self.box_block2.setObjectName("dashCard")
        self.box_block2.setStyleSheet(_CARD_QSS)
        self.lay_block2 = QVBoxLayout(self.box_block2)
        self.lay_block2.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        self.lay_block2.setSpacing(Spacing.MD)
        self.main_layout.addWidget(self.box_block2)

        self.main_layout.addStretch()
        scroll.setWidget(self.container)
        root.addWidget(scroll, 1)

    # ── Aggiornamento Dati ────────────────────────────────────────────
    def set_games(self, games: List[DashboardGame], team_hint: Optional[List[str]] = None):
        self._games = games
        self._report = compute_player_core_analysis(games, team_hint=team_hint)
        self._refresh()

    def _refresh(self):
        if not self._report or not self._report.player_team:
            self.lbl_summary.setText("Nessun match o team valido per il player.")
            return

        team_str = ", ".join(self._report.player_team)
        played_cores = sum(1 for c in self._report.cores_4 if c.played)
        self.lbl_summary.setText(
            f"Team Player: <b>{team_str}</b> · Core giocati: <b>{played_cores}/{len(self._report.cores_4)}</b>"
        )

        self._render_cores_block()
        self._render_pokemon_block()

    def _on_section_filter_changed(self, idx: int):
        if idx == 0:
            self.box_block1.show()
            self.box_block2.show()
        elif idx == 1:
            self.box_block1.show()
            self.box_block2.hide()
        elif idx == 2:
            self.box_block1.hide()
            self.box_block2.show()

    # ── Rendering Blocco 1: Analisi Core da 4 ─────────────────────────
    def _render_cores_block(self):
        # Svuota layout
        while self.lay_block1.count():
            item = self.lay_block1.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        header_box = QHBoxLayout()
        header_lbl = _label("1. Analisi dei Core da 4 (Team del Player)", _TITLE_QSS)
        header_box.addWidget(header_lbl)
        header_box.addStretch()
        self.lay_block1.addLayout(header_box)

        desc = _label(
            "Per tutte le 15 possibili combinazioni da 4: statistiche di utilizzo, singoli Pokémon avversari sconfitti "
            "e affrontati nelle sconfitte. I core non schierati sono etichettati come 'Mai giocato'.",
            _MUTED_QSS,
        )
        desc.setWordWrap(True)
        self.lay_block1.addWidget(desc)

        if not self._report or not self._report.cores_4:
            self.lay_block1.addWidget(_label("Nessun core da 4 disponibile.", _MUTED_QSS))
            return

        filter_mode = self.combo_core_filter.currentIndex()
        cores_to_display = []
        for c in self._report.cores_4:
            if filter_mode == 1 and not c.played:
                continue
            if filter_mode == 2 and c.played:
                continue
            cores_to_display.append(c)

        # Tabella principale dei Core da 4
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels([
            "Core da 4 (Player)",
            "Stato / Giocate",
            "Win Rate %",
            "Vittorie (Pokémon Avversari Sconfitti)",
            "Sconfitte (Pokémon Avversari Affrontati)",
        ])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setStyleSheet(_TABLE_QSS)

        for entry in cores_to_display:
            row_idx = table.rowCount()
            table.insertRow(row_idx)

            # Col 0: Icone + Nomi
            table.setCellWidget(row_idx, 0, _core_icons_widget(entry.core, 26))

            # Col 1: Stato / Giocate
            if not entry.played:
                table.setCellWidget(row_idx, 1, _badge("Mai giocato", Palette.TEXT_MUTED))
            else:
                table.setItem(row_idx, 1, _item(f"{entry.games} match ({entry.wins}W - {entry.losses}L)", Palette.TEXT_PRIMARY, bold=True))

            # Col 2: Win Rate %
            if not entry.played:
                table.setItem(row_idx, 2, _item("—", Palette.TEXT_MUTED))
            else:
                pct = entry.win_pct
                pct_str = f"{pct * 100:.0f}%" if pct is not None else "—"
                col = _pct_color(pct)
                table.setItem(row_idx, 2, _item(pct_str, col, bold=True))

            # Col 3: Singoli Pokémon avversari sconfitti
            if not entry.played or not entry.wins_vs_opp_pokemon:
                table.setItem(row_idx, 3, _item("—", Palette.TEXT_MUTED, center=False))
            else:
                # Elenco formattato con conteggi
                wins_list = [f"{p} (×{cnt})" for p, cnt in entry.wins_vs_opp_pokemon.most_common()]
                wins_text = ", ".join(wins_list)
                table.setItem(row_idx, 3, _item(wins_text, Palette.SUCCESS_BRIGHT, center=False))

            # Col 4: Singoli Pokémon avversari nelle sconfitte
            if not entry.played or not entry.losses_vs_opp_pokemon:
                table.setItem(row_idx, 4, _item("—", Palette.TEXT_MUTED, center=False))
            else:
                losses_list = [f"{p} (×{cnt})" for p, cnt in entry.losses_vs_opp_pokemon.most_common()]
                losses_text = ", ".join(losses_list)
                table.setItem(row_idx, 4, _item(losses_text, Palette.DANGER_BRIGHT, center=False))

        # Imposta altezza adatta
        row_h = 48
        table.setFixedHeight(min(520, max(180, table.rowCount() * row_h + 38)))
        self.lay_block1.addWidget(table)

    # ── Rendering Blocco 2: Analisi Singoli Pokémon ───────────────────
    def _render_pokemon_block(self):
        while self.lay_block2.count():
            item = self.lay_block2.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        header_box = QHBoxLayout()
        header_lbl = _label("2. Analisi dei Singoli Pokémon (Team del Player)", _TITLE_QSS)
        header_box.addWidget(header_lbl)
        header_box.addStretch()
        self.lay_block2.addLayout(header_box)

        desc = _label(
            "Per ciascun Pokémon del giocatore: Best Matchup (core da 4 avversari con più vittorie) "
            "e Worst Matchup (core da 4 avversari con più sconfitte).",
            _MUTED_QSS,
        )
        desc.setWordWrap(True)
        self.lay_block2.addWidget(desc)

        if not self._report or not self._report.pokemon_matchups:
            self.lay_block2.addWidget(_label("Nessun dato singolo Pokémon disponibile.", _MUTED_QSS))
            return

        # Selettore orizzontale a bottoni/icone dei 6 Pokémon
        bar_pokes = QHBoxLayout()
        bar_pokes.setSpacing(Spacing.SM)

        if not self._selected_pokemon or self._selected_pokemon not in self._report.pokemon_matchups:
            self._selected_pokemon = self._report.player_team[0]

        for p in self._report.player_team:
            data_p = self._report.pokemon_matchups.get(p)
            games_p = data_p.total_games if data_p else 0
            is_active = (p == self._selected_pokemon)

            btn = QPushButton(f"  {p} ({games_p})")
            icon_path = get_pokemon_icon_path(p)
            if icon_path:
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(24, 24))
            btn.setFixedHeight(38)
            btn.setMinimumWidth(130)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            if is_active:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.PRIMARY};"
                    f" border: 2px solid {Palette.PRIMARY}; border-radius: 6px; font-weight: {Fonts.WEIGHT_SEMI}; font-size: {Fonts.SIZE_BASE}; padding: 4px 12px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_MUTED};"
                    f" border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; font-size: {Fonts.SIZE_BASE}; padding: 4px 12px; }}"
                    f"QPushButton:hover {{ color: {Palette.TEXT_PRIMARY}; border-color: {Palette.PRIMARY_DIM}; background-color: {Palette.BG_CARD}; }}"
                )

            # Slot di click per cambiare Pokémon attivo
            def make_click(species=p):
                return lambda: self._on_pokemon_selected(species)
            btn.clicked.connect(make_click())
            bar_pokes.addWidget(btn)

        bar_pokes.addStretch()
        self.lay_block2.addLayout(bar_pokes)

        # Scheda del Pokémon Selezionato
        cur_p = self._selected_pokemon
        matchup_data = self._report.pokemon_matchups.get(cur_p)
        if not matchup_data:
            return

        card_p = QFrame()
        card_p.setStyleSheet(f"QFrame {{ background-color: {Palette.BG_SURFACE}; border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; padding: 12px; }}")
        card_lay = QVBoxLayout(card_p)
        card_lay.setSpacing(Spacing.MD)

        # Header con info Pokémon
        p_head = QHBoxLayout()
        p_head.addWidget(PokemonSprite(cur_p, 36))
        p_name = _label(cur_p, f"font-size: {Fonts.SIZE_TITLE}; font-weight: {Fonts.WEIGHT_SEMI}; color: {Palette.PRIMARY}; border: none; background: transparent;")
        p_head.addWidget(p_name)
        p_head.addSpacing(Spacing.LG)

        wr_val = matchup_data.win_pct
        wr_text = f"{wr_val * 100:.0f}%" if wr_val is not None else "—"
        p_stats = _label(
            f"Presenze: <b>{matchup_data.total_games}</b>  ·  Record: <b>{matchup_data.total_wins}W - {matchup_data.total_losses}L</b>  ·  Win Rate: <b style='color:{_pct_color(wr_val)}'>{wr_text}</b>",
            _TEXT_QSS,
        )
        p_head.addWidget(p_stats)
        p_head.addStretch()
        card_lay.addLayout(p_head)

        # Layout a 2 Colonne: Best Matchup vs Worst Matchup
        cols = QHBoxLayout()
        cols.setSpacing(Spacing.LG)

        # Colonna Sinistra: Best Matchup
        best_box = QFrame()
        best_box.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid rgba(80,220,120,0.3); border-radius: 6px; }}"
            f"QLabel {{ border: none; background: transparent; }}"
        )
        best_lay = QVBoxLayout(best_box)
        best_lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        best_lay.addWidget(_label("🏆 Best Matchup (Core da 4 Avversari)", f"font-size: {Fonts.SIZE_LARGE}; font-weight: 600; color: {Palette.SUCCESS_BRIGHT}; border: none; background: transparent;"))

        if not matchup_data.best_matchups:
            best_lay.addWidget(_label("Nessuna vittoria registrata contro core da 4 avversari.", _MUTED_QSS))
        else:
            for core, w_cnt in matchup_data.best_matchups:
                row_w = QWidget()
                row_w.setStyleSheet("background: transparent; border: none;")
                r_lay = QHBoxLayout(row_w)
                r_lay.setContentsMargins(0, 4, 0, 4)
                r_lay.addWidget(_core_icons_widget(core, 24), 1)
                r_lay.addWidget(_badge(f"{w_cnt} Vittorie", Palette.SUCCESS_BRIGHT, "rgba(60,180,90,0.15)"))
                best_lay.addWidget(row_w)
        best_lay.addStretch()
        cols.addWidget(best_box, 1)

        # Colonna Destra: Worst Matchup
        worst_box = QFrame()
        worst_box.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border: 1px solid rgba(240,80,80,0.3); border-radius: 6px; }}"
            f"QLabel {{ border: none; background: transparent; }}"
        )
        worst_lay = QVBoxLayout(worst_box)
        worst_lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        worst_lay.addWidget(_label("💀 Worst Matchup (Core da 4 Avversari)", f"font-size: {Fonts.SIZE_LARGE}; font-weight: 600; color: {Palette.DANGER_BRIGHT}; border: none; background: transparent;"))

        if not matchup_data.worst_matchups:
            worst_lay.addWidget(_label("Nessuna sconfitta registrata contro core da 4 avversari.", _MUTED_QSS))
        else:
            for core, l_cnt in matchup_data.worst_matchups:
                row_w = QWidget()
                row_w.setStyleSheet("background: transparent; border: none;")
                r_lay = QHBoxLayout(row_w)
                r_lay.setContentsMargins(0, 4, 0, 4)
                r_lay.addWidget(_core_icons_widget(core, 24), 1)
                r_lay.addWidget(_badge(f"{l_cnt} Sconfitte", Palette.DANGER_BRIGHT, "rgba(220,60,60,0.15)"))
                worst_lay.addWidget(row_w)
        worst_lay.addStretch()
        cols.addWidget(worst_box, 1)

        card_lay.addLayout(cols)
        self.lay_block2.addWidget(card_p)

    def _on_pokemon_selected(self, species: str):
        self._selected_pokemon = species
        self._render_pokemon_block()
