from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QSplitter, QTextEdit
)
from PySide6.QtCore import Signal, Qt
from database.repository import search_matches, get_match_details


class ReplayListWidget(QWidget):
    """Schermata 1: Lista dei replay con Ricerca per Nome e Filtri"""
    replay_selected = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel("Libreria Replay VGC")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # --- BARRA DI RICERCA E FILTRI ---
        filter_group = QGroupBox("Ricerca e Filtri")
        filter_layout = QHBoxLayout(filter_group)

        self.input_search = QLineEdit()
        self.input_search.setPlaceholderText("Cerca per Nome/ID Match...")
        self.input_search.textChanged.connect(self.load_replays)

        self.input_player = QLineEdit()
        self.input_player.setPlaceholderText("Filtra per Allenatore...")
        self.input_player.textChanged.connect(self.load_replays)

        self.input_pokemon = QLineEdit()
        self.input_pokemon.setPlaceholderText("Filtra per Pokémon (es. Incineroar)...")
        self.input_pokemon.textChanged.connect(self.load_replays)

        btn_clear = QPushButton("Reset Filtri")
        btn_clear.clicked.connect(self.reset_filters)

        filter_layout.addWidget(self.input_search)
        filter_layout.addWidget(self.input_player)
        filter_layout.addWidget(self.input_pokemon)
        filter_layout.addWidget(btn_clear)
        layout.addWidget(filter_group)

        # --- TABELLA REPLAY ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID Match", "Giocatore 1", "Team P1", "Giocatore 2", "Team P2", "Azione"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.load_replays()

    def reset_filters(self):
        self.input_search.clear()
        self.input_player.clear()
        self.input_pokemon.clear()
        self.load_replays()

    def load_replays(self):
        query_text = self.input_search.text().strip()
        player_text = self.input_player.text().strip()
        pokemon_text = self.input_pokemon.text().strip()

        matches = search_matches(query_text, player_text, pokemon_text)
        self.table.setRowCount(len(matches))

        for row, match in enumerate(matches):
            self.table.setItem(row, 0, QTableWidgetItem(match["id"]))
            self.table.setItem(row, 1, QTableWidgetItem(match["p1"]))
            self.table.setItem(row, 2, QTableWidgetItem(match["p1_team"]))
            self.table.setItem(row, 3, QTableWidgetItem(match["p2"]))
            self.table.setItem(row, 4, QTableWidgetItem(match["p2_team"]))

            btn_view = QPushButton("Visualizza")
            btn_view.clicked.connect(lambda checked=False, m_id=match["id"]: self.replay_selected.emit(m_id))
            self.table.setCellWidget(row, 5, btn_view)


class ReplayDetailWidget(QWidget):
    """Schermata 2: Dettagli del match, Team dei Giocatori, Turni e Match State per azione"""
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        self.btn_back = QPushButton("← Torna alla Libreria")
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.title_label = QLabel("Seleziona un replay...")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        header_layout.addWidget(self.btn_back)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Visualizzazione Team Giocatori (P1 vs P2)
        teams_group = QGroupBox("Team dei Giocatori")
        teams_layout = QHBoxLayout(teams_group)

        self.lbl_p1_team = QLabel("Giocatore 1: -")
        self.lbl_p1_team.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_p2_team = QLabel("Giocatore 2: -")
        self.lbl_p2_team.setTextFormat(Qt.TextFormat.RichText)

        teams_layout.addWidget(self.lbl_p1_team)
        teams_layout.addWidget(self.lbl_p2_team)
        layout.addWidget(teams_group)

        # Splitter: Sinistra = Albero Turni/Azioni, Destra = Dettaglio Match State Azione Selezionata
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Albero Azioni
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Ordine / Evento", "Attore", "Bersaglio", "Dettagli"])
        self.tree.itemSelectionChanged.connect(self.on_action_selected)
        splitter.addWidget(self.tree)

        # Inspector Match State Azione
        inspector_group = QGroupBox("Match State & Attributi Azione")
        inspector_layout = QVBoxLayout(inspector_group)
        self.txt_state = QTextEdit()
        self.txt_state.setReadOnly(True)
        inspector_layout.addWidget(self.txt_state)
        splitter.addWidget(inspector_group)

        splitter.setSizes([550, 250])
        layout.addWidget(splitter)

    def display_match(self, match_id: str):
        self.title_label.setText(f"Replay: {match_id}")
        self.tree.clear()
        self.txt_state.clear()

        match_data = get_match_details(match_id)
        if not match_data:
            return

        # Renderizza i Team
        teams = match_data["teams"]
        if "p1" in teams:
            p1_html = f"<b>{teams['p1']['trainer']} (P1)</b><br>"
            for poke in teams['p1']['pokemon']:
                brought_tag = " <b>[In Campo]</b>" if poke["is_brought"] else ""
                p1_html += f"• {poke['species']} (Item: {poke['item']}, Tera: {poke['tera_type']}){brought_tag}<br>"
            self.lbl_p1_team.setText(p1_html)

        if "p2" in teams:
            p2_html = f"<b>{teams['p2']['trainer']} (P2)</b><br>"
            for poke in teams['p2']['pokemon']:
                brought_tag = " <b>[In Campo]</b>" if poke["is_brought"] else ""
                p2_html += f"• {poke['species']} (Item: {poke['item']}, Tera: {poke['tera_type']}){brought_tag}<br>"
            self.lbl_p2_team.setText(p2_html)

        # Renderizza Turni ed Azioni
        for turn in match_data["turns"]:
            conds = []
            if turn["trick_room"]: conds.append("Trick Room")
            if turn["p1_tailwind"]: conds.append("Tailwind P1")
            if turn["p2_tailwind"]: conds.append("Tailwind P2")
            if turn["weather"]: conds.append(f"Clima: {turn['weather']}")

            cond_str = f" [{', '.join(conds)}]" if conds else ""
            turn_node = QTreeWidgetItem(self.tree, [f"Turno {turn['turn_number']}{cond_str}", "", "", ""])
            turn_node.setExpanded(True)

            for act in turn["actions"]:
                action_item = QTreeWidgetItem(turn_node, [
                    f"#{act['order'] + 1} {act['type'].upper()}",
                    act["actor"],
                    act["target"],
                    act["details"]
                ])
                # Salviamo i dati completi nell'item per recuperarli al click
                action_item.setData(0, Qt.ItemDataRole.UserRole, act)

    def on_action_selected(self):
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        act = item.data(0, Qt.ItemDataRole.UserRole)

        if not act:
            self.txt_state.setText("<i>Seleziona una singola azione per vedere lo stato del campo.</i>")
            return

        state = act["board_state"]
        tags_str = str(act["tags"]) if act["tags"] else "Nessuno"

        html = f"""
        <h3>Azione: {act['type'].upper()}</h3>
        <b>Attore:</b> {act['actor']}<br>
        <b>Bersaglio:</b> {act['target']}<br>
        <b>Dettagli:</b> {act['details']}<br>
        <hr>
        <h4>Match State (Pokémon In Campo)</h4>
        <b>P1 Slot A:</b> {state['p1a']}<br>
        <b>P1 Slot B:</b> {state['p1b']}<br>
        <br>
        <b>P2 Slot A:</b> {state['p2a']}<br>
        <b>P2 Slot B:</b> {state['p2b']}<br>
        <hr>
        <h4>Event Tags (JSON)</h4>
        <pre>{tags_str}</pre>
        """
        self.txt_state.setHtml(html)
