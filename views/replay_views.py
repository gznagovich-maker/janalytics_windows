from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QTreeWidget, QTreeWidgetItem, QGroupBox, QSplitter, QTextEdit, QMessageBox, QFrame, QTextBrowser
)
from PySide6.QtCore import Signal, Qt, QUrl
from database.repository import search_matches, get_match_details, delete_match
from views.base_view import BaseHeaderWidget
import json
import copy

class PlayerTeamWidget(QGroupBox):
    def __init__(self, title, parent_main):
        super().__init__(title)
        self.parent_main = parent_main
        self.layout = QVBoxLayout(self)
        
        self.lbl_info = QLabel("Allenatore: - | Rating: -")
        self.lbl_info.setStyleSheet("font-size: 14px; font-weight: bold; color: #3498db;")
        self.layout.addWidget(self.lbl_info)
        
        self.pokemon_layout = QHBoxLayout()
        self.layout.addLayout(self.pokemon_layout)
        
    def populate(self, team_data):
        trainer = team_data.get("trainer", "Sconosciuto")
        rating = team_data.get("rating", "N/A")
        self.lbl_info.setText(f"Allenatore: {trainer}  |  Rating: {rating}")
        
        while self.pokemon_layout.count():
            child = self.pokemon_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        for poke in team_data.get("pokemon", []):
            btn = QPushButton(poke["species"])
            btn.setToolTip(f"Dettagli di {poke['species']}")
            if poke["is_brought"]:
                btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 6px;")
            else:
                btn.setStyleSheet("background-color: #555555; color: white; padding: 6px;")
            
            btn.clicked.connect(lambda checked=False, p=poke: self.parent_main.show_pokemon_details(p))
            self.pokemon_layout.addWidget(btn)


class ReplayListWidget(BaseHeaderWidget):
    """Schermata 1: Lista dei replay con Ricerca per Nome e Filtri"""
    replay_selected = Signal(str)

    def __init__(self):
        super().__init__("Libreria Replay VGC")

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
        self.add_content(filter_group)

        # --- PULSANTI AZIONE MASSIVA ---
        mass_actions_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Seleziona/Deseleziona Tutti")
        self.btn_select_all.clicked.connect(self.select_all_replays)
        self.btn_delete_selected = QPushButton("Elimina Selezionati")
        self.btn_delete_selected.setStyleSheet("background-color: #e74c3c; color: white;")
        self.btn_delete_selected.clicked.connect(self.delete_selected_replays)
        
        mass_actions_layout.addWidget(self.btn_select_all)
        mass_actions_layout.addWidget(self.btn_delete_selected)
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
            btn_delete.setStyleSheet("background-color: #e74c3c; color: white;")
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
                match_id = self.table.item(row, 1).text()
                selected_ids.append(match_id)
                
        if not selected_ids:
            QMessageBox.warning(self, "Attenzione", "Nessun replay selezionato.")
            return
            
        reply = QMessageBox.question(
            self, "Conferma Eliminazione Massiva", 
            f"Sei sicuro di voler eliminare i {len(selected_ids)} replay selezionati?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = 0
            for m_id in selected_ids:
                if delete_match(m_id):
                    success += 1
            QMessageBox.information(self, "Risultato Eliminazione", f"Eliminati {success} su {len(selected_ids)} replay.")
            self.load_replays()


class ReplayDetailWidget(BaseHeaderWidget):
    """Schermata 2: Dettagli del match, Team dei Giocatori, Turni e Match State per azione"""
    back_requested = Signal()
    link_clicked = Signal(str)

    def __init__(self):
        super().__init__("Dettaglio Replay")

        self.subtitle_label = QLabel("")
        self.subtitle_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #aaaaaa;")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.add_content(self.subtitle_label)

        # Visualizzazione Team Giocatori (P1 vs P2)
        teams_group = QGroupBox("Team dei Giocatori")
        teams_layout = QHBoxLayout(teams_group)

        self.p1_team_widget = PlayerTeamWidget("Giocatore 1 (Tu)", self)
        self.p2_team_widget = PlayerTeamWidget("Giocatore 2 (Avversario)", self)

        teams_layout.addWidget(self.p1_team_widget)
        teams_layout.addWidget(self.p2_team_widget)
        self.add_content(teams_group)

        # Pannello a scomparsa per i dettagli Pokemon
        self.pokemon_details_frame = QFrame()
        self.pokemon_details_frame.setStyleSheet("background-color: #222222; border-radius: 5px;")
        self.pokemon_details_frame.setVisible(False)
        details_layout = QVBoxLayout(self.pokemon_details_frame)
        self.lbl_pokemon_details = QLabel()
        self.lbl_pokemon_details.setWordWrap(True)
        self.lbl_pokemon_details.linkActivated.connect(self.link_clicked.emit)
        details_layout.addWidget(self.lbl_pokemon_details)
        self.add_content(self.pokemon_details_frame)

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
        
        # Area dedicata al campo (sempre visibile in alto a destra)
        self.lbl_board = QLabel("<i>Seleziona un'azione per vedere il campo</i>")
        self.lbl_board.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_board.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_board.setStyleSheet("background-color: #1a1a1a; padding: 10px; border-radius: 5px; border: 1px solid #444;")
        self.lbl_board.linkActivated.connect(self.on_board_link_clicked)
        
        self.txt_state = QTextBrowser()
        self.txt_state.setOpenExternalLinks(False)
        self.txt_state.anchorClicked.connect(self.on_txt_state_anchor_clicked)
        self.txt_state.setReadOnly(True)
        
        inspector_layout.addWidget(self.lbl_board)
        inspector_layout.addWidget(self.txt_state)
        splitter.addWidget(inspector_group)

        splitter.setSizes([550, 250])
        self.add_content(splitter)

    def on_txt_state_anchor_clicked(self, url: QUrl):
        self.link_clicked.emit(url.toString())

    def on_board_link_clicked(self, url: str):
        if url.startswith("boardpoke:"):
            try:
                b_id = int(url.split(":")[1])
                poke = getattr(self, 'build_map', {}).get(b_id)
                if poke:
                    self.show_pokemon_details(poke)
            except ValueError:
                pass

    def show_pokemon_details(self, poke):
        if self.pokemon_details_frame.isVisible() and poke.get('species') in self.lbl_pokemon_details.text():
            self.pokemon_details_frame.setVisible(False)
            return
            
        def make_link(tipo, nome):
            if not nome or nome == 'N/D': return nome
            return f'<a href="{tipo}:{nome}" style="color: #3498db; text-decoration: none;">{nome}</a>'

        moves_html = "<ul>"
        for m in poke.get('moves', []):
            moves_html += f"<li>{make_link('move', m)}</li>"
        moves_html += "</ul>" if poke.get('moves') else "<i>(Nessuna mossa rilevata)</i>"
        
        bs = poke.get('base_stats', {})
        if isinstance(bs, str):
            try:
                import json
                bs = json.loads(bs)
            except:
                bs = {}
        stats_html = f"HP: {bs.get('hp', '-')} | Atk: {bs.get('atk', '-')} | Def: {bs.get('def', '-')} | SpA: {bs.get('spa', '-')} | SpD: {bs.get('spd', '-')} | Spe: {bs.get('spe', '-')}" if bs else "<i>(Statistiche non disponibili)</i>"
        
        details = f"""
        <b>Specie:</b> {make_link('pokedex', poke.get('species', 'N/D'))}<br>
        <b>Abilità:</b> {make_link('ability', poke.get('ability', 'N/D'))}<br>
        <b>Strumento:</b> {make_link('item', poke.get('item', 'N/D'))}<br>
        <b>Teratipo:</b> {poke.get('tera_type', 'N/D')}<br>
        <b>Natura:</b> {poke.get('nature', 'N/D')}<br>
        <b>Base Stats:</b> <span style="color: #a0a0a0; font-size: 12px;">{stats_html}</span><br>
        <hr>
        <b>Mosse Conosciute:</b><br>
        {moves_html}
        """
        self.lbl_pokemon_details.setText(details)
        self.pokemon_details_frame.setVisible(True)

    def display_match(self, match_id: str):
        self.header_label.setText(match_id)
        self.subtitle_label.setText("")
        self.tree.clear()
        self.txt_state.clear()
        self.lbl_board.setText("<i>Seleziona un'azione per vedere il campo</i>")
        self.build_map = {}

        match_data = get_match_details(match_id)
        if not match_data:
            return
            
        fmt = match_data.get("format", "Regolamento Sconosciuto")
        self.subtitle_label.setText(f"Regolamentazione: {fmt}")

        # Renderizza i Team
        teams = match_data["teams"]
        if "p1" in teams:
            self.p1_team_widget.populate(teams["p1"])
            for poke in teams["p1"]["pokemon"]:
                self.build_map[poke["id"]] = poke

        if "p2" in teams:
            self.p2_team_widget.populate(teams["p2"])
            for poke in teams["p2"]["pokemon"]:
                self.build_map[poke["id"]] = poke

        self.current_hp = {}
        self.current_status = {}
        current_weather = None

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
                tags_dict = act.get("tags", {})
                if isinstance(tags_dict, str):
                    try:
                        tags_dict = json.loads(tags_dict)
                    except:
                        tags_dict = {}

                if "weather" in tags_dict:
                    for w_event in tags_dict["weather"]:
                        if len(w_event) > 0:
                            weather_val = w_event[0]
                            if weather_val != "none" and not weather_val.startswith("["):
                                current_weather = weather_val
                            elif weather_val == "none":
                                current_weather = None

                for dmg_key in ["damage", "heal"]:
                    if dmg_key in tags_dict:
                        for event in tags_dict[dmg_key]:
                            if len(event) >= 2:
                                slot_str = event[0].split(":")[0].strip()
                                hp_val = event[1]
                                b_id = act["board_state"].get(slot_str, {}).get("id")
                                if b_id:
                                    self.current_hp[b_id] = hp_val

                if "status" in tags_dict:
                    for event in tags_dict["status"]:
                        if len(event) >= 2:
                            slot_str = event[0].split(":")[0].strip()
                            st_val = event[1]
                            b_id = act["board_state"].get(slot_str, {}).get("id")
                            if b_id:
                                self.current_status[b_id] = st_val
                                
                if "curestatus" in tags_dict:
                    for event in tags_dict["curestatus"]:
                        if len(event) >= 1:
                            slot_str = event[0].split(":")[0].strip()
                            b_id = act["board_state"].get(slot_str, {}).get("id")
                            if b_id:
                                self.current_status[b_id] = ""

                if "faint" in tags_dict:
                    for event in tags_dict["faint"]:
                        if len(event) >= 1:
                            slot_str = event[0].split(":")[0].strip()
                            b_id = act["board_state"].get(slot_str, {}).get("id")
                            if b_id:
                                self.current_hp[b_id] = "0 fnt"
                                self.current_status[b_id] = ""

                act["simulated_state"] = {
                    "hp": copy.deepcopy(self.current_hp),
                    "status": copy.deepcopy(self.current_status),
                    "weather": current_weather
                }

                action_item = QTreeWidgetItem(turn_node, [
                    f"#{act['order'] + 1} {act['type'].upper()}",
                    act["actor"],
                    act["target"],
                    act["details"]
                ])
                # Salviamo i dati completi nell'item per recuperarli al click
                action_item.setData(0, Qt.ItemDataRole.UserRole, act)
                
        self.tree.setFocus()

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
        
        # Formattazione dei Tags ad albero
        tags_html = "<ul style='margin-top: 0px; margin-bottom: 0px; padding-left: 20px;'>"
        tags_dict = act.get("tags", {})
        if tags_dict:
            if isinstance(tags_dict, str):
                try:
                    tags_dict = json.loads(tags_dict)
                except:
                    pass
            if isinstance(tags_dict, dict):
                                tags_str += f"    -{item_list}\n"
            else:
                tags_str = str(tags_dict)
        if not tags_str.strip():
            tags_str = "Nessuno"

        sim_state = act.get("simulated_state", {"hp": {}, "status": {}, "weather": None})

        def format_board_slot(slot_data, sim):
            if not slot_data: return "<i>(Vuoto)</i>"
            name = slot_data.get("name", "Vuoto")
            if name == "Vuoto": return "<i>(Vuoto)</i>"
            b_id = slot_data.get("id")
            
            hp_val = sim["hp"].get(b_id, "100/100")
            st_val = sim["status"].get(b_id, "")
            
            hp_pct = 100
            try:
                if hp_val.startswith("0 fnt") or "fnt" in hp_val:
                    hp_pct = 0
                else:
                    parts = hp_val.split()[0].split('/')
                    if len(parts) == 2:
                        hp_pct = int(float(parts[0]) / float(parts[1]) * 100)
            except:
                pass
                
            color = "#00ff00"
            if hp_pct < 50: color = "#ffff00"
            if hp_pct < 20: color = "#ff0000"
            if hp_pct == 0: color = "#555555"
            
            st_badge = f'<span style="background-color:#9900cc; padding: 1px 4px; border-radius: 3px; font-size:10px; font-weight:bold; color:white;">{st_val.upper()}</span>' if st_val else ''
            
            link = f'<a href="boardpoke:{b_id}" style="color: inherit; text-decoration: none;">{name}</a>'
            bar = f'<div style="width:100%; height:6px; background-color:#333; margin-top:4px;"><div style="width:{hp_pct}%; height:100%; background-color:{color};"></div></div>'
            info = f'<div style="font-size:11px; margin-top:2px; color:#cccccc;">{hp_val} {st_badge}</div>'
            
            return f"{link}{bar}{info}"

        p1a_display = format_board_slot(state.get('p1a'), sim_state)
        p1b_display = format_board_slot(state.get('p1b'), sim_state)
        p2a_display = format_board_slot(state.get('p2a'), sim_state)
        p2b_display = format_board_slot(state.get('p2b'), sim_state)

        weather = sim_state.get("weather")
        bg_colors = {
            "SunnyDay": "#661100", 
            "RainDance": "#002266", 
            "Snow": "#225577", 
            "Sandstorm": "#443311" 
        }
        board_bg = bg_colors.get(weather, "#2A2A2A")

        # Scheda visiva del Campo ad Alto Contrasto
        board_html = f"""
        <table width="100%" border="0" cellspacing="4" cellpadding="10" style="text-align: center; font-size: 14px; color: #ffffff; background-color: {board_bg}; border-radius: 5px;">
            <tr>
                <td colspan="2" style="background-color: #8B0000; font-weight: bold; padding: 5px;">Lato Avversario (Giocatore 2)</td>
            </tr>
            <tr>
                <td width="50%" style="background-color: #4A1515; border: 2px solid #FF4444; border-radius: 4px;">
                    <span style="font-size:16px; font-weight:bold; color:#FFCCCC;">{p2b_display}</span><br><span style="color:#AAAAAA; font-size:11px;">Slot B</span>
                </td>
                <td width="50%" style="background-color: #4A1515; border: 2px solid #FF4444; border-radius: 4px;">
                    <span style="font-size:16px; font-weight:bold; color:#FFCCCC;">{p2a_display}</span><br><span style="color:#AAAAAA; font-size:11px;">Slot A</span>
                </td>
            </tr>
            <tr>
                <td width="50%" style="background-color: #194A24; border: 2px solid #44FF44; border-radius: 4px;">
                    <span style="font-size:16px; font-weight:bold; color:#CCFFCC;">{p1a_display}</span><br><span style="color:#AAAAAA; font-size:11px;">Slot A</span>
                </td>
                <td width="50%" style="background-color: #194A24; border: 2px solid #44FF44; border-radius: 4px;">
                    <span style="font-size:16px; font-weight:bold; color:#CCFFCC;">{p1b_display}</span><br><span style="color:#AAAAAA; font-size:11px;">Slot B</span>
                </td>
            </tr>
            <tr>
                <td colspan="2" style="background-color: #006400; font-weight: bold; padding: 5px;">Il Tuo Lato (Giocatore 1)</td>
            </tr>
        </table>
        """
        self.lbl_board.setText(board_html)

        details_text = act['details']
        if act['type'] == 'move':
            details_text = f'<a href="move:{details_text}" style="color:#ccffcc; text-decoration:none;">{details_text}</a>'
        elif act['type'] == 'ability':
            details_text = f'<a href="ability:{details_text}" style="color:#ccffcc; text-decoration:none;">{details_text}</a>'
        elif act['type'] == 'item':
            details_text = f'<a href="item:{details_text}" style="color:#ccffcc; text-decoration:none;">{details_text}</a>'

        html = f"""
        <h3 style="color: #66b3ff; margin-bottom: 5px;">Azione: {act['type'].upper()}</h3>
        <b style="color: #dddddd;">Attore:</b> <span style="color:#ffcc00; font-weight:bold;">{act['actor']}</span><br>
        <b style="color: #dddddd;">Bersaglio:</b> <span style="color:#ff6666; font-weight:bold;">{act['target']}</span><br>
        <b style="color: #dddddd;">Dettagli:</b> <span style="color:#ccffcc;">{details_text}</span><br>
        <hr style="border: 1px solid #444;">
        <h4 style="color: #66b3ff;">Dati Tecnici (Event Tags)</h4>
        <div style="background-color: #222222; padding: 10px; border: 1px solid #444; border-radius: 4px;">{tags_html}</div>
        """
        self.txt_state.setHtml(html)
