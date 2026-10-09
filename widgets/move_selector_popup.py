"""
move_selector_popup.py
======================
Widget popup per la selezione delle mosse dal move pool legale del Pokémon.
Include MoveChip (chip cliccabile inline) e MoveSelectorPopup (dialog modale).
"""

from typing import List, Dict, Any, Optional, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QWidget, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from config.theme import Palette


TYPE_COLORS = {
    "Normal": "#A8A77A", "Fire": "#EE8130", "Water": "#6390F0",
    "Electric": "#F7D02C", "Grass": "#7AC74C", "Ice": "#96D9D6",
    "Fighting": "#C22E28", "Poison": "#A33EA1", "Ground": "#E2BF65",
    "Flying": "#A98FF3", "Psychic": "#F95587", "Bug": "#A6B91A",
    "Rock": "#B6A136", "Ghost": "#735797", "Dragon": "#6F35FC",
    "Dark": "#705848", "Steel": "#B7B7CE", "Fairy": "#D685AD"
}

CATEGORY_ICONS = {
    "Physical": "💥",
    "Special": "🌀",
    "Status": "✦",
}


class MoveChip(QPushButton):
    """
    Chip cliccabile che mostra il nome di una mossa con colore di tipo.
    Click → emette il segnale clicked (ereditato da QPushButton).
    """
    def __init__(self, move_name: str = "", move_type: str = "", parent=None):
        super().__init__(parent)
        self._move_name = move_name
        self._move_type = move_type
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.update_display(move_name, move_type)

    def update_display(self, move_name: str, move_type: str = ""):
        self._move_name = move_name
        self._move_type = move_type
        display = move_name if move_name else "—"
        self.setText(display)
        self.setToolTip(f"{move_name} ({move_type})" if move_type else move_name)

        bg_color = TYPE_COLORS.get(move_type, Palette.BG_CARD)
        text_color = "#FFFFFF" if move_type else Palette.TEXT_MUTED

        self.setStyleSheet(
            f"QPushButton {{ background-color: {bg_color}; color: {text_color}; "
            f"border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: bold; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; text-align: center; }}"
            f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; opacity: 0.9; }}"
        )

    @property
    def move_name(self) -> str:
        return self._move_name

    @property
    def move_type(self) -> str:
        return self._move_type


class _MoveRow(QFrame):
    """Singola riga nella lista mosse del popup."""
    clicked = Signal(dict)

    def __init__(self, move_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._data = move_data
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)

        self.setStyleSheet(
            f"QFrame {{ background-color: {Palette.BG_CARD}; border-radius: 6px; "
            f"border: 1px solid {Palette.BORDER_COLOR}; }}"
            f"QFrame:hover {{ border-color: {Palette.PRIMARY}; background-color: {Palette.BG_SURFACE_ELEVATED}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Nome mossa
        name_lbl = QLabel(move_data.get("name", "?"))
        name_lbl.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; border: none;"
        )
        layout.addWidget(name_lbl)

        layout.addStretch()

        # Potenza base (se presente)
        bp = move_data.get("basePower", 0)
        if bp and bp > 0:
            bp_lbl = QLabel(f"BP {bp}")
            bp_lbl.setStyleSheet(
                f"color: {Palette.TEXT_MUTED}; font-size: 10px; border: none;"
            )
            layout.addWidget(bp_lbl)

        # Categoria icon
        cat = move_data.get("category", "")
        cat_icon = CATEGORY_ICONS.get(cat, "")
        if cat_icon:
            cat_lbl = QLabel(cat_icon)
            cat_lbl.setStyleSheet(f"font-size: 13px; border: none;")
            cat_lbl.setToolTip(cat)
            layout.addWidget(cat_lbl)

        # Type badge
        move_type = move_data.get("type", "")
        if move_type:
            type_badge = QLabel(move_type)
            bg = TYPE_COLORS.get(move_type, Palette.BG_SURFACE)
            type_badge.setStyleSheet(
                f"background-color: {bg}; color: #FFFFFF; "
                f"border-radius: 8px; padding: 2px 8px; font-size: 10px; "
                f"font-weight: bold; border: none;"
            )
            type_badge.setFixedHeight(20)
            layout.addWidget(type_badge)

    def mousePressEvent(self, event):
        self.clicked.emit(self._data)
        super().mousePressEvent(event)


class MoveSelectorPopup(QDialog):
    """
    Dialog modale per selezionare una mossa dal move pool legale.
    Mostra una lista filtrata con search, type badge e category icon.
    """
    move_selected = Signal(dict)  # Emesso con il dict della mossa selezionata

    def __init__(
        self,
        pokemon_name: str,
        slot_index: int,
        legal_moves: List[Dict[str, Any]],
        current_move: str = "",
        parent=None
    ):
        super().__init__(parent)
        self._legal_moves = legal_moves
        self._selected: Optional[Dict] = None

        self.setWindowTitle(f"Mosse di {pokemon_name}")
        self.setMinimumSize(340, 480)
        self.setMaximumSize(400, 600)
        self.setStyleSheet(
            f"QDialog {{ background-color: {Palette.BG_SURFACE}; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Titolo
        title = QLabel(f"Modifica Mossa: {pokemon_name}")
        title.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(title)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca mossa...")
        self.search_input.setStyleSheet(
            f"QLineEdit {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 8px; "
            f"padding: 8px 12px; font-size: 12px; }}"
            f"QLineEdit:focus {{ border-color: {Palette.PRIMARY}; }}"
        )
        self.search_input.textChanged.connect(self._filter_moves)
        layout.addWidget(self.search_input)

        # Label sezione
        section_lbl = QLabel("MOSSA")
        section_lbl.setStyleSheet(
            f"color: {Palette.TEXT_MUTED}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(section_lbl)

        # Scroll area per le mosse
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
            f"QScrollBar:vertical {{ background: {Palette.BG_SURFACE}; width: 6px; border: none; }}"
            f"QScrollBar::handle:vertical {{ background: {Palette.TERTIARY}; border-radius: 3px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}"
        )

        self.moves_container = QWidget()
        self.moves_layout = QVBoxLayout(self.moves_container)
        self.moves_layout.setContentsMargins(0, 0, 0, 0)
        self.moves_layout.setSpacing(3)

        self.scroll_area.setWidget(self.moves_container)
        layout.addWidget(self.scroll_area, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_confirm = QPushButton("Conferma")
        btn_confirm.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; "
            f"border-radius: 8px; padding: 8px 20px; font-weight: bold; font-size: 12px; "
            f"border: none; }}"
            f"QPushButton:hover {{ background-color: {Palette.PRIMARY_BRIGHT}; }}"
        )
        btn_confirm.clicked.connect(self._on_confirm)

        btn_cancel = QPushButton("Annulla")
        btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border-radius: 8px; padding: 8px 20px; font-size: 12px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
            f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; }}"
        )
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_confirm)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        # Popola
        self._populate_moves(legal_moves)

    def _populate_moves(self, moves: List[Dict[str, Any]]):
        """Riempie la lista mosse."""
        # Pulisci
        while self.moves_layout.count():
            item = self.moves_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for move_data in moves:
            row = _MoveRow(move_data)
            row.clicked.connect(self._on_move_clicked)
            self.moves_layout.addWidget(row)

        self.moves_layout.addStretch()

    def _filter_moves(self, text: str):
        """Filtra le mosse in base al testo di ricerca."""
        search = text.strip().lower()
        filtered = [
            m for m in self._legal_moves
            if search in m.get("name", "").lower() or search in m.get("type", "").lower()
        ] if search else self._legal_moves
        self._populate_moves(filtered)

    def _on_move_clicked(self, move_data: Dict):
        self._selected = move_data
        self.move_selected.emit(move_data)
        self.accept()

    def _on_confirm(self):
        if self._selected:
            self.move_selected.emit(self._selected)
        self.accept()
