import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt
from config.theme import Palette
from database.connection import SessionLocal
from database.models_v2 import PokemonSpeciesV2, MoveV2, AbilityV2, ItemV2
from src.domain.exceptions import EntityNotFoundError
from src.domain.type_chart import TYPE_DATA

class EntityResolutionDialog(QDialog):
    def __init__(self, error: EntityNotFoundError, parent=None):
        super().__init__(parent)
        self.error = error
        self.selected_name = None
        
        self.setWindowTitle("Risoluzione Entità Mancante")
        self.setMinimumSize(600, 400)
        self.setStyleSheet(f"background-color: {Palette.BG_SURFACE_ELEVATED}; color: {Palette.TEXT_PRIMARY};")
        
        layout = QVBoxLayout(self)
        
        # Header Info
        info_lbl = QLabel(f"<b>Attenzione:</b> Il termine <b>'{error.raw_name}'</b> ({error.entity_type}) per il Pokémon '{error.context_pokemon}' non è stato riconosciuto.")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(info_lbl)
        
        # Search & Filters
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca nel database...")
        self.search_input.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; border: 1px solid {Palette.BORDER_COLOR}; border-radius: 4px; padding: 6px;")
        self.search_input.textChanged.connect(self._perform_search)
        search_layout.addWidget(self.search_input)
        
        self.type_filter = None
        self.cat_filter = None
        
        if error.entity_type == 'move':
            self.type_filter = QComboBox()
            self.type_filter.addItem("Tutti i Tipi")
            self.type_filter.addItems(list(TYPE_DATA.keys()))
            self.type_filter.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; padding: 4px;")
            self.type_filter.currentIndexChanged.connect(self._perform_search)
            search_layout.addWidget(self.type_filter)
            
            self.cat_filter = QComboBox()
            self.cat_filter.addItems(["Tutte le Categorie", "Physical", "Special", "Status"])
            self.cat_filter.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; padding: 4px;")
            self.cat_filter.currentIndexChanged.connect(self._perform_search)
            search_layout.addWidget(self.cat_filter)
            
        layout.addLayout(search_layout)
        
        # Results Table
        self.table = QTableWidget()
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {Palette.BG_SURFACE}; border: 1px solid {Palette.BORDER_COLOR}; }}"
            f"QHeaderView::section {{ background-color: {Palette.BG_APP}; font-weight: bold; }}"
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.accept)
        layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; border: 1px solid {Palette.BORDER_COLOR}; padding: 8px 16px; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_ok = QPushButton("Conferma Selezione")
        btn_ok.setStyleSheet(f"background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_ok.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)
        
        # Initial Search
        self._perform_search()
        
    def _perform_search(self):
        query = self.search_input.text().strip().lower()
        
        with SessionLocal() as session:
            if self.error.entity_type == 'move':
                q = session.query(MoveV2)
                if query:
                    q = q.filter(MoveV2.name.ilike(f"%{query}%"))
                if self.type_filter.currentIndex() > 0:
                    q = q.filter(MoveV2.type == self.type_filter.currentText())
                if self.cat_filter.currentIndex() > 0:
                    q = q.filter(MoveV2.category == self.cat_filter.currentText())
                
                results = q.limit(50).all()
                self._populate_move_table(results)
                
            elif self.error.entity_type == 'species':
                q = session.query(PokemonSpeciesV2)
                if query:
                    q = q.filter(PokemonSpeciesV2.name.ilike(f"%{query}%"))
                results = q.limit(50).all()
                self._populate_species_table(results)
                
            elif self.error.entity_type == 'ability':
                q = session.query(AbilityV2)
                if query:
                    q = q.filter(AbilityV2.name.ilike(f"%{query}%"))
                results = q.limit(50).all()
                self._populate_generic_table(results)
                
            elif self.error.entity_type == 'item':
                q = session.query(ItemV2)
                if query:
                    q = q.filter(ItemV2.name.ilike(f"%{query}%"))
                results = q.limit(50).all()
                self._populate_generic_table(results)

    def _populate_move_table(self, moves):
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Nome", "Tipo", "Categoria", "Descrizione"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setRowCount(len(moves))
        for row, mv in enumerate(moves):
            self.table.setItem(row, 0, QTableWidgetItem(mv.name))
            self.table.setItem(row, 1, QTableWidgetItem(mv.type))
            self.table.setItem(row, 2, QTableWidgetItem(mv.category))
            self.table.setItem(row, 3, QTableWidgetItem(mv.short_desc or ""))

    def _populate_species_table(self, species_list):
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Nome", "Tipo 1", "Tipo 2"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setRowCount(len(species_list))
        for row, sp in enumerate(species_list):
            self.table.setItem(row, 0, QTableWidgetItem(sp.name))
            self.table.setItem(row, 1, QTableWidgetItem(sp.type1 or ""))
            self.table.setItem(row, 2, QTableWidgetItem(sp.type2 or ""))

    def _populate_generic_table(self, items):
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Nome", "Descrizione"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item.name))
            self.table.setItem(row, 1, QTableWidgetItem(item.short_desc or ""))

    def accept(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Attenzione", "Seleziona un'entità dalla lista.")
            return
            
        row = selected_items[0].row()
        self.selected_name = self.table.item(row, 0).text()
        super().accept()
