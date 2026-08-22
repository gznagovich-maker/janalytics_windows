from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QSplitter, QTextEdit, QMessageBox, QFrame, QTextBrowser
)
from PySide6.QtCore import Signal, Qt, QUrl
from database.repository import search_matches, get_match_details, delete_match, clear_all_matches
from views.base_view import BaseHeaderWidget
import json
import copy

class ReplayListWidget(BaseHeaderWidget):
    """Schermata 1: Lista dei replay con Ricerca per Nome e Filtri"""
    replay_selected = Signal(str)

    def __init__(self):
        super().__init__("Libreria Replay VGC")

        self.current_page = 1
        self.items_per_page = 20
        self.total_pages = 1

        # --- BARRA DI RICERCA E FILTRI ---
        filter_group = QGroupBox("Ricerca e Filtri")
        filter_layout = QHBoxLayout(filter_group)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Cerca per Nome/ID Match...")
        self.input_search.textChanged.connect(self.on_filter_changed)

        self.input_player = QLineEdit()
        self.input_player.setPlaceholderText("Filtra per Allenatore...")
        self.input_player.textChanged.connect(self.on_filter_changed)

        self.input_pokemon = QLineEdit()
        self.input_pokemon.setPlaceholderText("Filtra per Pokémon (es. Incineroar)...")
        self.input_pokemon.textChanged.connect(self.on_filter_changed)

        btn_clear = QPushButton("Reset Filtri")
        btn_clear.clicked.connect(self.reset_filters)

        filter_layout.addWidget(self.input_search)
        filter_layout.addWidget(self.input_player)
        filter_layout.addWidget(self.input_pokemon)
        filter_layout.addWidget(btn_clear)
        self.add_content(filter_group)

        # --- PULSANTI AZIONE MASSIVA ---
        mass_actions_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Seleziona/Deseleziona Tutti")
        self.btn_select_all.clicked.connect(self.select_all_replays)
        
        self.btn_delete_selected = QPushButton("Elimina Selezionati")
        self.btn_delete_selected.setStyleSheet("background-color: #e74c3c; color: white; border-bottom: 3px solid #c0392b;")
        self.btn_delete_selected.clicked.connect(self.delete_selected_replays)

        self.btn_clear_db = QPushButton("Pulisci DB")
        self.btn_clear_db.setStyleSheet("background-color: #8b0000; color: white; border-bottom: 3px solid #5a0000;")
        self.btn_clear_db.clicked.connect(self.clear_database)
        
        mass_actions_layout.addWidget(self.btn_select_all)
        mass_actions_layout.addWidget(self.btn_delete_selected)
        mass_actions_layout.addWidget(self.btn_clear_db)
        mass_actions_layout.addStretch()
        self.add_layout(mass_actions_layout)

        # --- TABELLA REPLAY ---
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "", "ID Match", "Giocatore 1", "Team P1", "Giocatore 2", "Team P2", "Azione", "Elimina"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.add_content(self.table)

        # --- PAGINAZIONE ---
        pagination_layout = QHBoxLayout()
        self.btn_prev = QPushButton("< Precedente")
        self.btn_prev.clicked.connect(self.prev_page)
        self.lbl_page = QLabel("Pagina 1 / 1")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.btn_next = QPushButton("Successiva >")
        self.btn_next.clicked.connect(self.next_page)
        
        pagination_layout.addWidget(self.btn_prev)
        pagination_layout.addWidget(self.lbl_page)
        pagination_layout.addWidget(self.btn_next)
        self.add_layout(pagination_layout)

        self.load_replays()

    def on_filter_changed(self):
        self.current_page = 1
        self.load_replays()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.load_replays()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_replays()

    def reset_filters(self):
        self.input_search.blockSignals(True)
        self.input_player.blockSignals(True)
        self.input_pokemon.blockSignals(True)
        
        self.input_search.clear()
        self.input_player.clear()
        self.input_pokemon.clear()
        
        self.input_search.blockSignals(False)
        self.input_player.blockSignals(False)
        self.input_pokemon.blockSignals(False)
        
        self.current_page = 1
        self.load_replays()

    def load_replays(self):
        query_text = self.input_search.text().strip()
        player_text = self.input_player.text().strip()
        pokemon_text = self.input_pokemon.text().strip()

        offset = (self.current_page - 1) * self.items_per_page
        matches, total_count = search_matches(query_text, player_text, pokemon_text, limit=self.items_per_page, offset=offset)
        
        import math
        self.total_pages = max(1, math.ceil(total_count / self.items_per_page))
        self.lbl_page.setText(f"Pagina {self.current_page} / {self.total_pages} ({total_count} totali)")
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)

        self.table.setRowCount(len(matches))

        for row, match in enumerate(matches):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, chk)
            
            self.table.setItem(row, 1, QTableWidgetItem(match["id"]))
            self.table.setItem(row, 2, QTableWidgetItem(match["p1"]))
            self.table.setItem(row, 3, QTableWidgetItem(match["p1_team"]))
            self.table.setItem(row, 4, QTableWidgetItem(match["p2"]))
            self.table.setItem(row, 5, QTableWidgetItem(match["p2_team"]))

            btn_view = QPushButton("Visualizza")
            btn_view.clicked.connect(lambda checked=False, m_id=match["id"]: self.replay_selected.emit(m_id))
            self.table.setCellWidget(row, 6, btn_view)

            btn_delete = QPushButton("Elimina")
            btn_delete.setStyleSheet("background-color: #e74c3c; color: white; border-bottom: 2px solid #c0392b;")
            btn_delete.clicked.connect(lambda checked=False, m_id=match["id"]: self.on_delete_match(m_id))
            self.table.setCellWidget(row, 7, btn_delete)

    def on_delete_match(self, match_id: str):
        reply = QMessageBox.question(
            self, "Conferma Eliminazione", 
            f"Sei sicuro di voler eliminare il replay '{match_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if delete_match(match_id):
                self.load_replays()
            else:
                QMessageBox.critical(self, "Errore", "Si è verificato un errore durante l'eliminazione.")

    def select_all_replays(self):
        all_checked = True
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Unchecked:
                all_checked = False
                break
                
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk:
                chk.setCheckState(new_state)

    def delete_selected_replays(self):
        selected_ids = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                m_id = self.table.item(row, 1).text()
                selected_ids.append(m_id)
        
        if not selected_ids:
            QMessageBox.warning(self, "Attenzione", "Nessun match selezionato.")
            return

        reply = QMessageBox.question(self, 'Conferma Eliminazione', 
                                     f"Sei sicuro di voler eliminare i {len(selected_ids)} match selezionati?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            success_count = 0
            for m_id in selected_ids:
                if delete_match(m_id):
                    success_count += 1
            
            QMessageBox.information(self, "Completato", f"Eliminati {success_count} su {len(selected_ids)} match.")
            self.load_replays()

    def clear_database(self):
        reply = QMessageBox.question(self, 'Conferma Pulizia', 
                                     "Sei sicuro di voler eliminare TUTTI i match dal database? Questa azione è irreversibile.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if clear_all_matches():
                QMessageBox.information(self, "Successo", "Database ripulito con successo.")
                self.current_page = 1
                self.load_replays()
            else:
                QMessageBox.critical(self, "Errore", "Si è verificato un errore durante la pulizia del database.")

