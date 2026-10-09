"""
ability_selector_popup.py
=========================
Widget popup per la selezione dell'abilità dal pool legale del Pokémon.
Include AbilityChip (chip cliccabile inline) e AbilitySelectorPopup (dialog modale).
"""

from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from config.theme import Palette


class AbilityChip(QPushButton):
    """
    Chip cliccabile che mostra il nome dell'abilità.
    Click → emette clicked (ereditato da QPushButton).
    """
    def __init__(self, ability_name: str = "", parent=None):
        super().__init__(parent)
        self._ability_name = ability_name
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.update_display(ability_name)

    def update_display(self, ability_name: str):
        self._ability_name = ability_name
        display = ability_name if ability_name else "— Seleziona Abilità —"
        self.setText(f"  {display}")
        self.setToolTip(f"Abilità: {ability_name}" if ability_name else "Clicca per selezionare")

        has_value = bool(ability_name)
        text_color = Palette.TEXT_PRIMARY if has_value else Palette.TEXT_MUTED
        self.setStyleSheet(
            f"QPushButton {{ background-color: transparent; color: {text_color}; "
            f"font-size: 11px; text-align: left; border: none; padding: 2px 4px; }}"
            f"QPushButton:hover {{ color: {Palette.PRIMARY}; }}"
        )

    @property
    def ability_name(self) -> str:
        return self._ability_name


class _AbilityCard(QFrame):
    """Singola card nella lista abilità del popup."""
    clicked = Signal(dict)

    def __init__(self, ability_data: Dict[str, str], is_selected: bool = False, parent=None):
        super().__init__(parent)
        self._data = ability_data
        self.setCursor(Qt.PointingHandCursor)

        border_color = Palette.PRIMARY if is_selected else Palette.BORDER_COLOR
        bg = Palette.BG_SURFACE_ELEVATED if is_selected else Palette.BG_CARD

        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 8px; "
            f"border: 1px solid {border_color}; }}"
            f"QFrame:hover {{ border-color: {Palette.PRIMARY}; "
            f"background-color: {Palette.BG_SURFACE_ELEVATED}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        # Header: icona + nome
        header = QHBoxLayout()
        icon_lbl = QLabel("◆")
        icon_lbl.setStyleSheet(
            f"color: {Palette.PRIMARY}; font-size: 14px; border: none;"
        )
        header.addWidget(icon_lbl)

        name_lbl = QLabel(ability_data.get("name", "?"))
        name_lbl.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 13px; font-weight: bold; border: none;"
        )
        header.addWidget(name_lbl)
        header.addStretch()

        if is_selected:
            sel_lbl = QLabel("✓")
            sel_lbl.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 14px; border: none;")
            header.addWidget(sel_lbl)

        layout.addLayout(header)

        # Descrizione
        desc = ability_data.get("desc", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(
                f"color: {Palette.TEXT_MUTED}; font-size: 11px; border: none; "
                f"padding-left: 20px;"
            )
            layout.addWidget(desc_lbl)

    def mousePressEvent(self, event):
        self.clicked.emit(self._data)
        super().mousePressEvent(event)


class AbilitySelectorPopup(QDialog):
    """
    Dialog modale per selezionare un'abilità dal pool legale.
    Mostra cards con nome e descrizione, click seleziona e chiude.
    """
    ability_selected = Signal(dict)

    def __init__(
        self,
        pokemon_name: str,
        legal_abilities: List[Dict[str, str]],
        current_ability: str = "",
        parent=None
    ):
        super().__init__(parent)
        self._selected: Optional[Dict] = None

        self.setWindowTitle(f"Abilità di {pokemon_name}")
        self.setMinimumSize(320, 200)
        self.setMaximumSize(400, 400)
        self.setStyleSheet(
            f"QDialog {{ background-color: {Palette.BG_SURFACE}; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Titolo
        title = QLabel(f"Abilità — {pokemon_name}")
        title.setStyleSheet(
            f"color: {Palette.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(title)

        # Label sezione
        section_lbl = QLabel("ABILITY")
        section_lbl.setStyleSheet(
            f"color: {Palette.TEXT_MUTED}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(section_lbl)

        # Cards abilità
        for ab_data in legal_abilities:
            is_sel = ab_data.get("name", "") == current_ability
            card = _AbilityCard(ab_data, is_selected=is_sel)
            card.clicked.connect(self._on_ability_clicked)
            layout.addWidget(card)

        layout.addStretch()

        # Bottom cancel
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_CARD}; color: {Palette.TEXT_PRIMARY}; "
            f"border-radius: 8px; padding: 8px 20px; font-size: 12px; "
            f"border: 1px solid {Palette.BORDER_LIGHT}; }}"
            f"QPushButton:hover {{ border-color: {Palette.PRIMARY}; }}"
        )
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel, alignment=Qt.AlignRight)

    def _on_ability_clicked(self, ab_data: Dict):
        self._selected = ab_data
        self.ability_selected.emit(ab_data)
        self.accept()
