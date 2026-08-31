import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QFrame, QDialog, QDialogButtonBox, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QPixmap, QIcon, QColor
from PySide6.QtCore import Qt, QThread, Signal

from database.connection import SessionLocal
from database.models_v2 import MatchV2
from database.core_repository import MetaAnalysisRepository
from src.domain.core_models import PokemonUsageStats, BuildDetails, CoreTeammates, CoreCombo

class CoreAnalysisWorker(QThread):
    progress = Signal(str)
    finished = Signal(list)
    error = Signal(str)
    
    def __init__(self, format_id: str):
        super().__init__()
        self.format_id = format_id
        
    def run(self):
        try:
            self.progress.emit("Connessione al database...")
            session = SessionLocal()
            repo = MetaAnalysisRepository(session)
            
            self.progress.emit(f"Estrazione e calcolo delle Core per il formato {self.format_id} (potrebbe richiedere qualche secondo)...")
            stats = repo.get_all_pokemon_stats(self.format_id)
            
            session.close()
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))


from src.utils.icon_utils import get_pokemon_icon_path

TYPE_COLORS = {
    "Normal": "#A8A77A", "Fire": "#EE8130", "Water": "#6390F0", "Electric": "#F7D02C",
    "Grass": "#7AC74C", "Ice": "#96D9D6", "Fighting": "#C22E28", "Poison": "#A33EA1",
    "Ground": "#E2BF65", "Flying": "#A98FF3", "Psychic": "#F95587", "Bug": "#A6B91A",
    "Rock": "#B6A136", "Ghost": "#735797", "Dragon": "#6F35FC", "Dark": "#705746",
    "Steel": "#B7B7CE", "Fairy": "#D685AD"
}

class CoreMatchupDialog(QDialog):
    def __init__(self, core: CoreCombo, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Analisi Difensiva Core: {' + '.join([p.capitalize() for p in core.pokemon])}")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Titolo
        title = QLabel(f"<h2 style='color: #C2BFBC;'>{' + '.join([p.capitalize() for p in core.pokemon])}</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Resistenze
        if core.resistances:
            layout.addWidget(QLabel("<b style='color:#4CAF50;'>Resistenze (Tipi a cui la Core resiste):</b>"))
            res_layout = QHBoxLayout()
            for t in core.resistances:
                lbl = QLabel(t)
                color = TYPE_COLORS.get(t.capitalize(), "#777")
                lbl.setStyleSheet(f"background-color: {color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
                res_layout.addWidget(lbl)
            res_layout.addStretch()
            layout.addLayout(res_layout)
            
        # Debolezze
        if core.weaknesses:
            layout.addWidget(QLabel("<b style='color:#F44336;'>Debolezze (Tipi super-efficaci):</b>"))
            deb_layout = QHBoxLayout()
            for t in core.weaknesses:
                lbl = QLabel(t)
                color = TYPE_COLORS.get(t.capitalize(), "#777")
                lbl.setStyleSheet(f"background-color: {color}; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
                deb_layout.addWidget(lbl)
            deb_layout.addStretch()
            layout.addLayout(deb_layout)
            
        # Minacce
        if core.top_threats:
            layout.addWidget(QLabel("<b style='color:#FF9800;'>Principali Minacce nel Metagame:</b>"))
            thr_layout = QHBoxLayout()
            for pk in core.top_threats:
                icon_path = get_pokemon_icon_path(pk)
                container = QVBoxLayout()
                container.setAlignment(Qt.AlignCenter)
                if icon_path:
                    lbl_icon = QLabel()
                    lbl_icon.setPixmap(QPixmap(icon_path).scaledToHeight(40, Qt.SmoothTransformation))
                    container.addWidget(lbl_icon, alignment=Qt.AlignCenter)
                lbl_name = QLabel(pk.capitalize())
                container.addWidget(lbl_name, alignment=Qt.AlignCenter)
                thr_layout.addLayout(container)
            thr_layout.addStretch()
            layout.addLayout(thr_layout)
            
        layout.addStretch()
        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

class CoreCellWidget(QWidget):
    def __init__(self, core_list, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        if not core_list:
            lbl = QLabel("N/A")
            layout.addWidget(lbl)
            layout.addStretch()
            return
            
        for i, core in enumerate(core_list):
            combo = core.pokemon
            pct = core.usage_percent
            
            combo_layout = QVBoxLayout()
            combo_layout.setContentsMargins(0, 0, 0, 0)
            combo_layout.setSpacing(4)
            
            # Row 1: Usage % + Pokemon Icons
            r1 = QHBoxLayout()
            r1.setContentsMargins(0, 0, 0, 0)
            r1.addWidget(QLabel(f"<b>{pct:.1f}%</b>"))
            
            for pk in combo:
                icon_path = get_pokemon_icon_path(pk)
                if icon_path:
                    lbl = QLabel()
                    pix = QPixmap(icon_path).scaledToHeight(24, Qt.SmoothTransformation)
                    lbl.setPixmap(pix)
                    lbl.setToolTip(pk.capitalize())
                    r1.addWidget(lbl)
                else:
                    lbl = QLabel(pk.capitalize())
                    lbl.setWordWrap(True)
                    r1.addWidget(lbl)
            r1.addStretch()
            
            btn_info = QPushButton("🔎 Analisi")
            btn_info.setCursor(Qt.PointingHandCursor)
            btn_info.clicked.connect(lambda checked=False, c=core: self.open_matchup_dialog(c))
            r1.addWidget(btn_info)
            
            combo_layout.addLayout(r1)
            layout.addLayout(combo_layout)
            
            if i < len(core_list) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.HLine)
                sep.setFrameShadow(QFrame.Sunken)
                sep.setStyleSheet("background-color: #333;")
                layout.addWidget(sep)
                
        layout.addStretch()

    def open_matchup_dialog(self, core):
        dialog = CoreMatchupDialog(core, self)
        dialog.exec_()


class GlobalMetaWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        
        # Controls Header
        self.header_widget = QFrame()
        self.header_widget.setObjectName("header_widget")
        self.header_widget.setFixedHeight(64)
        self.header_widget.setStyleSheet("#header_widget { background-color: #342A38; border-radius: 8px; }")
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)
        self.header_widget.setGraphicsEffect(shadow)
        
        controls = QHBoxLayout(self.header_widget)
        controls.setContentsMargins(15, 10, 15, 10)
        
        controls.addSpacing(30)
        
        controls.addWidget(QLabel("Formato:"))
        self.format_combo = QComboBox()
        controls.addWidget(self.format_combo)
        
        self.btn_analyze = QPushButton("Analizza Core")
        self.btn_analyze.clicked.connect(self.start_analysis)
        controls.addWidget(self.btn_analyze)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        controls.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        controls.addWidget(self.status_label)
        controls.addStretch()
        
        self.layout.addWidget(self.header_widget)
        
        # Main Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.layout.addWidget(self.splitter)
        
        # Table for global stats
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Pokémon", "Usage %", "Top Core 2", "Top Core 3", "Top Core 4"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.on_pokemon_double_clicked)
        
        self.splitter.addWidget(self.table)
        
        # Build Detail Tree
        self.detail_tree = QTreeWidget()
        self.detail_tree.setHeaderLabels(["Builds & Core", "Dettagli"])
        self.detail_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.detail_tree.hide()
        
        self.splitter.addWidget(self.detail_tree)
        self.splitter.setSizes([700, 300])
        
        self.worker = None
        self.current_stats = []
        
        self.load_formats()
        
    def showEvent(self, event):
        super().showEvent(event)
        # Salva il formato corrente se c'è
        curr = self.format_combo.currentText()
        self.load_formats()
        if curr:
            idx = self.format_combo.findText(curr)
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
        
    def load_formats(self):
        session = SessionLocal()
        try:
            formats = session.query(MatchV2.format).distinct().all()
            self.format_combo.clear()
            for (f,) in formats:
                if f:
                    self.format_combo.addItem(f)
        except Exception as e:
            print("Error loading formats:", e)
        finally:
            session.close()
            
    def start_analysis(self):
        fmt = self.format_combo.currentText()
        if not fmt: return
        
        self.btn_analyze.setEnabled(False)
        self.progress_bar.show()
        self.status_label.setText("Calcolo in corso...")
        self.table.setRowCount(0)
        self.detail_tree.clear()
        self.detail_tree.hide()
        self.current_stats = []
        
        self.worker = CoreAnalysisWorker(fmt)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.finished.connect(self.on_analysis_finished)
        self.worker.error.connect(self.on_analysis_error)
        self.worker.start()
        
    def on_analysis_finished(self, stats: list):
        self.current_stats = stats
        self.progress_bar.hide()
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"Completato! Trovati {len(stats)} Pokémon.")
        
        self.table.setRowCount(len(stats))
        for row, s in enumerate(stats):
            w_name = QTableWidgetItem(s.species_id.capitalize() if s.species_id else "Sconosciuto")
            
            w_usage = QTableWidgetItem()
            w_usage.setData(Qt.EditRole, float(f"{s.usage_percent:.1f}"))
            
            w_c2 = QTableWidgetItem("")
            w_c3 = QTableWidgetItem("")
            w_c4 = QTableWidgetItem("")
            
            self.table.setItem(row, 0, w_name)
            self.table.setItem(row, 1, w_usage)
            self.table.setItem(row, 2, w_c2)
            self.table.setItem(row, 3, w_c3)
            self.table.setItem(row, 4, w_c4)
            
            self.table.setCellWidget(row, 2, CoreCellWidget(s.global_cores.core_2))
            self.table.setCellWidget(row, 3, CoreCellWidget(s.global_cores.core_3))
            self.table.setCellWidget(row, 4, CoreCellWidget(s.global_cores.core_4))
            
            w_name.setData(Qt.UserRole, s)
            
        self.table.setSortingEnabled(True)
        self.table.sortItems(1, Qt.DescendingOrder)
        self.table.resizeRowsToContents()
            
    def on_analysis_error(self, err: str):
        self.progress_bar.hide()
        self.btn_analyze.setEnabled(True)
        self.status_label.setText("Errore!")
        QMessageBox.critical(self, "Errore", f"Errore durante l'analisi:\n{err}")

    def on_pokemon_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        name_item = self.table.item(row, 0)
        stats = name_item.data(Qt.UserRole)
        if not stats: return
        
        self.detail_tree.clear()
        self.detail_tree.show()
        
        root = QTreeWidgetItem(self.detail_tree, [f"Dettaglio Build per {stats.species_id.capitalize()}"])
        root.setExpanded(True)
        
        for idx, build in enumerate(stats.builds):
            b_node = QTreeWidgetItem(root, [f"Build #{idx+1} ({build.usage_percent:.1f}%)"])
            
            QTreeWidgetItem(b_node, ["Strumento", build.item])
            QTreeWidgetItem(b_node, ["Natura", build.nature])
            QTreeWidgetItem(b_node, ["Mosse", build.moves.replace(',', ', ')])
            
            core_node = QTreeWidgetItem(b_node, ["Core Dedicate"])
            
            c2_node = QTreeWidgetItem(core_node, ["Core 2", ""])
            c3_node = QTreeWidgetItem(core_node, ["Core 3", ""])
            c4_node = QTreeWidgetItem(core_node, ["Core 4", ""])
            
            self.detail_tree.setItemWidget(c2_node, 1, CoreCellWidget(build.cores.core_2))
            self.detail_tree.setItemWidget(c3_node, 1, CoreCellWidget(build.cores.core_3))
            self.detail_tree.setItemWidget(c4_node, 1, CoreCellWidget(build.cores.core_4))
            
            b_node.setExpanded(True)
