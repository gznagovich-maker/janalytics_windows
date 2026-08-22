import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QPushButton, QSplitter,
    QApplication, QMessageBox, QComboBox, QLineEdit, QSpinBox, QFileDialog
)
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap, QBrush, QColor, QFont

from src.analytics.team_clustering import get_team_archetypes_and_groupings
from src.analytics.archetypes import generate_unrecognized_actions_log
from database.connection import SessionLocal
from database.models import Match

class NumericTableItem(QTableWidgetItem):
    def __init__(self, value, text=""):
        super().__init__(text if text else str(value))
        self.value = value
        
    def __lt__(self, other):
        if isinstance(other, NumericTableItem):
            return self.value < other.value
        return super().__lt__(other)

def get_pokemon_pixmap(species: str, size: int = 32) -> QPixmap:
    # Usiamo assets/icons come richiesto
    path = os.path.join("assets", "icons", f"{species.lower()}.png")
    if os.path.exists(path):
        return QPixmap(path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return None

def create_team_icons_widget(species_list: list) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(5, 2, 5, 2)
    layout.setSpacing(2)
    
    for sp in species_list:
        pixmap = get_pokemon_pixmap(sp)
        lbl = QLabel()
        if pixmap and not pixmap.isNull():
            lbl.setPixmap(pixmap)
            lbl.setToolTip(sp.capitalize())
        else:
            lbl.setText(sp.capitalize())
            lbl.setStyleSheet("font-size: 10px; color: #ccc; border: 1px solid #555; padding: 2px; border-radius: 4px;")
        layout.addWidget(lbl)
        
    layout.addStretch()
    return container

class TeamAnalysisWidget(QWidget):
    show_builds_signal = Signal(object) # Invia il dict della variant
    
    def __init__(self):
        super().__init__()
        self.groupings = []
        
        main_layout = QVBoxLayout(self)
        
        header_label = QLabel("Analisi e Clustering dei Team per Archetipi")
        header_label.setFixedHeight(124)
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #B6FAF5; margin-bottom: 10px; background-color: #0A0A0A; border: 1px solid #1A1A1A; border-radius: 6px;")
        main_layout.addWidget(header_label)
        
        # --- SEZIONE FILTRI ---
        filters_container = QWidget()
        filters_container.setFixedHeight(68)
        filters_container.setStyleSheet("background-color: #111; border: 1px solid #222; border-radius: 6px;")
        filters_main_layout = QVBoxLayout(filters_container)
        filters_main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Riga 1: Filtri Database (Ricalcolo Necessario)
        db_filters_layout = QHBoxLayout()
        db_lbl = QLabel("Filtri Dati Base:")
        db_lbl.setStyleSheet("color: #aaffaa; font-weight: bold;")
        
        lbl_format = QLabel("Regolamentazione:")
        self.cmb_format = QComboBox()
        session = SessionLocal()
        formats = [f[0] for f in session.query(Match.format).distinct().all() if f[0]]
        session.close()
        self.cmb_format.addItems(["Tutti"] + formats)
        
        lbl_trainer = QLabel("Allenatore:")
        self.txt_trainer = QLineEdit()
        self.txt_trainer.setPlaceholderText("Es. Wolfey...")
        
        lbl_dist = QLabel("Distanza Varianti (D):")
        self.spn_distance = QSpinBox()
        self.spn_distance.setRange(0, 6)
        self.spn_distance.setValue(2)
        
        self.btn_calc = QPushButton("Calcola Raggruppamenti")
        self.btn_calc.setStyleSheet("background-color: #444; color: white; padding: 4px 10px; font-weight: bold; border-radius: 4px;")
        self.btn_calc.clicked.connect(self.load_data)

        self.btn_export = QPushButton("Esporta Log Azioni")
        self.btn_export.setStyleSheet("background-color: #664444; color: white; padding: 4px 10px; font-weight: bold; border-radius: 4px;")
        self.btn_export.clicked.connect(self.export_unrecognized_log)
        
        db_filters_layout.addWidget(db_lbl)
        db_filters_layout.addWidget(lbl_format)
        db_filters_layout.addWidget(self.cmb_format)
        db_filters_layout.addWidget(lbl_trainer)
        db_filters_layout.addWidget(self.txt_trainer)
        db_filters_layout.addWidget(lbl_dist)
        db_filters_layout.addWidget(self.spn_distance)
        db_filters_layout.addWidget(self.btn_calc)
        db_filters_layout.addWidget(self.btn_export)
        db_filters_layout.addStretch()
        
        # Riga 2: Filtri Vista (Immediati)
        view_filters_layout = QHBoxLayout()
        view_lbl = QLabel("Filtri Visualizzazione:")
        view_lbl.setStyleSheet("color: #B6FAF5; font-weight: bold;")
        
        lbl_arch = QLabel("Archetipo:")
        self.cmb_archetype = QComboBox()
        self.cmb_archetype.addItems([
            "Tutti", 
            "Setup Sweeper / Setter", 
            "Hard Trick Room", 
            "Tailwind Offense", 
            "Weather Abuse", 
            "Balance / Good Stuff",
            "Unclassified"
        ])
        self.cmb_archetype.currentIndexChanged.connect(self.populate_table)
        
        lbl_poke = QLabel("Pokémon:")
        self.txt_pokemon = QLineEdit()
        self.txt_pokemon.setPlaceholderText("Es. Incineroar...")
        self.txt_pokemon.textChanged.connect(self.populate_table)
        
        lbl_min_wr = QLabel("Min WR (%):")
        self.spn_min_wr = QSpinBox()
        self.spn_min_wr.setRange(0, 100)
        self.spn_min_wr.setValue(0)
        self.spn_min_wr.valueChanged.connect(self.populate_table)
        
        lbl_max_wr = QLabel("Max WR (%):")
        self.spn_max_wr = QSpinBox()
        self.spn_max_wr.setRange(0, 100)
        self.spn_max_wr.setValue(100)
        self.spn_max_wr.valueChanged.connect(self.populate_table)
        
        lbl_min_match = QLabel("Min Match:")
        self.spn_min_match = QSpinBox()
        self.spn_min_match.setRange(1, 9999)
        self.spn_min_match.setValue(1)
        self.spn_min_match.valueChanged.connect(self.populate_table)
        
        view_filters_layout.addWidget(view_lbl)
        view_filters_layout.addWidget(lbl_arch)
        view_filters_layout.addWidget(self.cmb_archetype)
        view_filters_layout.addWidget(lbl_poke)
        view_filters_layout.addWidget(self.txt_pokemon)
        view_filters_layout.addWidget(lbl_min_wr)
        view_filters_layout.addWidget(self.spn_min_wr)
        view_filters_layout.addWidget(lbl_max_wr)
        view_filters_layout.addWidget(self.spn_max_wr)
        view_filters_layout.addWidget(lbl_min_match)
        view_filters_layout.addWidget(self.spn_min_match)
        view_filters_layout.addStretch()
        
        filters_main_layout.addLayout(db_filters_layout)
        filters_main_layout.addLayout(view_filters_layout)
        
        main_layout.addWidget(filters_container)
        
        # --- SPLITTER E GRIGLIE ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background-color: #333; width: 2px; }")
        
        # Lato Sinistro: Gruppi (Core)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.table_groups = QTableWidget()
        self.table_groups.setColumnCount(4)
        self.table_groups.setHorizontalHeaderLabels(["Core (Componente Base)", "Win Rate (%)", "Match", "Varianti"])
        self.table_groups.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_groups.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_groups.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table_groups.verticalHeader().setDefaultSectionSize(45)
        self.table_groups.itemSelectionChanged.connect(self.on_group_selected)
        
        left_layout.addWidget(self.table_groups)
        
        right_widget = QWidget()
        detail_layout = QVBoxLayout(right_widget)
        
        self.lbl_detail_title = QLabel("Seleziona un Raggruppamento")
        self.lbl_detail_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FAB7F0;")
        
        self.tree_variants = QTreeWidget()
        self.tree_variants.setHeaderHidden(True)
        self.tree_variants.setIndentation(20)
        self.tree_variants.itemDoubleClicked.connect(self.open_replay)
        
        info_label = QLabel("Espandi una variante. Doppio clic su un Match per aprirlo su Showdown")
        info_label.setStyleSheet("color: #888888; font-size: 11px;")
        
        detail_layout.addWidget(self.lbl_detail_title)
        detail_layout.addWidget(info_label)
        detail_layout.addWidget(self.tree_variants)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([2000, 2000]) # Forza il 50/50
        
        main_layout.addWidget(splitter)
        
    def load_data(self):
        self.btn_calc.setText("Calcolo in corso...")
        self.btn_calc.setEnabled(False)
        QApplication.processEvents()
        
        try:
            # Passiamo il parametro distanza al calcolo
            dist = self.spn_distance.value()
            fmt = self.cmb_format.currentText()
            trainer = self.txt_trainer.text().strip()
            self.groupings = get_team_archetypes_and_groupings(
                max_distance=dist, 
                format_filter=fmt, 
                trainer_filter=trainer
            )
            self.populate_table()
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Errore nel calcolo: {e}")
        finally:
            self.btn_calc.setText("Calcola Raggruppamenti")
            self.btn_calc.setEnabled(True)

    def export_unrecognized_log(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Salva Log Azioni Non Riconosciute", "unrecognized_actions.txt", "Text Files (*.txt)")
        if not file_path:
            return
            
        try:
            with SessionLocal() as session:
                log_data = generate_unrecognized_actions_log(session)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(log_data)
            QMessageBox.information(self, "Esportazione completata", f"Log salvato in:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile esportare il log:\n{str(e)}")
            
    def populate_table(self):
        self.table_groups.setSortingEnabled(False)
        self.table_groups.setRowCount(0)
        
        filter_arch = self.cmb_archetype.currentText()
        filter_poke = self.txt_pokemon.text().strip().lower()
        
        row_idx = 0
        
        for g in self.groupings:
            # Filtro Archetipo
            if filter_arch != "Tutti":
                has_arch = False
                
                # Mappiamo le voci della combobox a termini di ricerca robusti
                mapping = {
                    "Setup Sweep": "setupsweep",
                    "Hard Trick Room": "hardtrickroom",
                    "Tailwind Offense": "tailwindoffense",
                    "Weather Abuse": "team",
                    "Balance / Good Stuff": "balance",
                    "Unclassified": "unclassified"
                }
                search_term = mapping.get(filter_arch, filter_arch.lower())
                
                for v in g['variants']:
                    for a in v['archetypes']:
                        # Isoliamo la parte degli archetipi (dopo i due punti)
                        arch_part = a.lower().split(":")
                        arch_part = arch_part[1] if len(arch_part) > 1 else a.lower()
                        if search_term in arch_part:
                            has_arch = True
                            break
                    if has_arch:
                        break
                if not has_arch:
                    continue
                
            # Filtro Pokémon (controlla nel core)
            if filter_poke:
                # Se non c'è corrispondenza nel core species, skippa
                if not any(filter_poke in sp.lower() for sp in g["core_species"]):
                    continue
            
            # Filtro Win Rate e Match Minimi
            min_wr = self.spn_min_wr.value()
            max_wr = self.spn_max_wr.value()
            min_match = self.spn_min_match.value()
            
            if not (min_wr <= g["win_rate"] <= max_wr):
                continue
                
            if g["total_matches"] < min_match:
                continue
            
            self.table_groups.insertRow(row_idx)
            
            core_widget = create_team_icons_widget(g["core_species"])
            
            # Per mantenere un riferimento al gruppo, lo attacchiamo alla cella 0
            item_core = QTableWidgetItem()
            item_core.setData(Qt.UserRole, g)
            self.table_groups.setItem(row_idx, 0, item_core)
            self.table_groups.setCellWidget(row_idx, 0, core_widget)
            
            win_item = NumericTableItem(g['win_rate'], f"{g['win_rate']}%")
            win_item.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 1, win_item)
            
            match_item = NumericTableItem(g['total_matches'])
            match_item.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 2, match_item)
            
            var_item = NumericTableItem(g['num_variants'])
            var_item.setTextAlignment(Qt.AlignCenter)
            self.table_groups.setItem(row_idx, 3, var_item)
            
            row_idx += 1
            
        self.table_groups.setSortingEnabled(True)
        self.table_groups.sortItems(2, Qt.DescendingOrder)
            
    def on_group_selected(self):
        row = self.table_groups.currentRow()
        if row < 0:
            return
            
        # Recuperiamo il gruppo dai dati dell'item (perché gli indici row potrebbero non corrispondere a self.groupings per via dei filtri)
        item = self.table_groups.item(row, 0)
        if not item: return
        
        group = item.data(Qt.UserRole)
        
        self.lbl_detail_title.setText(f"Raggruppamento selezionato ({group['total_matches']} match)")
        self.tree_variants.clear()
        
        for i, v in enumerate(group["variants"]):
            var_item = QTreeWidgetItem(self.tree_variants)
            self.tree_variants.setItemWidget(var_item, 0, self.create_variant_header(v, i+1))
            
            for match_data in v["match_ids"]:
                match_id = match_data["id"]
                match_title = match_data["title"]
                
                child_item = QTreeWidgetItem(var_item)
                child_item.setText(0, f"▶ {match_title} ({match_id})")
                child_item.setData(0, Qt.UserRole, match_id)
                
    def create_variant_header(self, variant: dict, index: int) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        
        lbl_info = QLabel(f"<b>VARIANTE {index}</b><br><span style='color:#ccc; font-size:10px;'>{variant['total']} match, {variant['wins']} win</span>")
        lbl_info.setFixedWidth(100)
        layout.addWidget(lbl_info)
        
        arch_str = variant.get("archetypes", [""])[0]
        parts = arch_str.split(" : ")
        arch_data = parts[1].split() if len(parts) > 1 else []
        
        formatted_archs = []
        for a in arch_data:
            if ":" in a:
                name, pct = a.split(":")
                if name == "SetupSweep": name = "Setup Sweep"
                if name == "HardTrickRoom": name = "Hard Trick Room"
                if name == "TailwindOffense": name = "Tailwind Offense"
                formatted_archs.append(f"<span style='color:#aaffaa;'>{name}: {pct}</span>")
            else:
                formatted_archs.append(f"<span style='color:#aaffaa;'>{a}</span>")
                
        arch_html = "<br>".join(formatted_archs) if formatted_archs else "<span style='color:#aaa;'>Nessun dato</span>"
        lbl_arch = QLabel(arch_html)
        lbl_arch.setStyleSheet("font-size: 11px;")
        lbl_arch.setFixedWidth(140)
        layout.addWidget(lbl_arch)
        
        icons_widget = create_team_icons_widget(variant["species_ids"])
        layout.addWidget(icons_widget)
        
        btn_builds = QPushButton("Builds")
        btn_builds.setCursor(Qt.PointingHandCursor)
        btn_builds.setStyleSheet("background-color: #B6FAF5; color: #0A0A0A; padding: 4px 12px; border-radius: 4px; font-weight: bold;")
        btn_builds.clicked.connect(lambda: self.show_builds_signal.emit(variant))
        layout.addWidget(btn_builds)
        
        layout.addStretch()
        return container
                
    def open_replay(self, item: QTreeWidgetItem, column: int):
        match_id = item.data(0, Qt.UserRole)
        if match_id:
            url = f"https://replay.pokemonshowdown.com/{match_id}"
            QDesktopServices.openUrl(QUrl(url))
