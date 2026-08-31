import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox,
    QPushButton, QStackedWidget, QWidget, QFormLayout, QScrollArea, QFrame,
    QProgressBar, QApplication, QFileDialog, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap, QColor, QIcon, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from config.theme import Palette
from src.domain.batch_generator_service import BatchGeneratorService
from src.utils.icon_utils import get_pokemon_icon_path
from domain.batch_analyzer import BatchDamageAnalyzer, convert_desc_to_champions, normalize_evs, evs_to_champions

class BatchDamageConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurazione Analisi Batch")
        self.setFixedSize(450, 300)
        self.setStyleSheet(f"background-color: {Palette.BG_SURFACE}; color: {Palette.TEXT_PRIMARY};")
        
        self.selected_target_type = "Team Caricati"
        self.selected_format = ""
        self.min_usage = 0.0
        
        layout = QVBoxLayout(self)
        
        # Titolo
        lbl_title = QLabel("Analisi Batch Danni")
        lbl_title.setStyleSheet(f"color: {Palette.PRIMARY}; font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_title)
        
        # Scelta Target
        layout.addWidget(QLabel("Scegli Target Minacce:"))
        self.combo_target = QComboBox()
        self.combo_target.addItems(["Team Caricati", "Formato"])
        self.combo_target.setStyleSheet(f"background-color: {Palette.BG_APP}; border: 1px solid {Palette.BORDER_COLOR}; padding: 6px; border-radius: 4px;")
        self.combo_target.currentTextChanged.connect(self._on_target_changed)
        layout.addWidget(self.combo_target)
        
        # Form per le opzioni
        self.stacked_options = QStackedWidget()
        
        # Opzioni Team Caricati
        page_teams = QWidget()
        layout_teams = QVBoxLayout(page_teams)
        layout_teams.addWidget(QLabel("I Pokémon analizzati verranno testati contro\ni Pokémon presenti negli altri team caricati in 'Costruisci e Confronta'."))
        layout_teams.addStretch()
        self.stacked_options.addWidget(page_teams)
        
        # Opzioni Formato
        page_format = QWidget()
        form_layout = QFormLayout(page_format)
        
        self.combo_format = QComboBox()
        self.combo_format.setStyleSheet(f"background-color: {Palette.BG_APP}; border: 1px solid {Palette.BORDER_COLOR}; padding: 6px; border-radius: 4px;")
        formats = BatchGeneratorService.get_available_formats()
        self.combo_format.addItems(formats)
        
        self.spin_usage = QDoubleSpinBox()
        self.spin_usage.setRange(0.0, 100.0)
        self.spin_usage.setDecimals(1)
        self.spin_usage.setSuffix(" %")
        self.spin_usage.setValue(5.0)
        self.spin_usage.setStyleSheet(f"background-color: {Palette.BG_APP}; border: 1px solid {Palette.BORDER_COLOR}; padding: 6px; border-radius: 4px;")
        
        form_layout.addRow("Nome Formato:", self.combo_format)
        form_layout.addRow("Min Usage:", self.spin_usage)
        self.stacked_options.addWidget(page_format)
        
        layout.addWidget(self.stacked_options)
        
        # Pulsanti
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Annulla")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.BG_APP}; border: 1px solid {Palette.BORDER_COLOR}; padding: 8px 16px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.BG_SURFACE_ELEVATED}; }}"
        )
        
        self.btn_start = QPushButton("Avvia Analisi")
        self.btn_start.clicked.connect(self.accept)
        self.btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.SECONDARY}; }}"
        )
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_start)
        
        layout.addStretch()
        layout.addLayout(btn_layout)
        
    def _on_target_changed(self, target: str):
        self.selected_target_type = target
        if target == "Formato":
            self.stacked_options.setCurrentIndex(1)
        else:
            self.stacked_options.setCurrentIndex(0)
            
    def accept(self):
        self.selected_target_type = self.combo_target.currentText()
        if self.selected_target_type == "Formato":
            self.selected_format = self.combo_format.currentText()
            self.min_usage = self.spin_usage.value()
        super().accept()

class BatchDamageResultDialog(QDialog):
    def __init__(self, def_results, off_results, switch_results, team_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Risultati Analisi Batch")
        self.setMinimumSize(950, 700)
        
        self.def_results = def_results
        self.off_results = off_results
        self.switch_results = switch_results
        self.team_data = team_data or []
        
        layout = QVBoxLayout(self)
        
        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Tab Difesa
        self.tab_def = QWidget()
        self.layout_def = QVBoxLayout(self.tab_def)
        self.tree_def = self._create_tree("Nessun danno critico subito rilevato contro i parametri impostati! 🎉", self.def_results, self.layout_def, is_offensive=False)
        self.tabs.addTab(self.tab_def, "🛡️ Danni Subiti (Difesa)")
        
        # Tab Attacco
        self.tab_off = QWidget()
        self.layout_off = QVBoxLayout(self.tab_off)
        self.tree_off = self._create_tree("Nessun danno critico inflitto rilevato contro i parametri impostati! 🎉", self.off_results, self.layout_off, is_offensive=True)
        self.tabs.addTab(self.tab_off, "⚔️ Danni Inflitti (Attacco)")
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_export = QPushButton("📄 Esporta PDF")
        btn_export.clicked.connect(self.export_pdf)
        btn_export.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.PRIMARY}; color: {Palette.BG_APP}; border: none; padding: 10px 16px; border-radius: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.PRIMARY_BRIGHT}; }}"
        )
        
        has_critical = any(len(v) > 0 for v in self.def_results.values()) or any(len(v) > 0 for v in self.off_results.values())
        if not has_critical:
            btn_export.hide()
            
        btn_layout.addWidget(btn_export)
            
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet(
            f"QPushButton {{ background-color: {Palette.TERTIARY}; color: {Palette.TEXT_PRIMARY}; border: none; padding: 10px 16px; border-radius: 6px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {Palette.SECONDARY}; }}"
        )
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)

    def _create_tree(self, empty_msg: str, data: dict, layout: QVBoxLayout, is_offensive: bool) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Palette.BG_SURFACE};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_COLOR};
                border-radius: 6px;
                padding: 5px;
            }}
            QTreeWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {Palette.BORDER_COLOR};
            }}
            QTreeWidget::item:selected {{
                background-color: {Palette.BG_SURFACE_ELEVATED};
            }}
        """)
        
        has_data = False
        for root_entity, threats in data.items():
            if not threats:
                continue
            has_data = True
            
            root_item = QTreeWidgetItem(tree)
            root_item.setText(0, root_entity)
            root_path = get_pokemon_icon_path(root_entity)
            if root_path and os.path.exists(root_path):
                root_item.setIcon(0, QIcon(root_path))
            root_item.setFont(0, QFont("Segoe UI", 12, QFont.Bold))
            root_item.setForeground(0, QColor(Palette.TEXT_PRIMARY))
            
            grouped_threats = {}
            for t in threats:
                # Se è offensivo, root = attacker (nostro), t["defender"] = target
                # Se è difensivo, root = defender (nostro), t["attacker"] = threat
                target_entity = t["defender"] if is_offensive else t["attacker"]
                if target_entity not in grouped_threats:
                    grouped_threats[target_entity] = []
                grouped_threats[target_entity].append(t)
                
            for target_name, t_list in grouped_threats.items():
                child_item = QTreeWidgetItem(root_item)
                child_item.setText(0, target_name)
                t_path = get_pokemon_icon_path(target_name)
                if t_path and os.path.exists(t_path):
                    child_item.setIcon(0, QIcon(t_path))
                child_item.setFont(0, QFont("Segoe UI", 11, QFont.Bold))
                child_item.setForeground(0, QColor(Palette.PRIMARY_BRIGHT))
                
                for t in t_list:
                    build_item = QTreeWidgetItem(child_item)
                    
                    if is_offensive:
                        scenario = t.get("scenario", "")
                        info = f"Scenario: {scenario}\n"
                        info += f"Mossa: {t['move']}  ({t['ko_chance'] if t['is_ohko'] else f'Danni: {t['damage_min']} - {t['damage_max']} HP (Max {t['damage_pct']}%)'})\n"
                        info += f"Info: {t['description']}"
                    else:
                        info = f"Natura: {t.get('nature') or 'Nessuna'} | Strumento: {t.get('item') or 'Nessuno'}\n"
                        info += f"Mossa: {t['move']}  ({t['ko_chance'] if t['is_ohko'] else f'Danni: {t['damage_min']} - {t['damage_max']} HP (Max {t['damage_pct']}%)'})\n"
                        info += f"Info: {t['description']}"
                        
                        top_switches = t.get("top_switches", [])
                        if top_switches:
                            info += "\n\n🔄 Top Switch Consigliati:\n"
                            for idx, sw in enumerate(top_switches):
                                info += f"  {idx+1}. {sw['switch']} (NAS: {sw['score']:.1f}, Efficienza: {sw['efficienza']:.2f}, Danno Previsto: {sw['dmg_switch']:.1f}%)\n"
                    
                    build_item.setText(0, info)
                    
                    if t["is_ohko"]:
                        build_item.setForeground(0, QColor(Palette.SECONDARY))
                    elif t.get("damage_pct", 0) > 80.0:
                        build_item.setForeground(0, QColor(Palette.TEXT_PRIMARY))
                    else:
                        build_item.setForeground(0, QColor(Palette.TEXT_MUTED))
                        
        if not has_data:
            tree.hide()
            empty_lbl = QLabel(empty_msg)
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet(f"color: {Palette.SECONDARY}; font-size: 14px; font-weight: bold; margin-top: 50px;")
            layout.addWidget(empty_lbl)
            layout.addStretch()
        else:
            layout.addWidget(tree)
            
        return tree

    def _create_switch_table(self, data: list, layout: QVBoxLayout) -> QTableWidget:
        table = QTableWidget()
        headers = [
            "Pokemon Attaccante", "Natura", "Attacco", "Bersaglio", "Switch Suggerito",
            "Danno su Bersaglio", "Danno su Switch", "Outspeed", "Dmg True Survival",
            "Press. da Bersaglio", "Press. da Switch", "NAS (Score)", "Efficienza"
        ]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        
        header = table.horizontalHeader()
        for i in range(len(headers)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch) 
            
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Palette.BG_SURFACE};
                color: {Palette.TEXT_PRIMARY};
                border: 1px solid {Palette.BORDER_COLOR};
                gridline-color: {Palette.BORDER_COLOR};
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {Palette.BG_CARD};
                color: {Palette.TEXT_PRIMARY};
                padding: 4px;
                border: 1px solid {Palette.BORDER_COLOR};
                font-weight: bold;
                font-size: 11px;
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {Palette.BG_SURFACE_ELEVATED};
            }}
        """)
        
        table.setRowCount(len(data))
        for row_idx, row_data in enumerate(data):
            att_item = QTableWidgetItem(row_data.get("attacker", ""))
            nat_item = QTableWidgetItem(row_data.get("nature", ""))
            move_item = QTableWidgetItem(row_data.get("move", ""))
            move_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
            tgt_item = QTableWidgetItem(row_data.get("target", ""))
            
            sw_item = QTableWidgetItem(row_data.get("switch", ""))
            sw_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
            sw_item.setForeground(QColor(Palette.PRIMARY))
            
            dmg_tgt = row_data.get("dmg_target", 0.0)
            dmg_sw = row_data.get("dmg_switch", 0.0)
            press_tgt = row_data.get("press_target", 0.0)
            press_sw = row_data.get("press_switch", 0.0)
            
            score = row_data.get("score", 0.0)
            efficienza = row_data.get("efficienza", 0.0)
            outspeeds = row_data.get("outspeeds", False)
            
            dmg_true = dmg_sw if outspeeds else dmg_sw * 2.0
            
            out_item = QTableWidgetItem("Si" if outspeeds else "No")
            out_item.setForeground(QColor("#00cc00" if outspeeds else "#cc0000"))
            
            dmg_true_item = QTableWidgetItem(f"{dmg_true:.1f}%")
            dmg_true_item.setForeground(QColor("#cc0000" if dmg_true > 80.0 else Palette.TEXT_PRIMARY))
            
            dmg_tgt_item = QTableWidgetItem(f"{dmg_tgt:.1f}%")
            dmg_tgt_item.setForeground(QColor("#cc0000" if dmg_tgt > 80.0 else Palette.TEXT_PRIMARY))
            
            dmg_sw_item = QTableWidgetItem(f"{dmg_sw:.1f}%")
            dmg_sw_item.setForeground(QColor("#cc0000" if dmg_sw > 80.0 else Palette.TEXT_PRIMARY))
            
            press_tgt_item = QTableWidgetItem(f"{press_tgt:.1f}%")
            press_tgt_item.setForeground(QColor("#00cc00" if press_tgt > 80.0 else Palette.TEXT_PRIMARY))
            
            press_sw_item = QTableWidgetItem(f"{press_sw:.1f}%")
            press_sw_item.setForeground(QColor("#00cc00" if press_sw > 80.0 else Palette.TEXT_PRIMARY))
            
            score_item = QTableWidgetItem(f"{score:.1f}")
            score_item.setFont(QFont("Segoe UI", 11, QFont.Bold))
            score_item.setForeground(QColor(Palette.PRIMARY_BRIGHT))
            
            eff_item = QTableWidgetItem(f"{efficienza:.2f}")
            
            items = [att_item, nat_item, move_item, tgt_item, sw_item, dmg_tgt_item, dmg_sw_item, out_item, dmg_true_item, press_tgt_item, press_sw_item, score_item, eff_item]
            for col_idx, item in enumerate(items):
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                table.setItem(row_idx, col_idx, item)
                
        layout.addWidget(table)
        return table

    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Salva Report PDF", "Report_Analisi_Danni.pdf", "PDF Files (*.pdf)")
        if not path:
            return
            
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            
            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #333; margin: 0; padding: 0; }}
                    .cover {{ text-align: center; margin-top: 150pt; page-break-after: always; }}
                    .cover h1 {{ font-size: 36pt; color: #1a237e; border-bottom: 3pt solid #1a237e; padding-bottom: 15pt; }}
                    .cover h3 {{ font-size: 18pt; color: #555; margin-top: 30pt; }}
                    
                    h2 {{ color: #1a237e; border-bottom: 2pt solid #1a237e; padding-bottom: 4pt; margin-top: 24pt; font-size: 16pt; }}
                    
                    .team-grid {{ width: 100%; border-collapse: collapse; margin-top: 15pt; }}
                    .team-grid td {{ width: 50%; vertical-align: top; padding: 12pt; border: 1pt solid #ddd; font-size: 11pt; }}
                    .team-header {{ font-size: 14pt; font-weight: bold; color: #1a237e; margin-bottom: 8pt; }}
                    
                    table.attack-card {{ width: 100%; border-collapse: collapse; margin-bottom: 15pt; border: 1pt solid #b0bec5; background-color: #fafafa; }}
                    table.attack-card td {{ padding: 8pt; }}
                    .attack-header {{ background-color: #e8eaf6; border-bottom: 1pt solid #b0bec5; }}
                    .attack-cell {{ font-size: 11pt; }}
                    
                    .ohko-yes {{ color: #d32f2f; font-weight: bold; }}
                    .ohko-no {{ color: #388e3c; font-weight: bold; }}
                    
                    .switch-row td {{ padding: 3pt 8pt 8pt 8pt; background-color: #e8f5e9; font-size: 10pt; border-bottom: 2pt solid #ccc; }}
                    .switch-title {{ color: #2e7d32; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="cover">
                    <h1>Pokemon VGC<br>DAMAGE ANALYSIS REPORT</h1>
                    <h3>PREPARED BY: JAnalytics</h3>
                    <h3>TARGET: COMPETITIVE PLAYERS</h3>
                    <h3>DATE: {current_date}</h3>
                </div>
            """
            
            # --- SEZIONE TEAM BUILD ---
            if self.team_data:
                html += "<h2>📋 Build dei Pokémon del Team</h2><table class='team-grid'>"
                for i in range(0, len(self.team_data), 2):
                    html += "<tr>"
                    for j in range(2):
                        if i + j < len(self.team_data):
                            p = self.team_data[i + j]
                            name = p.get("name", "Sconosciuto")
                            opts = p.get("options", {})
                            evs = opts.get("evs", {})
                            champ_evs = evs_to_champions(evs)
                            ev_str = " / ".join(f"{v} {k.capitalize()}" for k, v in champ_evs.items() if v > 0) or "Nessun EV"
                            ability = opts.get("ability", "Nessuna")
                            item = opts.get("item", "Nessuno")
                            moves = "<br>".join(f"- {m}" for m in p.get("moves", []))
                            
                            p_path = get_pokemon_icon_path(name)
                            img_tag = f"<img src='file:///{p_path.replace(chr(92), '/')}' width='32' height='32' style='vertical-align: middle;'> " if p_path and os.path.exists(p_path) else ""
                            
                            html += f"""
                            <td>
                                <div class='team-header'>{img_tag}{name}</div>
                                <b>Item:</b> {item}<br>
                                <b>Ability:</b> {ability}<br>
                                <b>EVs:</b> {ev_str}<br>
                                <b>Moves:</b><br>{moves}
                            </td>
                            """
                        else:
                            html += "<td></td>"
                    html += "</tr>"
                html += "</table><div style='page-break-after: always;'></div>"
            
            # --- SEZIONE DIFESA ---
            html += "<h2>🛡️ Defense Report (Danni Subiti)</h2>"
            has_def = False
            for defender, threats in self.def_results.items():
                if not threats: continue
                has_def = True
                
                def_path = get_pokemon_icon_path(defender)
                img_tag = f"<img src='file:///{def_path.replace(chr(92), '/')}' width='24' height='24' style='vertical-align: middle;'> " if def_path and os.path.exists(def_path) else "🛡️ "
                html += f"<h3 style='margin-top:20px; color:#1a237e;'>{img_tag}Target: {defender}</h3>"
                
                for t in threats:
                    att_path = get_pokemon_icon_path(t["attacker"])
                    att_img = f"<img src='file:///{att_path.replace(chr(92), '/')}' width='16' height='16' style='vertical-align: middle;'> " if att_path and os.path.exists(att_path) else ""
                    
                    ko_cls = "ohko-yes" if t["is_ohko"] else "ohko-no"
                    dmg_text = f"{t['damage_min']} - {t['damage_max']} HP (Max {t['damage_pct']}%)" if not t["is_ohko"] else "100%+"
                    
                    html += f"""
                    <table class='attack-card'>
                        <tr>
                            <td colspan="2" class="attack-header">
                                <span style="font-size: 12pt;">{att_img}<b>{t['attacker']}</b> ({t.get('nature', 'Nessuna')} | {t.get('item', 'Nessuno')}) ⚔️ <b>{t['move']}</b></span><br>
                                <span style='font-size:10pt; color:#555;'>{t['description']}</span>
                            </td>
                        </tr>
                        <tr>
                            <td width="50%" class="attack-cell"><b>Danni:</b> {dmg_text}</td>
                            <td width="50%" class="attack-cell"><b>Stato:</b> <span class='{ko_cls}'>{t['ko_chance']}</span></td>
                        </tr>
                    """
                    
                    top_switches = t.get("top_switches", [])
                    if top_switches:
                        html += f"<tr class='switch-row'><td colspan='2'><span class='switch-title'>🔄 Top Switch Consigliati:</span> "
                        sw_texts = []
                        for idx, sw in enumerate(top_switches[:3]):
                            sw_texts.append(f"{idx+1}. {sw['switch']} (Danni: {sw['dmg_switch']:.1f}%)")
                        html += " | ".join(sw_texts)
                        html += "</td></tr>"
                        
                    html += "</table>"
                
            if not has_def:
                html += "<p>Nessun danno critico subito.</p>"
            html += "<div style='page-break-after: always;'></div>"
                
            # --- SEZIONE ATTACCO ---
            html += "<h2>⚔️ Offense Report (Danni Inflitti)</h2>"
            has_off = False
            for attacker, threats in self.off_results.items():
                if not threats: continue
                has_off = True
                
                att_path = get_pokemon_icon_path(attacker)
                img_tag = f"<img src='file:///{att_path.replace(chr(92), '/')}' width='24' height='24' style='vertical-align: middle;'> " if att_path and os.path.exists(att_path) else "⚔️ "
                html += f"<h3 style='margin-top:20px; color:#1a237e;'>{img_tag}Attacker: {attacker}</h3>"
                
                for t in threats:
                    def_path = get_pokemon_icon_path(t["defender"])
                    def_img = f"<img src='file:///{def_path.replace(chr(92), '/')}' width='16' height='16' style='vertical-align: middle;'> " if def_path and os.path.exists(def_path) else ""
                    
                    ko_cls = "ohko-yes" if t["is_ohko"] else "ohko-no"
                    dmg_text = f"{t['damage_min']} - {t['damage_max']} HP (Max {t['damage_pct']}%)" if not t["is_ohko"] else "100%+"
                    scenario = f" [{t.get('scenario', '')}]" if t.get('scenario') else ""
                    
                    html += f"""
                    <table class='attack-card'>
                        <tr>
                            <td colspan="2" class="attack-header">
                                <span style="font-size: 12pt;">{def_img}<b>{t['defender']}</b> ({t.get('nature', 'Nessuna')} | {t.get('item', 'Nessuno')}) 🛡️ <b>{t['move']}</b>{scenario}</span><br>
                                <span style='font-size:10pt; color:#555;'>{t['description']}</span>
                            </td>
                        </tr>
                        <tr>
                            <td width="50%" class="attack-cell"><b>Danni:</b> {dmg_text}</td>
                            <td width="50%" class="attack-cell"><b>Stato:</b> <span class='{ko_cls}'>{t['ko_chance']}</span></td>
                        </tr>
                    </table>
                    """
                
            if not has_off:
                html += "<p>Nessun danno critico inflitto.</p>"
                
            html += "</body></html>"
            
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(printer)
            
            QMessageBox.information(self, "Successo", "Report PDF salvato correttamente!")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile esportare il PDF:\n{str(e)}")
