"""
team_builder_view.py
====================
Vista principale della sezione Team Builder di Janalytics.
Redesign v2 — Layout pulito ispirato al mockup con:
  - Import Roster unificato (3 tab: Paste / Meta Replay / Meta Usage)
  - MoveChip + popup per selezione mosse
  - AbilityChip + popup per selezione abilità
  - Role detection automatico + auto-build
  - Pannello editor singolo
  - Field State nella colonna destra
  - Strip icone compatte per Team e Roster
"""

import os
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QStackedWidget, QScrollArea, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialog, QSlider, QSpinBox, QGridLayout, QComboBox, QApplication,
    QFileDialog, QToolButton, QSizePolicy, QLineEdit, QTabWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QPixmap, QColor, QFont, QTextDocument, QIcon
from PySide6.QtPrintSupport import QPrinter

from config.theme import Palette
from src.domain.team_builder_service import (
    parse_pokepaste, TeamMember, get_legal_abilities_details,
    get_legal_moves_details, get_all_items, calculate_vgc_stat
)
from src.domain.role_detector import detect_role, get_role_icon, get_role_color, cycle_role
from src.domain.auto_build import generate_auto_build, has_custom_spread
from src.utils.icon_utils import get_pokemon_icon_path
from domain.smogon_calc import SmogonDamageCalc, PokemonOptions, FieldOptions
from domain.team_builder_engine import TeamBuilderEngine
from widgets.move_selector_popup import MoveChip, MoveSelectorPopup
from widgets.ability_selector_popup import AbilityChip, AbilitySelectorPopup

TYPE_COLORS = {
    "Normal": "#A8A77A", "Fire": "#EE8130", "Water": "#6390F0",
    "Electric": "#F7D02C", "Grass": "#7AC74C", "Ice": "#96D9D6",
    "Fighting": "#C22E28", "Poison": "#A33EA1", "Ground": "#E2BF65",
    "Flying": "#A98FF3", "Psychic": "#F95587", "Bug": "#A6B91A",
    "Rock": "#B6A136", "Ghost": "#735797", "Dragon": "#6F35FC",
    "Dark": "#705848", "Steel": "#B7B7CE", "Fairy": "#D685AD"
}


class EVRow(QWidget):
    valueChanged = Signal(str, int)

    def __init__(self, stat_name: str, color: str, parent=None):
        super().__init__(parent)
        self.stat_name = stat_name
        self._val = 0
        self._base = 100
        self._mult = 1.0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.lbl_stat = QLabel(stat_name)
        self.lbl_stat.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
        self.lbl_stat.setFixedWidth(28)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 32)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border-radius: 2px;
                height: 4px;
                background: {Palette.BG_CARD};
            }}
            QSlider::handle:horizontal {{
                background: {Palette.TEXT_PRIMARY};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: {color};
                border-radius: 2px;
            }}
        """)

        self.lbl_val = QLabel("—")
        self.lbl_val.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
        self.lbl_val.setFixedWidth(32)

        layout.addWidget(self.lbl_stat)
        layout.addWidget(self.slider)
        layout.addWidget(self.lbl_val)

        self.slider.valueChanged.connect(self._on_change)

    def _on_change(self, val):
        self._val = val
        self._update_label()
        self.valueChanged.emit(self.stat_name, val)

    def value(self) -> int:
        return self._val

    def setValue(self, val: int):
        self.slider.blockSignals(True)
        self._val = val
        self.slider.setValue(val)
        self._update_label()
        self.slider.blockSignals(False)

    def set_base_and_mult(self, base: int, mult: float):
        self._base = base
        self._mult = mult
        self._update_label()

    def _update_label(self):
        is_hp = (self.stat_name == "HP")
        ev = (self._val * 8) - 4 if self._val > 0 else 0
        val = calculate_vgc_stat(self._base, 31, ev, self._mult, is_hp)
        self.lbl_val.setText(str(val))


# ── Helpers di icone ─────────────────────────────────────────────────────────

def get_pokemon_pixmap(species: str, size: int = 48) -> QPixmap:
    if not species:
        return None
    path = get_pokemon_icon_path(species)
    if path and os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None


# ── Stili condivisi ───────────────────────────────────────────────────────────

BTN_PILL_STYLE = (
    f"QPushButton {{ background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY}; "
    f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 20px; padding: 6px 14px; "
    f"font-size: 13px; text-align: left; }}"
    f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; color: {Palette.PRIMARY}; }}"
    f"QPushButton:checked {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
    f"border-color: {Palette.PRIMARY}; font-weight: bold; }}"
)

TABLE_STYLE = (
    f"QTableWidget {{ background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY}; "
    f"border: 1px solid {Palette.BORDER_LIGHT}; gridline-color: {Palette.BORDER_COLOR}; "
    f"border-radius: 6px; }}"
    f"QHeaderView::section {{ background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.PRIMARY}; "
    f"padding: 6px; border: none; font-weight: bold; font-size: 12px; }}"
    f"QTableWidget::item {{ padding: 6px; }}"
    f"QTableWidget::item:selected {{ background-color: {Palette.TERTIARY}; }}"
)


# ── Worker: Live Preview ──────────────────────────────────────────────────────

class LivePreviewWorker(QThread):
    """Calcola in background le tabelle KOs e Threats per il Pokémon selezionato."""
    finished = Signal(list, list)  # (kos, threats)
    error = Signal(str)

    def __init__(self, engine: TeamBuilderEngine, selected_member: Dict, roster: List[Dict], field_opts: FieldOptions):
        super().__init__()
        self._engine = engine
        self._selected = selected_member
        self._roster = roster
        self._field_opts = field_opts

    def run(self):
        try:
            kos, threats = self._engine.compute_live_preview(self._selected, self._roster, self._field_opts)
            self.finished.emit(kos, threats)
        except Exception as e:
            self.error.emit(str(e))


# ── Worker: Analisi Completa ──────────────────────────────────────────────────

class AnalysisWorker(QThread):
    """Calcola i tre report (Bulk, Offence, Best Switch) in background."""
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, engine: TeamBuilderEngine, team: List[Dict], roster: List[Dict], field_opts: FieldOptions):
        super().__init__()
        self._engine = engine
        self._team = team
        self._roster = roster
        self._field_opts = field_opts

    def run(self):
        try:
            self.progress.emit(10, "Analisi Bulk (danni subiti)...")
            bulk = self._engine.compute_bulk_report(self._team, self._roster, self._field_opts)

            self.progress.emit(45, "Analisi Offence (danni inflitti)...")
            offence = self._engine.compute_offence_report(self._team, self._roster, self._field_opts)

            self.progress.emit(70, "Analisi Best Switch...")
            best_switch = self._engine.compute_best_switch_report(self._team, self._roster, self._field_opts)

            self.progress.emit(100, "Completato!")
            self.finished.emit({
                "bulk": bulk,
                "offence": offence,
                "best_switch": best_switch,
            })
        except Exception as e:
            self.error.emit(str(e))


# ── Mini-pannello Pokémon (Editor) ────────────────────────────────────────────

class MiniPokemonPanel(QFrame):
    """
    Pannello compatto di editing per un singolo Pokémon.
    Redesign v2: MoveChip + popup, AbilityChip + popup, Role Badge.
    Emette build_changed quando l'utente modifica qualcosa.
    """
    build_changed = Signal()

    NATURES = sorted(set([
        "Adamant", "Bashful", "Bold", "Brave", "Calm", "Careful", "Docile",
        "Gentle", "Hardy", "Hasty", "Impish", "Jolly", "Lax",
        "Lonely", "Mild", "Modest", "Naive", "Naughty", "Quiet", "Quirky",
        "Rash", "Relaxed", "Sassy", "Serious", "Timid"
    ]))

    def __init__(self, title: str = "Build", parent=None):
        super().__init__(parent)
        self._member: Optional[Dict[str, Any]] = None
        self._is_updating = False
        self._move_types = {}
        self._legal_moves_data: List[Dict] = []
        self._legal_abilities_data: List[Dict] = []
        self._all_items = []
        self._base_stats = {}
        self._current_role = "Offensive"

        self.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 10px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # ── Header: Title + Role Badge ──
        header_row = QHBoxLayout()
        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet(
            f"color: {Palette.TEXT_MUTED}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; border: none;"
        )
        header_row.addWidget(lbl_title)
        header_row.addStretch()

        # Role badge (cliccabile per override)
        self.btn_role = QPushButton("⚔ Offensive")
        self.btn_role.setCursor(Qt.PointingHandCursor)
        self.btn_role.setFixedHeight(22)
        self.btn_role.setToolTip("Click per cambiare ruolo manualmente")
        self._update_role_badge("Offensive")
        self.btn_role.clicked.connect(self._on_role_clicked)
        header_row.addWidget(self.btn_role)

        layout.addLayout(header_row)

        # ── Top row: icon + name + nature + item ──
        top_row = QHBoxLayout()

        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(56, 56)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_icon.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; border-radius: 8px; "
            f"border: 1px solid {Palette.BORDER_LIGHT};"
        )
        top_row.addWidget(self.lbl_icon)

        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        self.lbl_name = QLabel("—")
        self.lbl_name.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-weight: bold; font-size: 15px; border: none;"
        )
        info_col.addWidget(self.lbl_name)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        self.combo_nature = QComboBox()
        self.combo_nature.addItems(self.NATURES)
        self.combo_nature.setStyleSheet(
            f"QComboBox {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border-radius: 10px; padding: 2px 8px; font-size: 11px; "
            f"border: 1px solid {Palette.BORDER_COLOR}; }}"
            f"QComboBox QAbstractItemView {{ background-color: {Palette.BG_CARD}; "
            f"color: {Palette.TEXT_PRIMARY}; }}"
        )
        self.combo_nature.setFixedHeight(24)
        self.combo_nature.currentTextChanged.connect(self._on_nature_changed)
        badge_row.addWidget(self.combo_nature)

        self.combo_item = QComboBox()
        self.combo_item.setEditable(True)
        self.combo_item.setStyleSheet(
            f"QComboBox {{ background-color: {Palette.BG_CARD}; color: {Palette.SECONDARY}; "
            f"border-radius: 10px; padding: 2px 8px; font-size: 11px; "
            f"border: 1px solid {Palette.BORDER_COLOR}; }}"
            f"QComboBox QAbstractItemView {{ background-color: {Palette.BG_CARD}; "
            f"color: {Palette.SECONDARY}; }}"
        )
        self.combo_item.currentTextChanged.connect(self._on_build_changed)
        badge_row.addWidget(self.combo_item)
        badge_row.addStretch()
        info_col.addLayout(badge_row)

        # Ability chip
        self.chip_ability = AbilityChip()
        self.chip_ability.clicked.connect(self._on_ability_chip_clicked)
        info_col.addWidget(self.chip_ability)

        top_row.addLayout(info_col)
        layout.addLayout(top_row)

        # ── Moves row: 4 MoveChips ──
        moves_layout = QHBoxLayout()
        moves_layout.setSpacing(4)
        self.move_chips: List[MoveChip] = []
        for i in range(4):
            chip = MoveChip()
            chip.clicked.connect(lambda checked=False, idx=i: self._on_move_chip_clicked(idx))
            self.move_chips.append(chip)
            moves_layout.addWidget(chip)
        layout.addLayout(moves_layout)

        # ── Stats / EVs section ──
        lbl_stats = QLabel("EVs — Statistiche")
        lbl_stats.setStyleSheet(
            f"color: {Palette.TEXT_MUTED}; font-size: 10px; font-weight: bold; "
            f"border: none; margin-top: 4px;"
        )
        layout.addWidget(lbl_stats)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(4)

        self.ev_rows: Dict[str, EVRow] = {}
        STATS = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
        STAT_COLORS = {
            "HP": Palette.CHART_HP, "Atk": Palette.CHART_ATK, "Def": Palette.CHART_DEF,
            "SpA": Palette.CHART_SPA, "SpD": Palette.CHART_SPD, "Spe": Palette.CHART_SPE
        }
        for i, stat in enumerate(STATS):
            color = STAT_COLORS.get(stat, Palette.TEXT_PRIMARY)
            row = EVRow(stat, color)
            row.valueChanged.connect(self._on_ev_changed)
            self.ev_rows[stat] = row
            stats_grid.addWidget(row, i, 0, 1, 3)

        layout.addLayout(stats_grid)
        layout.addStretch()

    # ── Role Badge ──

    def _update_role_badge(self, role: str):
        self._current_role = role
        icon = get_role_icon(role)
        color = get_role_color(role)
        self.btn_role.setText(f"{icon} {role}")
        self.btn_role.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: #FFFFFF; "
            f"border-radius: 11px; padding: 2px 10px; font-size: 10px; "
            f"font-weight: bold; border: none; }}"
            f"QPushButton:hover {{ opacity: 0.8; }}"
        )

    def _on_role_clicked(self):
        if self._is_updating:
            return
        new_role = cycle_role(self._current_role)
        self._update_role_badge(new_role)
        # Se le EVs sono tutte a 0, applica auto-build
        if self._member and not has_custom_spread(self._member):
            self._apply_auto_build(new_role)
        self._on_build_changed()

    def _apply_auto_build(self, role: str):
        """Applica auto-build solo se le EVs sono vuote."""
        if not self._member:
            return
        build = generate_auto_build(role, self._base_stats)
        self._is_updating = True
        # Imposta EVs
        evs = build.get("evs", {})
        self._member["options"]["evs"] = evs
        for stat, row in self.ev_rows.items():
            row.setValue(evs.get(stat, 0))
        # Imposta natura
        nature = build.get("nature", "Serious")
        self._member["options"]["nature"] = nature
        idx = self.combo_nature.findText(nature)
        if idx >= 0:
            self.combo_nature.setCurrentIndex(idx)
        self._update_multipliers(nature)
        self._is_updating = False

    # ── Move popup ──

    def _on_move_chip_clicked(self, slot_index: int):
        if not self._member:
            return
        species = self._member.get("name", "")
        if not self._legal_moves_data:
            self._legal_moves_data = get_legal_moves_details(species)

        current = self.move_chips[slot_index].move_name

        popup = MoveSelectorPopup(
            pokemon_name=species,
            slot_index=slot_index,
            legal_moves=self._legal_moves_data,
            current_move=current,
            parent=self
        )
        popup.move_selected.connect(lambda data, idx=slot_index: self._on_move_selected(idx, data))
        popup.exec()

    def _on_move_selected(self, slot_index: int, move_data: Dict):
        move_name = move_data.get("name", "")
        move_type = move_data.get("type", "")
        self.move_chips[slot_index].update_display(move_name, move_type)
        self._move_types[move_name] = move_type
        self._on_build_changed()

    # ── Ability popup ──

    def _on_ability_chip_clicked(self):
        if not self._member:
            return
        species = self._member.get("name", "")
        if not self._legal_abilities_data:
            self._legal_abilities_data = get_legal_abilities_details(species)

        current = self.chip_ability.ability_name

        popup = AbilitySelectorPopup(
            pokemon_name=species,
            legal_abilities=self._legal_abilities_data,
            current_ability=current,
            parent=self
        )
        popup.ability_selected.connect(self._on_ability_selected)
        popup.exec()

    def _on_ability_selected(self, ab_data: Dict):
        name = ab_data.get("name", "")
        self.chip_ability.update_display(name)
        self._on_build_changed()

    # ── Nature / EV handlers ──

    def _on_nature_changed(self, nature: str):
        if self._is_updating:
            return
        self._update_multipliers(nature)
        self._on_build_changed()

    def _update_multipliers(self, nature: str):
        NATURE_MAP = {
            "Adamant": ("Atk", "SpA"), "Bold": ("Def", "Atk"), "Brave": ("Atk", "Spe"),
            "Calm": ("SpD", "Atk"), "Careful": ("SpD", "SpA"), "Gentle": ("SpD", "Def"),
            "Hasty": ("Spe", "Def"), "Impish": ("Def", "SpA"), "Jolly": ("Spe", "SpA"),
            "Lax": ("Def", "SpD"), "Lonely": ("Atk", "Def"), "Mild": ("SpA", "Def"),
            "Modest": ("SpA", "Atk"), "Naive": ("Spe", "SpD"), "Naughty": ("Atk", "SpD"),
            "Quiet": ("SpA", "Spe"), "Rash": ("SpA", "SpD"), "Relaxed": ("Def", "Spe"),
            "Sassy": ("SpD", "Spe"), "Timid": ("Spe", "Atk"),
        }
        plus, minus = NATURE_MAP.get(nature, (None, None))
        for stat, row in self.ev_rows.items():
            mult = 1.0
            if stat == plus: mult = 1.1
            elif stat == minus: mult = 0.9
            row.set_base_and_mult(self._base_stats.get(stat.lower(), 100), mult)

    def _on_ev_changed(self, stat_name: str, val: int):
        if self._is_updating:
            return
        total = sum(r.value() for r in self.ev_rows.values())
        if total > 66:
            diff = total - 66
            new_val = max(0, val - diff)
            self.ev_rows[stat_name].setValue(new_val)
        self._on_build_changed()

    def _on_build_changed(self, *args):
        if self._is_updating:
            return
        if self._member:
            self._member["options"]["nature"] = self.combo_nature.currentText()
            self._member["options"]["item"] = self.combo_item.currentText().strip() or None
            self._member["options"]["ability"] = self.chip_ability.ability_name or None

            moves = []
            for chip in self.move_chips:
                move = chip.move_name
                moves.append(move if move else "")
            self._member["moves"] = moves

            evs = {}
            for stat, row in self.ev_rows.items():
                if row.value() > 0:
                    evs[stat] = row.value()
            self._member["options"]["evs"] = evs
        self.build_changed.emit()

    def load_member(self, member: Dict[str, Any]):
        """Popola il pannello con i dati di un membro."""
        self._is_updating = True
        self._member = member
        opts = member.get("options", {})

        self.lbl_name.setText(member.get("name", "—"))

        # Carica Items (solo 1 volta)
        if not self._all_items:
            self._all_items = get_all_items()
            self.combo_item.addItems([""] + self._all_items)

        item = opts.get("item") or ""
        self.combo_item.setCurrentText(item)

        # Carica Abilità Legali
        species_name = member.get("name", "")
        self._legal_abilities_data = get_legal_abilities_details(species_name)
        ability = opts.get("ability") or ""
        self.chip_ability.update_display(ability)

        # Icona
        px = get_pokemon_pixmap(species_name, 48)
        if px:
            self.lbl_icon.setPixmap(px)
        else:
            self.lbl_icon.setText("?")

        # Base Stats per il calcolo UI
        from database.connection import SessionLocal
        from database.models_v2 import PokemonSpeciesV2
        with SessionLocal() as session:
            pkmn = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species_name).first()
            if pkmn:
                self._base_stats = {
                    "hp": pkmn.bst_hp, "atk": pkmn.bst_atk, "def": pkmn.bst_def,
                    "spa": pkmn.bst_spa, "spd": pkmn.bst_spd, "spe": pkmn.bst_spe
                }
            else:
                self._base_stats = {}

        # Natura
        nat = opts.get("nature", "Serious") or "Serious"
        idx = self.combo_nature.findText(nat)
        if idx >= 0:
            self.combo_nature.setCurrentIndex(idx)
        self._update_multipliers(nat)

        # Mosse (Legal Moves → MoveChips)
        self._legal_moves_data = get_legal_moves_details(species_name)
        self._move_types = {m["name"]: m["type"] for m in self._legal_moves_data}
        moves = member.get("moves", [])
        for i, chip in enumerate(self.move_chips):
            m_name = moves[i] if i < len(moves) else ""
            m_type = self._move_types.get(m_name, "")
            chip.update_display(m_name, m_type)

        # Role Detection
        role = detect_role(species_name, moves, self._base_stats)
        self._update_role_badge(role)

        # EVs
        evs = opts.get("evs") or {}
        for stat, row in self.ev_rows.items():
            ev = evs.get(stat, 0)
            row.setValue(ev)

        self._is_updating = False

    def get_member(self) -> Optional[Dict[str, Any]]:
        return self._member

    def clear(self):
        """Reset visuale del pannello."""
        self._is_updating = True
        self._member = None
        self.lbl_name.setText("—")
        self.combo_item.clear()
        self.chip_ability.update_display("")
        self.lbl_icon.setText("?")
        self._legal_moves_data = []
        self._legal_abilities_data = []
        for chip in self.move_chips:
            chip.update_display("", "")
        for row in self.ev_rows.values():
            row.setValue(0)
        self._update_role_badge("Offensive")
        self._is_updating = False


# ── Dialog Roster Completo ────────────────────────────────────────────────────

class FullRosterDialog(QDialog):
    """Dialog che mostra tutto il roster corrente."""
    def __init__(self, roster: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Roster Completo")
        self.setMinimumSize(500, 600)
        self.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        lbl = QLabel(f"Roster — {len(roster)} Pokémon")
        lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {Palette.PRIMARY};")
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        content = QWidget()
        grid = QGridLayout(content)
        grid.setSpacing(8)

        for i, mon in enumerate(roster):
            row, col = divmod(i, 3)
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 8px; "
                f"border: 1px solid {Palette.BORDER_LIGHT}; padding: 6px; }}"
            )
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)

            icon_lbl = QLabel()
            px = get_pokemon_pixmap(mon.get("name", ""), 36)
            if px:
                icon_lbl.setPixmap(px)
            else:
                icon_lbl.setText("?")
            card_layout.addWidget(icon_lbl)

            name_lbl = QLabel(mon.get("name", "?"))
            name_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {Palette.TEXT_PRIMARY};")
            card_layout.addWidget(name_lbl)
            card_layout.addStretch()

            grid.addWidget(card, row, col)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        btn_close = QPushButton("Chiudi")
        btn_close.setStyleSheet(
            f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"padding: 8px 24px; border-radius: 6px; font-weight: bold;"
        )
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


# ── Report Widgets ────────────────────────────────────────────────────────────

class AccordionItem(QWidget):
    """Categoria espandibile/collassabile (es. 1HKO, 2HKO, 3HKO+)."""
    def __init__(self, title: str, count: int = 0, parent=None):
        super().__init__(parent)
        self._expanded = (title == "1HKOs")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.btn_header = QPushButton()
        self._title = title
        self._count = count
        self._update_header_text()
        self.btn_header.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY}; "
            f"border: none; border-radius: 6px; padding: 10px 16px; font-weight: bold; font-size: 13px; "
            f"text-align: left; }}"
            f"QPushButton:hover {{ background-color: {Palette.TERTIARY}; }}"
        )
        self.btn_header.clicked.connect(self.toggle)
        layout.addWidget(self.btn_header)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 4, 8, 8)
        self.content_layout.setSpacing(2)
        layout.addWidget(self.content_widget)

        self.content_widget.setVisible(self._expanded)

    def _update_header_text(self):
        arrow = "▼" if self._expanded else "▶"
        self.btn_header.setText(f"{self._title}  ({self._count})  {arrow}")

    def toggle(self):
        self._expanded = not self._expanded
        self.content_widget.setVisible(self._expanded)
        self._update_header_text()

    def set_count(self, count: int):
        self._count = count
        self._update_header_text()

    def add_entry(self, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; padding: 4px 8px; "
            f"background-color: {Palette.BG_CARD}; border-radius: 4px;"
        )
        lbl.setWordWrap(True)
        self.content_layout.addWidget(lbl)

    def clear_entries(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class ReportPokemonSelector(QWidget):
    """Griglia 2x3 con le icone cliccabili dei 6 Pokémon per filtrare il report."""
    pokemon_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_idx = 0
        self.btns: List[QPushButton] = []

        layout = QGridLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        for i in range(6):
            btn = QPushButton()
            btn.setFixedSize(72, 72)
            btn.setStyleSheet(self._btn_style(False))
            btn.clicked.connect(lambda checked, idx=i: self._on_clicked(idx))
            self.btns.append(btn)
            layout.addWidget(btn, i // 2, i % 2)

    def _btn_style(self, selected: bool) -> str:
        border = Palette.PRIMARY if selected else Palette.BORDER_LIGHT
        bg = Palette.BG_SURFACE_ELEVATED if selected else Palette.BG_CARD
        return (
            f"QPushButton {{ background-color: {bg}; border-radius: 10px; "
            f"border: 2px solid {border}; }}"
            f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; }}"
        )

    def _on_clicked(self, idx: int):
        self._selected_idx = idx
        for i, btn in enumerate(self.btns):
            btn.setStyleSheet(self._btn_style(i == idx))
        self.pokemon_selected.emit(idx)

    def load_team(self, team: List[Dict[str, Any]]):
        for i, btn in enumerate(self.btns):
            if i < len(team):
                mon = team[i]
                px = get_pokemon_pixmap(mon.get("name", ""), 56)
                if px:
                    btn.setIcon(px)
                    btn.setIconSize(QSize(56, 56))
                btn.setToolTip(mon.get("name", ""))
            else:
                btn.setIcon(QIcon())
                btn.setToolTip("")

        if team:
            self._on_clicked(0)


# ── Vista Principale ──────────────────────────────────────────────────────────

class TeamBuilderView(QWidget):
    """
    Sezione Team Builder principale — Redesign v2.
    Layout unificato con Import Panel a tab, strip icone, pannello editor singolo,
    Field State a destra, e tabelle KOs/Threats ai lati.
    """

    def __init__(self, parent_main=None):
        super().__init__()
        self.parent_main = parent_main

        # Stato interno
        self._team: List[Dict[str, Any]] = []
        self._roster: List[Dict[str, Any]] = []
        self._selected_team_idx: Optional[int] = None
        self._selected_roster_idx: Optional[int] = None
        self._engine: Optional[TeamBuilderEngine] = None
        self._live_worker: Optional[LivePreviewWorker] = None
        self._analysis_worker: Optional[AnalysisWorker] = None
        self._live_timer = QTimer()
        self._live_timer.setSingleShot(True)
        self._live_timer.timeout.connect(self._run_live_preview)
        self._report_data: Optional[Dict] = None

        # Layout root con QStackedWidget (Editor vs Report)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.root_stack = QStackedWidget()
        root_layout.addWidget(self.root_stack)

        # Pagina 0: Editor
        self.page_editor = QWidget()
        self._build_editor_page()
        self.root_stack.addWidget(self.page_editor)

        # Pagina 1: Report
        self.page_report = QWidget()
        self._build_report_page()
        self.root_stack.addWidget(self.page_report)

    # ══════════════════════════════════════════════════════════════════════════
    # BUILD EDITOR PAGE (Redesign v2)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_editor_page(self):
        main_layout = QVBoxLayout(self.page_editor)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # ── SEZIONE 1: Team & Roster Management ──
        mgmt_frame = QFrame()
        mgmt_frame.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 10px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
        )
        mgmt_layout = QVBoxLayout(mgmt_frame)
        mgmt_layout.setContentsMargins(14, 10, 14, 10)
        mgmt_layout.setSpacing(8)

        # Header: "Team & Roster Management" + Manage Team toggle
        mgmt_header = QHBoxLayout()
        lbl_mgmt_title = QLabel("Team & Roster Management")
        lbl_mgmt_title.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;"
        )
        mgmt_header.addWidget(lbl_mgmt_title)
        mgmt_header.addStretch()

        self.btn_manage_team = QPushButton("⚙  Manage Team")
        self.btn_manage_team.setCheckable(True)
        self.btn_manage_team.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"border-radius: 8px; padding: 6px 16px; font-weight: bold; font-size: 12px; "
            f"border: none; }}"
            f"QPushButton:checked {{ background-color: {Palette.PRIMARY_DIM}; }}"
            f"QPushButton:hover {{ background-color: {Palette.PRIMARY_BRIGHT}; }}"
        )
        self.btn_manage_team.clicked.connect(self._toggle_import_panel)
        mgmt_header.addWidget(self.btn_manage_team)
        mgmt_layout.addLayout(mgmt_header)

        # ── Team Strip (icone orizzontali) ──
        strips_row = QHBoxLayout()
        strips_row.setSpacing(16)

        # Your Team (max 6)
        team_strip_col = QVBoxLayout()
        team_strip_col.setSpacing(4)
        lbl_your_team = QLabel("Your Team (max 6)")
        lbl_your_team.setStyleSheet(
            f"color: {Palette.TEXT_MUTED}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; border: none;"
        )
        team_strip_col.addWidget(lbl_your_team)

        team_icons_row = QHBoxLayout()
        team_icons_row.setSpacing(4)
        self.team_icon_btns: List[QPushButton] = []
        for i in range(6):
            btn = QPushButton()
            btn.setFixedSize(42, 42)
            btn.setCheckable(True)
            btn.setStyleSheet(self._icon_btn_style(False))
            btn.clicked.connect(lambda checked, idx=i: self._on_team_slot_clicked(idx))
            self.team_icon_btns.append(btn)
            team_icons_row.addWidget(btn)
        team_icons_row.addStretch()
        team_strip_col.addLayout(team_icons_row)
        strips_row.addLayout(team_strip_col)

        # Opponent Roster (scrollable strip)
        roster_strip_col = QVBoxLayout()
        roster_strip_col.setSpacing(4)

        roster_header = QHBoxLayout()
        lbl_roster = QLabel("Opponent Roster")
        lbl_roster.setStyleSheet(
            f"color: {Palette.TEXT_MUTED}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; border: none;"
        )
        roster_header.addWidget(lbl_roster)
        roster_header.addStretch()

        btn_show_full = QPushButton("Mostra Tutti")
        btn_show_full.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_MUTED}; "
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 12px; "
            f"padding: 2px 10px; font-size: 11px;"
        )
        btn_show_full.clicked.connect(self._show_full_roster)
        roster_header.addWidget(btn_show_full)
        roster_strip_col.addLayout(roster_header)

        self.roster_scroll = QScrollArea()
        self.roster_scroll.setWidgetResizable(True)
        self.roster_scroll.setFixedHeight(48)
        self.roster_scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; "
            f"background: transparent; }}"
            f"QScrollBar:horizontal {{ height: 4px; background: transparent; }}"
            f"QScrollBar::handle:horizontal {{ background: {Palette.TERTIARY}; border-radius: 2px; }}"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}"
        )
        self.roster_icons_widget = QWidget()
        self.roster_icons_layout = QHBoxLayout(self.roster_icons_widget)
        self.roster_icons_layout.setContentsMargins(4, 4, 4, 4)
        self.roster_icons_layout.setSpacing(4)
        self.roster_icons_layout.addStretch()
        self.roster_scroll.setWidget(self.roster_icons_widget)
        roster_strip_col.addWidget(self.roster_scroll)

        strips_row.addLayout(roster_strip_col, 1)
        mgmt_layout.addLayout(strips_row)

        # ── Import Panel (collassabile, nascosto di default) ──
        self.import_panel = QFrame()
        self.import_panel.setVisible(False)
        self.import_panel.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE}; border-radius: 8px; "
            f"border: 1px solid {Palette.BORDER_COLOR}; }}"
        )

        import_layout = QVBoxLayout(self.import_panel)
        import_layout.setContentsMargins(10, 10, 10, 10)
        import_layout.setSpacing(0)

        self.import_tabs = QTabWidget()
        self.import_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: transparent; }}"
            f"QTabBar::tab {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_MUTED}; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-bottom: none; "
            f"border-top-left-radius: 8px; border-top-right-radius: 8px; "
            f"padding: 6px 16px; font-size: 11px; margin-right: 2px; }}"
            f"QTabBar::tab:selected {{ background-color: {Palette.BG_SURFACE_ELEVATED}; "
            f"color: {Palette.PRIMARY}; font-weight: bold; }}"
            f"QTabBar::tab:hover {{ color: {Palette.TEXT_PRIMARY}; }}"
        )

        # Tab 1: Showdown Paste
        tab_paste = QWidget()
        self._build_tab_paste(tab_paste)
        self.import_tabs.addTab(tab_paste, "📋  Import via Showdown Paste")

        # Tab 2: Meta Replay
        tab_meta_replay = QWidget()
        self._build_tab_meta_replay(tab_meta_replay)
        self.import_tabs.addTab(tab_meta_replay, "▶  Import via Meta Replay")

        # Tab 3: Meta Usage
        tab_meta_usage = QWidget()
        self._build_tab_meta_usage(tab_meta_usage)
        self.import_tabs.addTab(tab_meta_usage, "📊  Import via Meta Usage")

        import_layout.addWidget(self.import_tabs)
        mgmt_layout.addWidget(self.import_panel)

        main_layout.addWidget(mgmt_frame)

        # ── SEZIONE 2: Editor + Tables + Field State (3 colonne) ──
        editor_section = QHBoxLayout()
        editor_section.setSpacing(12)

        # Colonna sinistra: KOs Table
        self.kos_panel = self._make_preview_table("Pokémon KOs", Palette.SUCCESS)

        # Colonna centro: Build Panel + Start Analysis
        center_col = QVBoxLayout()
        center_col.setSpacing(8)

        # Header "Build Suggerita"
        build_header = QHBoxLayout()
        self.lbl_build_title = QLabel("Build Suggerita (Basata sul ruolo)")
        self.lbl_build_title.setStyleSheet(
            f"color: {Palette.PRIMARY}; font-size: 13px; font-weight: bold;"
        )
        build_header.addWidget(self.lbl_build_title)
        build_header.addStretch()

        btn_auto_evs = QPushButton("Auto-Allocate EVs")
        btn_auto_evs.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_MUTED}; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px; "
            f"padding: 4px 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {Palette.PRIMARY}; border-color: {Palette.PRIMARY}; }}"
        )
        btn_auto_evs.clicked.connect(self._on_auto_allocate_evs)
        build_header.addWidget(btn_auto_evs)
        center_col.addLayout(build_header)

        # Pannello editor singolo
        self.panel_editor = MiniPokemonPanel("Build")
        self.panel_editor.build_changed.connect(self._on_edit_build_changed)
        center_col.addWidget(self.panel_editor)

        # Start Analysis
        self.btn_start_analysis = QPushButton("▶  Start Analysis")
        self.btn_start_analysis.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"border-radius: 20px; padding: 12px 40px; font-size: 15px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.PRIMARY_BRIGHT}; }}"
            f"QPushButton:disabled {{ background-color: {Palette.TERTIARY}; color: {Palette.TEXT_MUTED}; }}"
        )
        self.btn_start_analysis.setEnabled(False)
        self.btn_start_analysis.clicked.connect(self._on_start_analysis)
        center_col.addWidget(self.btn_start_analysis, alignment=Qt.AlignCenter)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setAlignment(Qt.AlignCenter)
        self.lbl_progress.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        center_col.addWidget(self.lbl_progress)

        # Colonna destra: Threats + Field State
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        self.threats_panel = self._make_preview_table("Pokémon Threats", Palette.DANGER_BRIGHT)
        right_col.addWidget(self.threats_panel)

        # ── Field State (colonna destra) ──
        field_frame = QFrame()
        field_frame.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 10px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
        )
        field_layout = QVBoxLayout(field_frame)
        field_layout.setContentsMargins(10, 8, 10, 8)
        field_layout.setSpacing(6)

        lbl_field = QLabel("Field State")
        lbl_field.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; border: none;"
        )
        field_layout.addWidget(lbl_field)

        FIELD_BTN_STYLE = (
            f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_MUTED}; "
            f"border-radius: 6px; padding: 4px 8px; font-size: 11px; "
            f"border: 1px solid {Palette.BORDER_COLOR}; }}"
            f"QPushButton:checked {{ background-color: {Palette.PRIMARY_DIM}; color: {Palette.PRIMARY_BRIGHT}; "
            f"border-color: {Palette.PRIMARY}; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; }}"
        )
        FIELD_COMBO_STYLE = (
            f"QComboBox {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border-radius: 6px; padding: 4px 8px; font-size: 11px; "
            f"border: 1px solid {Palette.BORDER_COLOR}; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background-color: {Palette.BG_CARD}; "
            f"color: {Palette.TEXT_PRIMARY}; }}"
        )

        field_grid = QGridLayout()
        field_grid.setSpacing(4)

        self.btn_reflect = QPushButton("Reflect")
        self.btn_lightscreen = QPushButton("Light Screen")
        self.btn_auroraveil = QPushButton("Aurora Veil")
        self.btn_friendguard = QPushButton("FriendGuard")

        for btn in [self.btn_reflect, self.btn_lightscreen, self.btn_auroraveil, self.btn_friendguard]:
            btn.setCheckable(True)
            btn.setStyleSheet(FIELD_BTN_STYLE)
            btn.clicked.connect(self._schedule_live_preview)

        field_grid.addWidget(self.btn_reflect, 0, 0)
        field_grid.addWidget(self.btn_lightscreen, 0, 1)
        field_grid.addWidget(self.btn_auroraveil, 1, 0)
        field_grid.addWidget(self.btn_friendguard, 1, 1)

        field_layout.addLayout(field_grid)

        weather_row = QHBoxLayout()
        self.combo_weather = QComboBox()
        self.combo_weather.addItems(["Meteo", "Sun", "Rain", "Sand", "Snow"])
        self.combo_weather.setStyleSheet(FIELD_COMBO_STYLE)
        self.combo_weather.currentTextChanged.connect(self._schedule_live_preview)

        self.combo_terrain = QComboBox()
        self.combo_terrain.addItems(["Campo", "Electric", "Grassy", "Misty", "Psychic"])
        self.combo_terrain.setStyleSheet(FIELD_COMBO_STYLE)
        self.combo_terrain.currentTextChanged.connect(self._schedule_live_preview)

        weather_row.addWidget(self.combo_weather)
        weather_row.addWidget(self.combo_terrain)
        field_layout.addLayout(weather_row)

        right_col.addWidget(field_frame)

        editor_section.addWidget(self.kos_panel, 1)
        editor_section.addLayout(center_col, 2)
        editor_section.addLayout(right_col, 1)

        main_layout.addLayout(editor_section, 1)

    # ── Import Tab Builders ──

    def _build_tab_paste(self, parent: QWidget):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # Team paste
        team_col = QVBoxLayout()
        lbl_t = QLabel("Il Tuo Team (max 6 Pokémon)")
        lbl_t.setStyleSheet(f"color: {Palette.PRIMARY}; font-weight: bold; font-size: 12px;")
        self.txt_team = QTextEdit()
        self.txt_team.setPlaceholderText("Incolla qui il tuo team in formato Pokémon Showdown...")
        self.txt_team.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px; padding: 6px;"
        )
        self.txt_team.setMaximumHeight(120)
        btn_load = QPushButton("Carica Team")
        btn_load.setStyleSheet(
            f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"border-radius: 6px; padding: 6px; font-weight: bold;"
        )
        btn_load.clicked.connect(self._on_load_team)
        team_col.addWidget(lbl_t)
        team_col.addWidget(self.txt_team)
        team_col.addWidget(btn_load)

        # Roster paste
        roster_col = QVBoxLayout()
        lbl_r = QLabel("Roster Avversari (illimitato)")
        lbl_r.setStyleSheet(f"color: {Palette.SECONDARY}; font-weight: bold; font-size: 12px;")
        self.txt_roster = QTextEdit()
        self.txt_roster.setPlaceholderText("Incolla qui uno o più team avversari...")
        self.txt_roster.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 6px; padding: 6px;"
        )
        self.txt_roster.setMaximumHeight(120)
        btn_add = QPushButton("Aggiungi al Roster")
        btn_add.setStyleSheet(
            f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; "
            f"border-radius: 6px; padding: 6px; font-weight: bold;"
        )
        btn_add.clicked.connect(self._on_add_roster)
        roster_col.addWidget(lbl_r)
        roster_col.addWidget(self.txt_roster)
        roster_col.addWidget(btn_add)

        layout.addLayout(team_col, 1)
        layout.addLayout(roster_col, 1)

    def _build_tab_meta_replay(self, parent: QWidget):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(12)

        lbl = QLabel("Importa team archetipici dal database replay.")
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(lbl)

        self.combo_distanza = QComboBox()
        self.combo_distanza.addItems(["Distanza Varianti: 0", "Distanza Varianti: 1", "Distanza Varianti: 2"])
        self.combo_distanza.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self.combo_distanza)

        self.spin_min_match = QSpinBox()
        self.spin_min_match.setRange(1, 1000)
        self.spin_min_match.setValue(5)
        self.spin_min_match.setPrefix("Min Match: ")
        self.spin_min_match.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self.spin_min_match)

        btn = QPushButton("Importa Teams")
        btn.setStyleSheet(
            f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"border-radius: 6px; padding: 6px 16px; font-weight: bold;"
        )
        btn.clicked.connect(self._on_search_meta_teams)
        layout.addWidget(btn)

    def _build_tab_meta_usage(self, parent: QWidget):
        layout = QHBoxLayout(parent)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(12)

        lbl = QLabel("Importa build singole dal meta per utilizzo.")
        lbl.setStyleSheet(f"color: {Palette.TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(lbl)

        self.spin_min_usage = QSpinBox()
        self.spin_min_usage.setRange(1, 1000)
        self.spin_min_usage.setValue(10)
        self.spin_min_usage.setPrefix("Min Usage: ")
        self.spin_min_usage.setStyleSheet(
            f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_COLOR}; border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self.spin_min_usage)

        btn = QPushButton("Importa Build")
        btn.setStyleSheet(
            f"background-color: {Palette.SECONDARY}; color: {Palette.BG_APP}; "
            f"border-radius: 6px; padding: 6px 16px; font-weight: bold;"
        )
        btn.clicked.connect(self._on_import_meta_roster)
        layout.addWidget(btn)
        layout.addStretch()

    # ── Preview Table Builder ──

    def _make_preview_table(self, title: str, title_color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_SURFACE_ELEVATED}; border-radius: 10px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {title_color}; border: none;")
        header_row.addWidget(lbl)
        header_row.addStretch()

        btn_print = QPushButton("⎙")
        btn_print.setToolTip("Stampa / Esporta PDF")
        btn_print.setFixedSize(28, 28)
        btn_print.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_MUTED}; "
            f"border-radius: 14px; border: 1px solid {Palette.BORDER_LIGHT}; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {Palette.PRIMARY}; }}"
        )
        header_row.addWidget(btn_print)
        layout.addLayout(header_row)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Pokémon", "Mossa", "Danno %"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setStyleSheet(TABLE_STYLE)
        table.setMinimumHeight(100)

        layout.addWidget(table)

        frame._table = table
        frame._title = title
        btn_print.clicked.connect(lambda: self._print_preview_table(frame._title, frame._table))

        return frame

    # ── Toggle Import Panel ──

    def _toggle_import_panel(self):
        visible = not self.import_panel.isVisible()
        self.import_panel.setVisible(visible)
        self.btn_manage_team.setChecked(visible)

    # ── Icon button style ──

    def _icon_btn_style(self, selected: bool) -> str:
        border = Palette.PRIMARY if selected else Palette.BORDER_LIGHT
        bg = Palette.BG_SURFACE_ELEVATED if selected else Palette.BG_CARD
        return (
            f"QPushButton {{ background-color: {bg}; border-radius: 8px; "
            f"border: 2px solid {border}; }}"
            f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; }}"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # BUILD REPORT PAGE
    # ══════════════════════════════════════════════════════════════════════════

    def _build_report_page(self):
        layout = QVBoxLayout(self.page_report)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()

        btn_back = QPushButton("← Torna all'Editor")
        btn_back.setStyleSheet(
            f"background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 8px; padding: 8px 16px; font-weight: bold;"
        )
        btn_back.clicked.connect(lambda: self.root_stack.setCurrentIndex(0))
        top_bar.addWidget(btn_back)
        top_bar.addSpacing(24)

        self._report_tab_btns: List[QPushButton] = []
        TAB_LABELS = ["Report Best Switch on Threat", "Report Bulk", "Report Offence"]
        for i, label in enumerate(TAB_LABELS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(self._tab_btn_style(False))
            btn.clicked.connect(lambda checked, idx=i: self._switch_report_tab(idx))
            self._report_tab_btns.append(btn)
            top_bar.addWidget(btn)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        self.report_stack = QStackedWidget()
        layout.addWidget(self.report_stack)

        self.tab_best_switch = QWidget()
        self._build_best_switch_tab()
        self.report_stack.addWidget(self.tab_best_switch)

        self.tab_bulk = QWidget()
        self._build_accordion_tab(self.tab_bulk, "bulk")
        self.report_stack.addWidget(self.tab_bulk)

        self.tab_offence = QWidget()
        self._build_accordion_tab(self.tab_offence, "offence")
        self.report_stack.addWidget(self.tab_offence)

        self._switch_report_tab(0)

    def _tab_btn_style(self, selected: bool) -> str:
        if selected:
            return (
                f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
                f"border-radius: 20px; padding: 8px 24px; font-weight: bold; font-size: 13px; border: none; }}"
            )
        return (
            f"QPushButton {{ background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_MUTED}; "
            f"border-radius: 20px; padding: 8px 24px; font-size: 13px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
            f"QPushButton:hover {{ color: {Palette.TEXT_PRIMARY}; }}"
        )

    def _switch_report_tab(self, idx: int):
        for i, btn in enumerate(self._report_tab_btns):
            btn.setStyleSheet(self._tab_btn_style(i == idx))
            btn.setChecked(i == idx)
        self.report_stack.setCurrentIndex(idx)

    def _build_best_switch_tab(self):
        layout = QVBoxLayout(self.tab_best_switch)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self.best_switch_table = QTableWidget()
        HEADERS = [
            "Threat", "Move", "Target", "Damage on Target",
            "Suggested Switch", "Damage on Switch",
            "Pressure from Target", "Target Move",
            "Pressure from Switch", "Switch Move"
        ]
        self.best_switch_table.setColumnCount(len(HEADERS))
        self.best_switch_table.setHorizontalHeaderLabels(HEADERS)
        self.best_switch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.best_switch_table.horizontalHeader().setStretchLastSection(True)
        self.best_switch_table.verticalHeader().setVisible(False)
        self.best_switch_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.best_switch_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.best_switch_table.setStyleSheet(TABLE_STYLE)
        self.best_switch_table.setSortingEnabled(True)
        layout.addWidget(self.best_switch_table)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_print = QPushButton("Print / PDF")
        btn_print.setStyleSheet(
            f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"border-radius: 16px; padding: 8px 24px; font-weight: bold;"
        )
        btn_print.clicked.connect(lambda: self._print_report("best_switch"))
        bottom_row.addWidget(btn_print)
        layout.addLayout(bottom_row)

    def _build_accordion_tab(self, parent_widget: QWidget, mode: str):
        layout = QHBoxLayout(parent_widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(16)

        left_col = QVBoxLayout()
        selector = ReportPokemonSelector()
        selector.pokemon_selected.connect(lambda idx: self._on_report_pokemon_selected(mode, idx))
        left_col.addWidget(selector)
        left_col.addStretch()
        layout.addLayout(left_col)

        right_col = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(6)

        content_layout.addStretch()
        scroll.setWidget(content)
        right_col.addWidget(scroll)

        layout.addLayout(right_col, 1)

        if mode == "bulk":
            self.bulk_selector = selector
            self.bulk_layout = content_layout

            bottom_row = QHBoxLayout()
            bottom_row.addStretch()
            btn_print = QPushButton("Print / PDF")
            btn_print.setStyleSheet(
                f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
                f"border-radius: 16px; padding: 8px 24px; font-weight: bold;"
            )
            btn_print.clicked.connect(lambda: self._print_report("bulk"))
            bottom_row.addWidget(btn_print)
            right_col.addLayout(bottom_row)
        else:
            self.offence_selector = selector
            self.offence_layout = content_layout

            bottom_row = QHBoxLayout()
            bottom_row.addStretch()
            btn_print = QPushButton("Print / PDF")
            btn_print.setStyleSheet(
                f"background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
                f"border-radius: 16px; padding: 8px 24px; font-weight: bold;"
            )
            btn_print.clicked.connect(lambda: self._print_report("offence"))
            bottom_row.addWidget(btn_print)
            right_col.addLayout(bottom_row)

    # ══════════════════════════════════════════════════════════════════════════
    # CONVERSIONE E LOGICA
    # ══════════════════════════════════════════════════════════════════════════

    def _member_to_dict(self, member: TeamMember) -> Dict[str, Any]:
        return {
            "name": member.species,
            "options": {
                "nature": member.nature or "Serious",
                "item": member.item or None,
                "ability": member.ability or None,
                "evs": dict(member.evs) if member.evs else {},
                "ivs": dict(member.ivs) if member.ivs else {},
                "teraType": member.tera_type or None,
            },
            "moves": list(member.moves),
        }

    def _get_base_stats_for_species(self, species_name: str) -> dict:
        """Recupera le base stats dal DB."""
        from database.connection import SessionLocal
        from database.models_v2 import PokemonSpeciesV2
        with SessionLocal() as session:
            pkmn = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species_name).first()
            if pkmn:
                return {
                    "hp": pkmn.bst_hp, "atk": pkmn.bst_atk, "def": pkmn.bst_def,
                    "spa": pkmn.bst_spa, "spd": pkmn.bst_spd, "spe": pkmn.bst_spe
                }
        return {}

    def _apply_role_and_auto_build(self, pkmn: Dict[str, Any]):
        """Applica role detection e auto-build a un Pokémon se non ha spread custom."""
        species = pkmn.get("name", "")
        moves = pkmn.get("moves", [])
        base_stats = self._get_base_stats_for_species(species)

        role = detect_role(species, moves, base_stats)
        pkmn["_detected_role"] = role

        if not has_custom_spread(pkmn):
            build = generate_auto_build(role, base_stats, moves)
            if "options" not in pkmn:
                pkmn["options"] = {}
            pkmn["options"]["evs"] = build["evs"]
            if pkmn["options"].get("nature") in (None, "", "Hardy", "Serious"):
                pkmn["options"]["nature"] = build["nature"]

    # ══════════════════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ══════════════════════════════════════════════════════════════════════════

    def _on_load_team(self):
        paste = self.txt_team.toPlainText().strip()
        if not paste:
            QMessageBox.warning(self, "Attenzione", "Inserisci il team in formato Showdown.")
            return
        try:
            members = parse_pokepaste(paste)
            if not members:
                QMessageBox.warning(self, "Attenzione", "Nessun Pokémon riconosciuto nel paste.")
                return
            self._team = [self._member_to_dict(m) for m in members[:6]]

            # Role detection + auto-build per ogni membro del team
            for pkmn in self._team:
                self._apply_role_and_auto_build(pkmn)

            self._refresh_team_strip()
            self._update_analysis_button()
            if self._team:
                self._on_team_slot_clicked(0)
        except Exception as e:
            QMessageBox.critical(self, "Errore Parsing", f"Errore nel parsing del team:\n{e}")

    def _on_add_roster(self):
        paste = self.txt_roster.toPlainText().strip()
        if not paste:
            QMessageBox.warning(self, "Attenzione", "Inserisci il roster avversario in formato Showdown.")
            return
        try:
            members = parse_pokepaste(paste)
            if not members:
                QMessageBox.warning(self, "Attenzione", "Nessun Pokémon riconosciuto nel paste.")
                return
            new_dicts = [self._member_to_dict(m) for m in members]
            import json
            existing_builds = {json.dumps(m, sort_keys=True) for m in self._roster}
            for d in new_dicts:
                # Role detection + auto-build per ogni Pokémon del roster
                self._apply_role_and_auto_build(d)
                d_str = json.dumps(d, sort_keys=True)
                if d_str not in existing_builds:
                    self._roster.append(d)
                    existing_builds.add(d_str)
            self._refresh_roster_strip()
            self._update_analysis_button()
            self.txt_roster.clear()
        except Exception as e:
            QMessageBox.critical(self, "Errore Parsing", f"Errore nel parsing del roster:\n{e}")

    def _on_auto_allocate_evs(self):
        """Forza l'auto-allocazione EVs per il Pokémon attualmente selezionato."""
        if self._selected_team_idx is not None and self._selected_team_idx < len(self._team):
            member = self._team[self._selected_team_idx]
            member["options"]["evs"] = {}  # Reset
            self._apply_role_and_auto_build(member)
            self.panel_editor.load_member(member)
            self._schedule_live_preview()

    def _refresh_team_strip(self):
        """Aggiorna le icone nella strip del team."""
        for i, btn in enumerate(self.team_icon_btns):
            if i < len(self._team):
                mon = self._team[i]
                px = get_pokemon_pixmap(mon["name"], 32)
                if px:
                    btn.setIcon(QIcon(px))
                    btn.setIconSize(QSize(32, 32))
                btn.setToolTip(mon["name"])
                btn.setEnabled(True)
            else:
                btn.setIcon(QIcon())
                btn.setToolTip("")
                btn.setChecked(False)
                btn.setEnabled(False)

    def _refresh_roster_strip(self):
        """Aggiorna le icone nella strip del roster."""
        # Rimuovi tutti eccetto lo stretch
        while self.roster_icons_layout.count() > 1:
            item = self.roster_icons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, mon in enumerate(self._roster):
            btn = QPushButton()
            btn.setFixedSize(38, 38)
            btn.setCheckable(True)
            btn.setStyleSheet(self._icon_btn_style(False))
            btn.setCursor(Qt.PointingHandCursor)
            px = get_pokemon_pixmap(mon["name"], 28)
            if px:
                btn.setIcon(QIcon(px))
                btn.setIconSize(QSize(28, 28))
            btn.setToolTip(mon["name"])
            btn.clicked.connect(lambda checked, idx=i: self._on_roster_slot_clicked(idx))
            self.roster_icons_layout.insertWidget(self.roster_icons_layout.count() - 1, btn)

    def _on_team_slot_clicked(self, idx: int):
        if idx >= len(self._team):
            return
        self._selected_team_idx = idx

        for i, btn in enumerate(self.team_icon_btns):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._icon_btn_style(i == idx))

        self.panel_editor.load_member(self._team[idx])
        self._schedule_live_preview()

    def _on_roster_slot_clicked(self, idx: int):
        if idx >= len(self._roster):
            return
        self._selected_roster_idx = idx

        # Aggiorna selezione visuale
        for i in range(self.roster_icons_layout.count() - 1):
            widget = self.roster_icons_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setChecked(i == idx)
                widget.setStyleSheet(self._icon_btn_style(i == idx))

        # Carica nel pannello editor (mostra Pokémon roster)
        self.panel_editor.load_member(self._roster[idx])

    def _on_edit_build_changed(self):
        self._schedule_live_preview()

    def _update_analysis_button(self):
        can_analyze = bool(self._team) and bool(self._roster)
        self.btn_start_analysis.setEnabled(can_analyze)

    def _show_full_roster(self):
        if not self._roster:
            QMessageBox.information(self, "Roster", "Il roster è vuoto.")
            return
        dlg = FullRosterDialog(self._roster, self)
        dlg.exec()

    # ── Live Preview ──────────────────────────────────────────────────────────

    def _get_current_field_options(self) -> FieldOptions:
        weather = self.combo_weather.currentText()
        weather = None if weather == "Meteo" else weather
        terrain = self.combo_terrain.currentText()
        terrain = None if terrain == "Campo" else terrain
        return FieldOptions(
            gameType="Doubles",
            weather=weather,
            terrain=terrain,
            isReflect=self.btn_reflect.isChecked(),
            isLightScreen=self.btn_lightscreen.isChecked(),
            isAuroraVeil=self.btn_auroraveil.isChecked(),
            isFriendGuard=self.btn_friendguard.isChecked()
        )

    def _get_engine(self) -> TeamBuilderEngine:
        if self._engine is None:
            calc = SmogonDamageCalc(db_path="janalytics.db")
            self._engine = TeamBuilderEngine(calc)
        return self._engine

    def _schedule_live_preview(self):
        self._live_timer.start(300)

    def _run_live_preview(self):
        if self._selected_team_idx is None or not self._roster:
            return
        if self._selected_team_idx >= len(self._team):
            return

        selected = self._team[self._selected_team_idx]

        if self._live_worker and self._live_worker.isRunning():
            self._live_worker.quit()

        self._live_worker = LivePreviewWorker(self._get_engine(), selected, self._roster, self._get_current_field_options())
        self._live_worker.finished.connect(self._on_live_preview_done)
        self._live_worker.error.connect(lambda e: print(f"[LivePreview] Errore: {e}"))
        self._live_worker.start()

        self.kos_panel._table.setRowCount(0)
        self.threats_panel._table.setRowCount(0)
        self.lbl_progress.setText("⏳ Aggiornamento live preview...")

    def _on_live_preview_done(self, kos: List[Dict], threats: List[Dict]):
        self.lbl_progress.setText("")
        self._fill_preview_table(self.kos_panel._table, kos)
        self._fill_preview_table(self.threats_panel._table, threats)

    def _fill_preview_table(self, table: QTableWidget, entries: List[Dict]):
        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            table.setItem(row, 0, QTableWidgetItem(entry.get("pokemon", "")))
            table.setItem(row, 1, QTableWidgetItem(entry.get("move", "")))
            table.setItem(row, 2, QTableWidgetItem(entry.get("damage_range", "")))

            color = QColor(Palette.BG_SURFACE_ELEVATED if row % 2 == 0 else Palette.BG_CARD)
            for col in range(3):
                item = table.item(row, col)
                if item:
                    item.setBackground(color)

    # ── Start Analysis ────────────────────────────────────────────────────────

    def _on_start_analysis(self):
        if not self._team or not self._roster:
            QMessageBox.warning(self, "Dati mancanti", "Carica il team e il roster prima di avviare l'analisi.")
            return

        self.btn_start_analysis.setEnabled(False)
        self.lbl_progress.setText("⏳ Analisi in corso... potrebbe richiedere qualche momento.")

        if self._analysis_worker and self._analysis_worker.isRunning():
            self._analysis_worker.quit()

        self._analysis_worker = AnalysisWorker(self._get_engine(), self._team, self._roster, self._get_current_field_options())
        self._analysis_worker.progress.connect(self._on_analysis_progress)
        self._analysis_worker.finished.connect(self._on_analysis_finished)
        self._analysis_worker.error.connect(self._on_analysis_error)
        self._analysis_worker.start()

    def _on_analysis_progress(self, pct: int, msg: str):
        self.lbl_progress.setText(f"⏳ {pct}% — {msg}")

    def _on_analysis_finished(self, data: Dict):
        self._report_data = data
        self.btn_start_analysis.setEnabled(True)
        self.lbl_progress.setText("✓ Analisi completata!")

        self._populate_best_switch(data.get("best_switch", []))
        self._populate_accordion_report("bulk", data.get("bulk", {}))
        self._populate_accordion_report("offence", data.get("offence", {}))

        self.bulk_selector.load_team(self._team)
        self.offence_selector.load_team(self._team)

        self.root_stack.setCurrentIndex(1)
        self._switch_report_tab(0)

    def _on_analysis_error(self, msg: str):
        self.btn_start_analysis.setEnabled(True)
        self.lbl_progress.setText("")
        QMessageBox.critical(self, "Errore Analisi", f"Si è verificato un errore:\n{msg}")

    # ── Popolamento Report ────────────────────────────────────────────────────

    def _populate_best_switch(self, rows: List[Dict]):
        self.best_switch_table.setSortingEnabled(False)
        self.best_switch_table.setRowCount(len(rows))

        COLS = [
            "threat", "move", "target", "damage_on_target",
            "suggested_switch", "damage_on_switch",
            "pressure_from_target", "target_move",
            "pressure_from_switch", "switch_move"
        ]

        for r, row_data in enumerate(rows):
            for c, col_key in enumerate(COLS):
                item = QTableWidgetItem(str(row_data.get(col_key, "—")))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col_key == "damage_on_target":
                    max_pct = row_data.get("max_on_target", 0)
                    if max_pct >= 100:
                        item.setForeground(QColor(Palette.DANGER_BRIGHT))
                    elif max_pct >= 50:
                        item.setForeground(QColor(Palette.WARNING))
                elif col_key in ("pressure_from_target", "pressure_from_switch"):
                    max_pct = row_data.get("max_on_target", 0)
                    if row_data.get(col_key, "").replace("%", "").replace(" ", "").replace("-", "").replace(".", "").replace("0", "") != "":
                        item.setForeground(QColor(Palette.SUCCESS))
                if col_key == "threat":
                    build = row_data.get("threat_build", {})
                    opts = build.get("options", {})
                    nature = opts.get("nature", "")
                    item_str = opts.get("item", "")
                    ability = opts.get("ability", "")
                    evs = opts.get("evs", {})
                    tera = opts.get("teraType", "")
                    
                    details = []
                    if ability: details.append(f"Ability: {ability}")
                    if tera: details.append(f"Tera: {tera}")
                    if nature: details.append(f"Nature: {nature}")
                    
                    if evs:
                        ev_parts = []
                        for stat in ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]:
                            if evs.get(stat, 0) > 0:
                                ev_parts.append(f"{evs[stat]} {stat}")
                        if ev_parts:
                            details.append("EVs: " + " / ".join(ev_parts))
                            
                    tooltip = f"{build.get('name', '—')}"
                    if item_str: tooltip += f" @ {item_str}"
                    if details: tooltip += f"\n{' | '.join(details)}"
                    
                    moves = build.get("moves", [])
                    if moves: tooltip += f"\nMoves: {', '.join([m for m in moves if m])}"
                    
                    item.setToolTip(tooltip)
                    
                self.best_switch_table.setItem(r, c, item)

            bg = QColor(Palette.BG_SURFACE_ELEVATED if r % 2 == 0 else Palette.BG_CARD)
            for c in range(len(COLS)):
                it = self.best_switch_table.item(r, c)
                if it:
                    it.setBackground(bg)

        self.best_switch_table.setSortingEnabled(True)
        self.best_switch_table.resizeColumnsToContents()

    def _populate_accordion_report(self, mode: str, report: Dict[str, Dict[str, List[Dict]]]):
        if mode == "bulk":
            self._bulk_report = report
        else:
            self._offence_report = report

    def _on_report_pokemon_selected(self, mode: str, idx: int):
        if idx >= len(self._team):
            return
        mon_name = self._team[idx]["name"]

        if mode == "bulk":
            report = getattr(self, "_bulk_report", {})
            layout = self.bulk_layout
            key_att = "attacker"
        else:
            report = getattr(self, "_offence_report", {})
            layout = self.offence_layout
            key_att = "defender"

        # Clear existing layout (accordion items and stretch)
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mon_data = report.get(mon_name, {"1HKO": [], "2HKO": [], "3HKO+": []})
        all_entries = []
        for cat in ["1HKO", "2HKO", "3HKO+"]:
            for entry in mon_data.get(cat, []):
                e2 = entry.copy()
                e2["_ko_cat"] = cat
                all_entries.append(e2)

        # Group by species
        by_species = {}
        for entry in all_entries:
            opp = entry.get(key_att, "?")
            if opp not in by_species:
                by_species[opp] = []
            by_species[opp].append(entry)

        import json
        # Ordina specie per KO tier (1HKO prima), poi per numero mosse in quel tier, poi per nome
        sorted_species = sorted(
            by_species.keys(),
            key=lambda s: self._species_sort_key(s, by_species[s])
        )
        for species in sorted_species:
            species_entries = by_species[species]
            
            by_build = self._group_entries_by_build(species_entries)

            acc = AccordionItem(species)
            acc.set_count(len(by_build))

            for b_str, b_data in by_build.items():
                sig = b_data["sig"]
                b_entries = b_data["entries"]

                header = f"<b>{species}</b>"
                if sig['item']: header += f" @ {sig['item']}"

                details = []
                if sig['ability']: details.append(f"Ability: {sig['ability']}")
                if sig['tera']: details.append(f"Tera: {sig['tera']}")
                if sig['nature']: details.append(f"Nature: {sig['nature']}")

                if sig['evs']:
                    ev_parts = []
                    for stat in ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]:
                        if sig['evs'].get(stat, 0) > 0:
                            ev_parts.append(f"{sig['evs'][stat]} {stat}")
                    if ev_parts:
                        details.append("EVs: " + " / ".join(ev_parts))

                details_str = " | ".join(details)
                moves_str = "Moves: " + ", ".join([m for m in sig['moves'] if m]) if sig['moves'] else ""

                text_lines = [header]
                if details_str: text_lines.append(f"<span style='color: {Palette.TEXT_MUTED}; font-size: 11px;'>{details_str}</span>")
                if moves_str: text_lines.append(f"<span style='color: {Palette.TEXT_MUTED}; font-size: 11px;'>{moves_str}</span>")

                # Append moves sorted by KO category
                cat_order = {"1HKO": 1, "2HKO": 2, "3HKO+": 3}
                b_entries.sort(key=lambda x: (cat_order.get(x["_ko_cat"], 9), -x.get("max_pct", 0)))

                for entry in b_entries:
                    move = entry.get("move", "?")
                    dmg = entry.get("damage_range", "?%")
                    cat = entry["_ko_cat"]
                    color = Palette.DANGER_BRIGHT if cat == "1HKO" else (Palette.WARNING if cat == "2HKO" else Palette.TEXT_PRIMARY)
                    text_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;<span style='color: {color};'>[{cat}]</span> <span style='color: {Palette.PRIMARY};'>► {move}</span> : <b>{dmg}</b>")

                text = "<br>".join(text_lines)
                
                # Aggiungiamo separatore se ci sono più build per la stessa specie (eccetto per l'ultimo testo)
                # Oppure lo facciamo come entry a sè stante
                acc.add_entry(text)

            layout.addWidget(acc)

        layout.addStretch()

    def _build_team_detail_html(self) -> str:
        """Genera l'HTML con il dettaglio del team in stile in-game (card con icone)."""
        html = "<h2>Dettaglio Team Analizzato</h2>"

        for mon in self._team:
            name = mon.get("name", "—")
            opts = mon.get("options", {})
            evs = opts.get("evs", {})
            role = mon.get("_detected_role", "—")
            ability = opts.get("ability", "") or ""
            item = opts.get("item", "") or ""
            tera = opts.get("teraType", "") or ""
            nature = opts.get("nature", "") or ""
            moves = [m for m in mon.get("moves", []) if m]

            ev_parts = []
            for stat in ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]:
                v = evs.get(stat, 0)
                if v > 0:
                    ev_parts.append(f"{v} {stat}")
            ev_str = " / ".join(ev_parts) if ev_parts else "—"

            # Colore role badge
            if role == "Offensive":
                role_color = "#FF6B6B"
                role_icon = "⚔"
            elif role == "Defensive":
                role_color = "#6BC5FF"
                role_icon = "🛡"
            else:
                role_color = "#FFD93D"
                role_icon = "⚡"

            # Recupera il percorso icona del Pokémon
            icon_path = get_pokemon_icon_path(name)
            icon_html = ""
            if icon_path and os.path.exists(icon_path):
                icon_html = f"<img src='file:///{icon_path}' width='56' height='56' style='vertical-align: middle;' />"

            html += (
                f"<div style='background: #131519; border: 1px solid #252932; border-radius: 8px; "
                f"padding: 10px 14px; margin: 8px 0; border-left: 4px solid {role_color};'>"
                f"<table cellspacing='0' cellpadding='0' style='width: 100%; border: none;'><tr>"
                f"<td style='width: 64px; border: none; vertical-align: top; padding-right: 12px;'>{icon_html}</td>"
                f"<td style='border: none; vertical-align: top;'>"
                f"<div style='font-size: 13pt; font-weight: bold; color: #DEDAD4;'>"
                f"{name}"
                f"<span style='color: {role_color}; font-size: 10pt; margin-left: 8px;'>{role_icon} {role}</span>"
                f"</div>"
            )

            if item:
                html += f"<div style='color: #C49A3C; font-size: 10pt; margin-top: 2px;'>@ {item}</div>"

            info_parts = []
            if ability:
                info_parts.append(f"<b>Ability:</b> {ability}")
            if tera:
                info_parts.append(f"<b>Tera:</b> {tera}")
            if nature:
                info_parts.append(f"<b>Nature:</b> {nature}")
            if info_parts:
                html += f"<div style='color: #8A9DB0; font-size: 9pt; margin-top: 3px;'>{' &nbsp;|&nbsp; '.join(info_parts)}</div>"

            html += f"<div style='color: #8577A8; font-size: 9pt; margin-top: 2px;'>EVs: {ev_str}</div>"

            if moves:
                moves_html = ""
                for m in moves:
                    moves_html += f"<span style='background: #1C1F26; border: 1px solid #252932; border-radius: 4px; padding: 2px 8px; margin: 2px 3px; display: inline-block; font-size: 9pt; color: #DEDAD4;'>{m}</span>"
                html += f"<div style='margin-top: 4px;'>{moves_html}</div>"

            html += "</td></tr></table></div>"

        return html

    @staticmethod
    def _species_sort_key(species: str, species_entries: list) -> tuple:
        """
        Ordina le specie per KO tier (1HKO prima, poi 2HKO, poi 3HKO+),
        poi a parità per numero di mosse in quel tier (decrescente), poi per nome.
        """
        cat_order = {"1HKO": 0, "2HKO": 1, "3HKO+": 2}
        best_cat = 2  # default worst (3HKO+)
        counts = {0: 0, 1: 0, 2: 0}
        for e in species_entries:
            cat_val = cat_order.get(e.get("_ko_cat", "3HKO+"), 2)
            if cat_val < best_cat:
                best_cat = cat_val
            counts[cat_val] += 1
        # Sort: best KO tier asc, count of that tier desc, then alphabetical
        return (best_cat, -counts[best_cat], species.lower())

    @staticmethod
    def _group_entries_by_build(species_entries: list) -> dict:
        """
        Raggruppa le entry di una specie ignorando le mosse (per accorpare build identiche).
        Deduplica inoltre le entry dei danni calcolati se coincidenti.
        """
        import json
        by_build = {}
        for entry in species_entries:
            sig = {
                "item": entry.get("item", ""),
                "ability": entry.get("ability", ""),
                "nature": entry.get("nature", ""),
                "tera": entry.get("teraType", ""),
                "evs": entry.get("evs", {})
            }
            sig_str = json.dumps(sig, sort_keys=True)
            if sig_str not in by_build:
                by_build[sig_str] = {"sig": sig, "entries": [], "merged_moves": set()}
            
            by_build[sig_str]["entries"].append(entry)
            for m in entry.get("moves", []):
                if m:
                    by_build[sig_str]["merged_moves"].add(m)

        for b_str, b_data in by_build.items():
            b_data["sig"]["moves"] = sorted(list(b_data["merged_moves"]))
            
            deduped = {}
            for e in b_data["entries"]:
                m = e.get("move", "?")
                if m not in deduped or e.get("max_pct", 0) > deduped[m].get("max_pct", 0):
                    deduped[m] = e
            b_data["entries"] = list(deduped.values())

        return by_build

    def _build_grouped_report_html(self, mode: str) -> str:
        """Genera l'HTML del report bulk/offence raggruppato per specie → build."""
        report = getattr(self, f"_{mode}_report", {})
        key_att = "attacker" if mode == "bulk" else "defender"
        title = "Report Bulk — Danni Subiti" if mode == "bulk" else "Report Offence — Danni Inflitti"

        html = f"<h2>{title}</h2>"

        for mon_name, categories in report.items():
            html += f"<h3 style='color: #C49A3C; border-bottom: 2px solid #C49A3C; padding-bottom: 4px;'>{mon_name}</h3>"

            # Unisci tutte le entries con la categoria KO
            all_entries = []
            for cat in ["1HKO", "2HKO", "3HKO+"]:
                for entry in categories.get(cat, []):
                    e2 = entry.copy()
                    e2["_ko_cat"] = cat
                    all_entries.append(e2)

            if not all_entries:
                html += "<p style='color: #888;'><i>Nessun risultato rilevante.</i></p>"
                continue

            # Raggruppa per specie
            by_species = {}
            for entry in all_entries:
                opp = entry.get(key_att, "?")
                by_species.setdefault(opp, []).append(entry)

            # Ordina specie per KO tier, poi per numero mosse in quel tier, poi per nome
            sorted_species = sorted(
                by_species.keys(),
                key=lambda s: self._species_sort_key(s, by_species[s])
            )

            for species in sorted_species:
                species_entries = by_species[species]

                by_build = self._group_entries_by_build(species_entries)

                # Icona del Pokémon roster
                icon_path = get_pokemon_icon_path(species)
                icon_html = ""
                if icon_path and os.path.exists(icon_path):
                    icon_html = f"<img src='file:///{icon_path}' width='36' height='36' style='vertical-align: middle; margin-right: 8px;' />"

                for b_str, b_data in by_build.items():
                    sig = b_data["sig"]
                    b_entries = b_data["entries"]

                    # Best KO of this build
                    cat_order_map = {"1HKO": 0, "2HKO": 1, "3HKO+": 2}
                    best_cat_val = min(cat_order_map.get(e["_ko_cat"], 2) for e in b_entries)
                    if best_cat_val == 0:
                        border_color = "#FF6B6B"
                    elif best_cat_val == 1:
                        border_color = "#FFD93D"
                    else:
                        border_color = "#607080"

                    # Header build
                    build_header = f"{icon_html}<b style='color: #DEDAD4; font-size: 11pt;'>{species}</b>"
                    if sig['item']:
                        build_header += f" <span style='color: #C49A3C;'>@ {sig['item']}</span>"

                    details = []
                    if sig['ability']:
                        details.append(f"Ability: {sig['ability']}")
                    if sig['tera']:
                        details.append(f"Tera: {sig['tera']}")
                    if sig['nature']:
                        details.append(f"Nature: {sig['nature']}")
                    if sig['evs']:
                        ev_parts = []
                        for stat in ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]:
                            if sig['evs'].get(stat, 0) > 0:
                                ev_parts.append(f"{sig['evs'][stat]} {stat}")
                        if ev_parts:
                            details.append("EVs: " + " / ".join(ev_parts))

                    details_str = " | ".join(details)
                    moves_str = ", ".join([m for m in sig['moves'] if m])

                    html += (
                        f"<div style='background: #131519; border: 1px solid #252932; border-radius: 6px; "
                        f"padding: 8px 12px; margin: 6px 0; border-left: 4px solid {border_color};'>"
                    )
                    html += f"<div>{build_header}</div>"
                    if details_str:
                        html += f"<div style='color: #8A9DB0; font-size: 9pt;'>{details_str}</div>"
                    if moves_str:
                        html += f"<div style='color: #8577A8; font-size: 9pt;'>Moves: {moves_str}</div>"

                    # Mosse ordinate per categoria KO
                    cat_order = {"1HKO": 1, "2HKO": 2, "3HKO+": 3}
                    b_entries.sort(key=lambda x: (cat_order.get(x["_ko_cat"], 9), -x.get("max_pct", 0)))

                    html += "<table cellspacing='0' cellpadding='3' style='margin-top: 4px; width: 100%; border: none;'>"
                    for entry in b_entries:
                        move = entry.get("move", "?")
                        dmg = entry.get("damage_range", "?%")
                        cat = entry["_ko_cat"]
                        if cat == "1HKO":
                            cat_color = "#FF6B6B"
                        elif cat == "2HKO":
                            cat_color = "#FFD93D"
                        else:
                            cat_color = "#8A9DB0"
                        html += (f"<tr>"
                                 f"<td style='width: 60px; color: {cat_color}; font-weight: bold; border: none;'>[{cat}]</td>"
                                 f"<td style='color: #C49A3C; border: none;'>► {move}</td>"
                                 f"<td style='text-align: right; color: #DEDAD4; border: none;'><b>{dmg}</b></td>"
                                 f"</tr>")
                    html += "</table>"
                    html += "</div>"

        return html

    def _print_preview_table(self, title: str, table: QTableWidget):
        html = self._build_team_detail_html()
        html += f"<h2>{title}</h2><table border='1' cellspacing='0' cellpadding='4'>"
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        for r in range(table.rowCount()):
            html += "<tr>"
            for c in range(table.columnCount()):
                item = table.item(r, c)
                html += f"<td>{item.text() if item else ''}</td>"
            html += "</tr>"
        html += "</table>"
        self._save_html_as_pdf(html, title)

    def _print_report(self, mode: str):
        html = self._build_team_detail_html()
        html += "<hr style='border: 1px solid #444; margin: 16px 0;'>"

        if mode == "best_switch":
            table = self.best_switch_table
            headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
            html += "<h2>Report Best Switch on Threat</h2>"
            html += "<table border='1' cellspacing='0' cellpadding='4'>"
            html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
            for r in range(table.rowCount()):
                html += "<tr>"
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    html += f"<td>{item.text() if item else ''}</td>"
                html += "</tr>"
            html += "</table>"
            self._save_html_as_pdf(html, "Report_BestSwitch")
        elif mode in ("bulk", "offence"):
            html += self._build_grouped_report_html(mode)
            title = "Report_Bulk" if mode == "bulk" else "Report_Offence"
            self._save_html_as_pdf(html, title)

    def _save_html_as_pdf(self, html: str, default_name: str):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva PDF", f"{default_name}.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        doc = QTextDocument()
        doc.setHtml(
            "<style>"
            "body { font-family: 'Segoe UI', sans-serif; font-size: 10pt; color: #e0e0e0; background: #0f0f1a; } "
            "h2 { color: #C49A3C; margin-top: 20px; } "
            "h3 { margin-top: 14px; margin-bottom: 6px; } "
            "table { border-collapse: collapse; width: 100%; } "
            "th { background: #1a1a2e; color: #C49A3C; padding: 6px 8px; font-size: 9pt; } "
            "td { border: 1px solid #333; padding: 4px 8px; font-size: 9pt; } "
            "tr:nth-child(even) { background: #16162a; } "
            "tr:nth-child(odd) { background: #1a1a2e; } "
            "hr { border: 1px solid #333; } "
            "</style>"
            + html
        )
        doc.print_(printer)
        QMessageBox.information(self, "Esportazione", f"PDF salvato in:\n{path}")

    # ── Meta Import Logic ──

    def _auto_assign_evs(self, pkmn: dict, role: str):
        from database.connection import SessionLocal
        from database.models_v2 import PokemonSpeciesV2

        species = pkmn.get("name", "")
        with SessionLocal() as session:
            sp = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.id == species).first()
            if not sp:
                sp = session.query(PokemonSpeciesV2).filter(PokemonSpeciesV2.name == species).first()
                if not sp:
                    return

            evs = {}
            if role == "offense":
                if (sp.bst_atk or 0) > (sp.bst_spa or 0):
                    evs["atk"] = 32
                    evs["spa"] = 0
                else:
                    evs["spa"] = 32
                    evs["atk"] = 0
                evs["spe"] = 32
                evs["hp"] = 2
            else:
                evs["hp"] = 32
                if (sp.bst_def or 0) > (sp.bst_spd or 0):
                    evs["def"] = 32
                    evs["spd"] = 0
                else:
                    evs["spd"] = 32
                    evs["def"] = 0
                evs["atk"] = 2

            if "options" not in pkmn:
                pkmn["options"] = {}
            pkmn["options"]["evs"] = evs

            if "nature" not in pkmn["options"] or pkmn["options"]["nature"] in (None, "", "Hardy", "Serious"):
                if role == "offense":
                    pkmn["options"]["nature"] = "Jolly" if evs.get("atk") else "Timid"
                else:
                    pkmn["options"]["nature"] = "Impish" if evs.get("def") else "Careful"

    def _on_import_meta_roster(self):
        from database.connection import SessionLocal
        from database.models_v2 import MatchTeamV2, TeamVariantBuild, PokemonBuild, PokemonBuildMove
        from sqlalchemy import func, desc

        min_usage = self.spin_min_usage.value()

        try:
            with SessionLocal() as session:
                query = session.query(
                    PokemonBuild, func.count(MatchTeamV2.id).label('usage')
                ).join(TeamVariantBuild, TeamVariantBuild.build_id == PokemonBuild.id) \
                 .join(MatchTeamV2, MatchTeamV2.team_variant_id == TeamVariantBuild.team_variant_id) \
                 .group_by(PokemonBuild.id) \
                 .having(func.count(MatchTeamV2.id) >= min_usage) \
                 .order_by(desc('usage')).limit(100)

                results = query.all()
                if not results:
                    QMessageBox.information(self, "Meta Roster", "Nessuna build trovata con questo utilizzo minimo.")
                    return

                added_count = 0
                for build, usage in results:
                    moves = [m.move.name for m in build.move_slots if m.move]
                    pkmn = {
                        "name": build.species_id,
                        "options": {
                            "ability": build.ability_id,
                            "item": build.item_id,
                            "teraType": build.tera_type,
                            "nature": build.nature,
                        },
                        "moves": moves
                    }

                    # Role detection + auto-build
                    self._apply_role_and_auto_build(pkmn)

                    import json
                    pkmn_hash = json.dumps(pkmn, sort_keys=True)
                    if not any(json.dumps(r, sort_keys=True) == pkmn_hash for r in self._roster):
                        self._roster.append(pkmn)
                        added_count += 1

                self._refresh_roster_strip()
                self._refresh_team_strip()
                self._update_analysis_button()
                QMessageBox.information(self, "Meta Roster", f"Importate {added_count} build (sopra soglia uso {min_usage}) nel roster.")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore importazione meta roster: {str(e)}")

    def _on_search_meta_teams(self):
        from src.analytics.team_clustering import get_team_archetypes_and_groupings
        from database.connection import SessionLocal
        from database.models_v2 import TeamVariantV2, TeamVariantBuild, PokemonBuild, PokemonBuildMove
        from sqlalchemy.orm import joinedload
        import json

        dist_str = self.combo_distanza.currentText()
        max_dist = int(dist_str.split(":")[-1].strip())
        min_match = self.spin_min_match.value()

        try:
            res = get_team_archetypes_and_groupings(max_distance=max_dist)

            added_teams = 0
            added_pkmn = 0

            with SessionLocal() as session:
                for group in res:
                    if group['total_matches'] >= min_match:
                        best_config_id = None
                        max_c = 0
                        for variant in group['variants']:
                            for cid, cdata in variant['configs'].items():
                                c_matches = len(cdata['matches'])
                                if c_matches > max_c:
                                    max_c = c_matches
                                    best_config_id = cid

                        if best_config_id:
                            variant_obj = session.query(TeamVariantV2).options(
                                joinedload(TeamVariantV2.builds).joinedload(TeamVariantBuild.build).joinedload(PokemonBuild.move_slots).joinedload(PokemonBuildMove.move)
                            ).filter(TeamVariantV2.id == best_config_id).first()

                            if variant_obj:
                                added_teams += 1
                                for tvb in variant_obj.builds:
                                    b = tvb.build
                                    moves = [m.move.name for m in b.move_slots if m.move]
                                    pkmn = {
                                        "name": b.species_id,
                                        "options": {
                                            "ability": b.ability_id,
                                            "item": b.item_id,
                                            "teraType": b.tera_type,
                                            "nature": b.nature,
                                        },
                                        "moves": moves
                                    }

                                    # Role detection + auto-build
                                    self._apply_role_and_auto_build(pkmn)

                                    pkmn_hash = json.dumps(pkmn, sort_keys=True)
                                    if not any(json.dumps(r, sort_keys=True) == pkmn_hash for r in self._roster):
                                        self._roster.append(pkmn)
                                        added_pkmn += 1

            self._refresh_roster_strip()
            self._refresh_team_strip()
            self._update_analysis_button()

            if added_teams == 0:
                QMessageBox.information(self, "Importazione Meta", "Nessun team trovato con i criteri specificati.")
            else:
                QMessageBox.information(self, "Importazione Meta", f"Importati {added_teams} team archetipici ({added_pkmn} nuovi Pokémon inseriti nel roster).")

        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore ricerca meta teams: {str(e)}")
