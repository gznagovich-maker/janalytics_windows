"""
gsheet_import_view.py
=====================
Vista PySide6 per l'importazione di team VGC dal Google Spreadsheet VGCPastes.

Layout:
  1. Header sezione (52px, bronzo, Hisui Goodra palette)
  2. Barra configurazione: lista fogli (checkbox), selettore formato, pulsanti
  3. Progress bar + messaggio
  4. Area risultati scrollabile con card per ogni team importato

Segue il design system definito in config/theme.py e i pattern
architetturali del codebase (MVVM / Signal-Slot / QThread worker).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QScrollArea, QFrame, QGridLayout,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QDesktopServices, QCursor
from config.theme import Palette, Fonts, Spacing

from src.domain.gsheet_import_service import (
    fetch_sheet_names, SheetInfo, ImportedTeam, TeamMemberBuild,
    SPREADSHEET_ID,
)
from src.domain.gsheet_import_worker import GSheetImportWorker
from src.domain.role_detector import get_role_icon, get_role_color


# ── Costanti stilistiche ─────────────────────────────────────────

_CARD_STYLE = f"""
    QFrame#teamCard {{
        background-color: {Palette.BG_SURFACE_ELEVATED};
        border: 1px solid {Palette.BORDER_LIGHT};
        border-radius: 8px;
    }}
"""

_POKEMON_SLOT_STYLE = f"""
    QFrame#pokemonSlot {{
        background-color: {Palette.BG_CARD};
        border: 1px solid {Palette.BORDER_COLOR};
        border-radius: 6px;
    }}
"""

_LINK_STYLE = f"""
    QLabel#pasteLink {{
        color: {Palette.SECONDARY};
        font-size: {Fonts.SIZE_SMALL};
    }}
    QLabel#pasteLink:hover {{
        color: {Palette.SECONDARY_DIM};
        text-decoration: underline;
    }}
"""


# ── Widget principale ────────────────────────────────────────────

class GSheetImportWidget(QWidget):
    """Vista per importare team dal Google Spreadsheet VGCPastes."""

    def __init__(self, parent_main=None):
        super().__init__()
        self.parent_main = parent_main
        self._worker = None
        self._imported_teams = []

        self._build_ui()

    def get_imported_teams(self):
        """Restituisce la lista di team importati, per uso da altre viste."""
        return list(self._imported_teams)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # ── 1. Header ────────────────────────────────────────────
        header = QLabel("VGCPastes Import")
        header.setFixedHeight(52)
        header.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {Palette.PRIMARY};"
            "margin: 0; padding: 0; background: transparent; border: none;"
            "letter-spacing: 0.4px;"
            f"font-family: {Fonts.FAMILY_UI};"
        )
        header.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        root.addWidget(header)

        # ── 2. Configurazione (splitter: fogli a sinistra, opzioni a destra)
        config_layout = QHBoxLayout()
        config_layout.setSpacing(Spacing.MD)

        # Lista fogli con checkbox
        sheets_frame = QVBoxLayout()
        sheets_header = QLabel("Seleziona Fogli")
        sheets_header.setStyleSheet(
            f"font-size: {Fonts.SIZE_MEDIUM}; font-weight: 600;"
            f"color: {Palette.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        sheets_frame.addWidget(sheets_header)

        self.sheets_list = QListWidget()
        self.sheets_list.setStyleSheet(
            f"QListWidget {{ background-color: {Palette.BG_SURFACE};"
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px;"
            f"color: {Palette.TEXT_PRIMARY}; font-size: {Fonts.SIZE_BASE};"
            f"padding: 4px; }}"
            f"QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}"
            f"QListWidget::item:hover {{ background-color: {Palette.BG_SURFACE_ELEVATED}; }}"
            f"QListWidget::item:selected {{ background-color: {Palette.PRIMARY_DIM}; }}"
        )
        self.sheets_list.setMinimumHeight(150)
        self.sheets_list.setMaximumHeight(250)
        sheets_frame.addWidget(self.sheets_list)

        btn_row = QHBoxLayout()
        self.btn_load_sheets = QPushButton("Carica Fogli")
        self.btn_load_sheets.setStyleSheet(self._button_style())
        self.btn_load_sheets.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_load_sheets.clicked.connect(self._on_load_sheets)
        btn_row.addWidget(self.btn_load_sheets)

        self.btn_select_all = QPushButton("Seleziona Tutti")
        self.btn_select_all.setStyleSheet(self._button_style(secondary=True))
        self.btn_select_all.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_select_all.clicked.connect(self._on_select_all)
        btn_row.addWidget(self.btn_select_all)
        sheets_frame.addLayout(btn_row)

        config_layout.addLayout(sheets_frame, stretch=3)

        # Opzioni (formato + azione)
        options_frame = QVBoxLayout()
        options_frame.setSpacing(Spacing.SM)

        fmt_label = QLabel("Formato di Gioco")
        fmt_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_MEDIUM}; font-weight: 600;"
            f"color: {Palette.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        options_frame.addWidget(fmt_label)

        self.combo_format = QComboBox()
        self.combo_format.addItems(["Champions", "Normale"])
        self.combo_format.setStyleSheet(
            f"QComboBox {{ background-color: {Palette.BG_SURFACE};"
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px;"
            f"color: {Palette.TEXT_PRIMARY}; padding: 8px 12px;"
            f"font-size: {Fonts.SIZE_BASE}; min-height: 20px; }}"
            f"QComboBox::drop-down {{ border: none; width: 24px; }}"
            f"QComboBox QAbstractItemView {{ background-color: {Palette.BG_CARD};"
            f"border: 1px solid {Palette.BORDER_LIGHT};"
            f"color: {Palette.TEXT_PRIMARY}; selection-background-color: {Palette.PRIMARY_DIM}; }}"
        )
        options_frame.addWidget(self.combo_format)

        options_frame.addSpacing(Spacing.MD)

        self.btn_import = QPushButton("⬇  Importa Team")
        self.btn_import.setStyleSheet(self._button_style(primary=True))
        self.btn_import.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_import.setMinimumHeight(44)
        self.btn_import.clicked.connect(self._on_import)
        options_frame.addWidget(self.btn_import)

        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.setStyleSheet(self._button_style(danger=True))
        self.btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        options_frame.addWidget(self.btn_cancel)

        options_frame.addStretch()
        config_layout.addLayout(options_frame, stretch=2)

        root.addLayout(config_layout)

        # ── 3. Progress ──────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: {Palette.BG_SURFACE};"
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 4px;"
            f"text-align: center; color: {Palette.TEXT_MUTED};"
            f"font-size: {Fonts.SIZE_SMALL}; height: 22px; }}"
            f"QProgressBar::chunk {{ background-color: {Palette.PRIMARY};"
            f"border-radius: 3px; }}"
        )
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(
            f"font-size: {Fonts.SIZE_SMALL}; color: {Palette.TEXT_MUTED};"
            "background: transparent; border: none;"
        )
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        # ── 4. Risultati (scrollabile) ────────────────────────────
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {Palette.BG_APP};"
            f"border: none; }}"
            f"QScrollBar:vertical {{ background: {Palette.BG_SURFACE};"
            f"width: 8px; border-radius: 4px; }}"
            f"QScrollBar::handle:vertical {{ background: {Palette.TERTIARY};"
            f"border-radius: 4px; min-height: 20px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(Spacing.MD)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.results_scroll.setWidget(self.results_container)

        root.addWidget(self.results_scroll, stretch=1)

    # ── Stili bottoni ────────────────────────────────────────────

    def _button_style(
        self, primary=False, secondary=False, danger=False
    ) -> str:
        if primary:
            bg = Palette.PRIMARY_DIM
            bg_hover = Palette.PRIMARY
            fg = Palette.TEXT_PRIMARY
        elif danger:
            bg = Palette.DANGER
            bg_hover = Palette.DANGER_BRIGHT
            fg = Palette.TEXT_PRIMARY
        elif secondary:
            bg = Palette.BG_SURFACE_ELEVATED
            bg_hover = Palette.BG_CARD
            fg = Palette.TEXT_PRIMARY
        else:
            bg = Palette.BG_SURFACE
            bg_hover = Palette.BG_SURFACE_ELEVATED
            fg = Palette.TEXT_PRIMARY

        return (
            f"QPushButton {{ background-color: {bg}; color: {fg};"
            f"border: 1px solid {Palette.BORDER_LIGHT}; border-radius: 6px;"
            f"padding: 8px 16px; font-size: {Fonts.SIZE_BASE};"
            f"font-weight: 500; }}"
            f"QPushButton:hover {{ background-color: {bg_hover}; }}"
            f"QPushButton:pressed {{ background-color: {Palette.PRIMARY_DIM}; }}"
            f"QPushButton:disabled {{ background-color: {Palette.BG_SURFACE};"
            f"color: {Palette.TEXT_MUTED}; }}"
        )

    # ── Handlers ─────────────────────────────────────────────────

    def _on_load_sheets(self):
        """Scarica e mostra la lista dei fogli del documento."""
        self.sheets_list.clear()
        self.lbl_status.setText("Caricamento fogli in corso...")
        self.btn_load_sheets.setEnabled(False)

        try:
            sheets = fetch_sheet_names(SPREADSHEET_ID)

            for sheet in sheets:
                item = QListWidgetItem(sheet.name)
                item.setFlags(
                    item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, sheet)
                self.sheets_list.addItem(item)

            self.lbl_status.setText(
                f"{len(sheets)} fogli trovati. Seleziona quelli da importare."
            )

        except Exception as e:
            self.lbl_status.setText(f"Errore: {e}")
            QMessageBox.critical(
                self, "Errore",
                f"Impossibile caricare la lista dei fogli:\n{e}"
            )
        finally:
            self.btn_load_sheets.setEnabled(True)

    def _on_select_all(self):
        """Seleziona/deseleziona tutti i fogli."""
        all_checked = all(
            self.sheets_list.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self.sheets_list.count())
        )
        new_state = (
            Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        )
        for i in range(self.sheets_list.count()):
            self.sheets_list.item(i).setCheckState(new_state)

    def _get_selected_sheets(self) -> list:
        """Restituisce la lista di SheetInfo selezionati."""
        selected = []
        for i in range(self.sheets_list.count()):
            item = self.sheets_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                sheet_info = item.data(Qt.ItemDataRole.UserRole)
                if sheet_info:
                    selected.append(sheet_info)
        return selected

    def _on_import(self):
        """Avvia il worker di importazione."""
        selected = self._get_selected_sheets()
        if not selected:
            QMessageBox.warning(
                self, "Attenzione",
                "Seleziona almeno un foglio prima di importare."
            )
            return

        format_mode = self.combo_format.currentText()

        # Pulisci risultati precedenti
        self._clear_results()

        # UI state → in progress
        self.btn_import.setEnabled(False)
        self.btn_load_sheets.setEnabled(False)
        self.sheets_list.setEnabled(False)
        self.combo_format.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        # Avvia il worker
        self._worker = GSheetImportWorker(selected, format_mode)
        self._worker.progress.connect(self._on_progress)
        self._worker.team_ready.connect(self._on_team_ready)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_cancel(self):
        """Annulla il worker in corso."""
        if self._worker:
            self._worker.cancel()
        self._restore_ui()
        self.lbl_status.setText("Importazione annullata.")

    def _on_progress(self, current: int, total: int, message: str):
        """Aggiorna progress bar e messaggio."""
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.lbl_status.setText(message)

    def _on_team_ready(self, team):
        """Aggiunge una card per il team appena processato."""
        self._imported_teams.append(team)
        card = self._build_team_card(team)
        self.results_layout.addWidget(card)

    def _on_finished(self, all_teams):
        """Handler di completamento."""
        self._restore_ui()
        count = len(all_teams)
        self.lbl_status.setText(
            f"✓ Importazione completata: {count} team caricati."
        )

    def _on_error(self, error_msg: str):
        """Handler di errore fatale."""
        self._restore_ui()
        self.lbl_status.setText(f"✗ Errore: {error_msg}")
        QMessageBox.critical(
            self, "Errore",
            f"Errore durante l'importazione:\n{error_msg}"
        )

    def _restore_ui(self):
        """Ripristina lo stato della UI dopo import/cancel/error."""
        self.btn_import.setEnabled(True)
        self.btn_load_sheets.setEnabled(True)
        self.sheets_list.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.btn_cancel.setVisible(False)

    def _clear_results(self):
        """Rimuove tutte le card dalla sezione risultati."""
        self._imported_teams.clear()
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    # ── Rendering card team ──────────────────────────────────────

    def _build_team_card(self, team: ImportedTeam) -> QFrame:
        """Crea una card visuale per un team importato."""
        card = QFrame()
        card.setObjectName("teamCard")
        card.setStyleSheet(_CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.SM)

        # Header: nome team + badge foglio
        header_row = QHBoxLayout()

        team_name = QLabel(team.team_name)
        team_name.setStyleSheet(
            f"font-size: {Fonts.SIZE_LARGE}; font-weight: 600;"
            f"color: {Palette.PRIMARY}; background: transparent; border: none;"
        )
        header_row.addWidget(team_name)

        header_row.addStretch()

        sheet_badge = QLabel(f"📋 {team.source_sheet}")
        sheet_badge.setStyleSheet(
            f"font-size: {Fonts.SIZE_XS}; color: {Palette.TEXT_MUTED};"
            f"background-color: {Palette.BG_SURFACE};"
            f"border-radius: 4px; padding: 2px 8px; border: none;"
        )
        header_row.addWidget(sheet_badge)

        evs_badge_text = "EVs: Paste" if team.has_evs else "EVs: Auto"
        evs_badge_color = Palette.SUCCESS if team.has_evs else Palette.WARNING
        evs_badge = QLabel(evs_badge_text)
        evs_badge.setStyleSheet(
            f"font-size: {Fonts.SIZE_XS}; color: {Palette.TEXT_PRIMARY};"
            f"background-color: {evs_badge_color};"
            f"border-radius: 4px; padding: 2px 8px; border: none;"
        )
        header_row.addWidget(evs_badge)

        layout.addLayout(header_row)

        # Griglia Pokémon (3 colonne x 2 righe per 6 Pokémon)
        pokemon_grid = QGridLayout()
        pokemon_grid.setSpacing(Spacing.SM)

        for idx, member in enumerate(team.members[:6]):
            row = idx // 3
            col = idx % 3
            slot = self._build_pokemon_slot(member)
            pokemon_grid.addWidget(slot, row, col)

        layout.addLayout(pokemon_grid)

        # Footer: link al Pokepaste
        footer = QHBoxLayout()
        paste_link = QLabel(
            f"<a href='{team.pokepaste_url}'"
            f" style='color: {Palette.SECONDARY};"
            f" text-decoration: none;'>🔗 Apri Pokepaste</a>"
        )
        paste_link.setOpenExternalLinks(True)
        paste_link.setStyleSheet(
            f"font-size: {Fonts.SIZE_SMALL}; background: transparent; border: none;"
        )
        paste_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        footer.addWidget(paste_link)
        footer.addStretch()
        layout.addLayout(footer)

        return card

    def _build_pokemon_slot(self, member: TeamMemberBuild) -> QFrame:
        """Crea il riquadro visuale per un singolo Pokémon."""
        slot = QFrame()
        slot.setObjectName("pokemonSlot")
        slot.setStyleSheet(_POKEMON_SLOT_STYLE)
        slot.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout = QVBoxLayout(slot)
        layout.setContentsMargins(
            Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM
        )
        layout.setSpacing(2)

        # Riga 1: Nome specie + icona ruolo
        name_row = QHBoxLayout()
        species_label = QLabel(member.species)
        species_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_MEDIUM}; font-weight: 600;"
            f"color: {Palette.TEXT_PRIMARY}; background: transparent; border: none;"
        )
        name_row.addWidget(species_label)

        role_icon = get_role_icon(member.role)
        role_color = get_role_color(member.role)
        role_label = QLabel(f"{role_icon} {member.role}")
        role_label.setStyleSheet(
            f"font-size: {Fonts.SIZE_XS}; color: {Palette.TEXT_PRIMARY};"
            f"background-color: {role_color}; border-radius: 3px;"
            f"padding: 1px 6px; border: none;"
        )
        name_row.addStretch()
        name_row.addWidget(role_label)
        layout.addLayout(name_row)

        # Riga 2: Item + Ability
        meta_text = []
        if member.item:
            meta_text.append(f"📦 {member.item}")
        if member.ability:
            meta_text.append(f"✧ {member.ability}")
        if meta_text:
            meta_label = QLabel("  |  ".join(meta_text))
            meta_label.setStyleSheet(
                f"font-size: {Fonts.SIZE_XS}; color: {Palette.TEXT_MUTED};"
                "background: transparent; border: none;"
            )
            layout.addWidget(meta_label)

        # Riga 3: Natura + Tera Type
        nature_tera = []
        if member.nature:
            nature_tera.append(f"🌿 {member.nature}")
        if member.tera_type:
            nature_tera.append(f"💎 {member.tera_type}")
        if nature_tera:
            nt_label = QLabel("  |  ".join(nature_tera))
            nt_label.setStyleSheet(
                f"font-size: {Fonts.SIZE_XS}; color: {Palette.TEXT_MUTED};"
                "background: transparent; border: none;"
            )
            layout.addWidget(nt_label)

        # Riga 4: EVs (verde se paste, arancio/bronzo se auto)
        if member.evs:
            evs_parts = [
                f"{v} {k}" for k, v in member.evs.items() if v > 0
            ]
            evs_text = " / ".join(evs_parts)

            if member.evs_source == "paste":
                ev_color = Palette.SUCCESS
                ev_prefix = "📊"
            else:
                ev_color = Palette.WARNING
                ev_prefix = "⚙"

            evs_label = QLabel(f"{ev_prefix} {evs_text}")
            evs_label.setStyleSheet(
                f"font-size: {Fonts.SIZE_XS}; color: {ev_color};"
                f"font-family: {Fonts.FAMILY_DATA};"
                "background: transparent; border: none;"
            )
            layout.addWidget(evs_label)

        # Riga 5: Mosse
        for move in member.moves[:4]:
            move_label = QLabel(f"  – {move}")
            move_label.setStyleSheet(
                f"font-size: {Fonts.SIZE_XS}; color: {Palette.TERTIARY_LIGHT};"
                "background: transparent; border: none;"
            )
            layout.addWidget(move_label)

        return slot
