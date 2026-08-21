import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QSplitter, QGroupBox, QProgressBar, QFormLayout, QLineEdit
)
from PySide6.QtCore import Qt
from database.connection import SessionLocal
from database.models import PokemonSpecies, PokemonBuild
from views.base_view import BaseHeaderWidget

class PokedexWidget(BaseHeaderWidget):
    def __init__(self):
        super().__init__("Esplora Pokédex / Meta")

        # Filtri
        filter_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Cerca per nome...")
        self.search_bar.textChanged.connect(self.load_data)
        filter_layout.addWidget(self.search_bar)
        self.add_layout(filter_layout)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Pokémon", "Forma"])
        self.tree.itemSelectionChanged.connect(self.on_pokemon_selected)
        splitter.addWidget(self.tree)

        # Right: Details
        self.details_group = QGroupBox("Dettagli e Statistiche Base")
        details_layout = QVBoxLayout(self.details_group)
        
        self.lbl_name = QLabel("Seleziona un Pokémon")
        self.lbl_name.setStyleSheet("font-size: 20px; font-weight: bold;")
        details_layout.addWidget(self.lbl_name)
        
        self.lbl_types = QLabel("Tipi: -")
        self.lbl_types.setStyleSheet("font-size: 14px; color: #bdc3c7;")
        details_layout.addWidget(self.lbl_types)
        
        # Stats Form
        self.stats_layout = QFormLayout()
        self.bars = {}
        for stat in ["hp", "atk", "def", "spa", "spd", "spe"]:
            bar = QProgressBar()
            bar.setMaximum(255)
            bar.setTextVisible(True)
            self.bars[stat] = bar
            self.stats_layout.addRow(stat.upper(), bar)
            
        details_layout.addLayout(self.stats_layout)
        
        self.lbl_usage = QLabel("Utilizzi totali nel DB: 0")
        self.lbl_usage.setStyleSheet("font-weight: bold; margin-top: 20px; font-size: 16px; color: #3498db;")
        details_layout.addWidget(self.lbl_usage)
        
        details_layout.addStretch()
        splitter.addWidget(self.details_group)
        
        splitter.setSizes([350, 450])
        self.add_content(splitter)
        
    def load_data(self):
        self.tree.clear()
        session = SessionLocal()
        try:
            q = session.query(PokemonSpecies)
            
            txt = self.search_bar.text().strip().lower()
            if txt:
                q = q.filter(PokemonSpecies.name.ilike(f"%{txt}%"))
                
            species_list = q.order_by(PokemonSpecies.num, PokemonSpecies.name).all()
            
            groups = {}
            for sp in species_list:
                base = sp.base_species if sp.base_species else sp.name
                if base not in groups:
                    groups[base] = []
                groups[base].append(sp)
                
            for base, forms in groups.items():
                parent = QTreeWidgetItem([base, ""])
                parent.setData(0, Qt.ItemDataRole.UserRole, forms[0].id)
                
                if len(forms) > 1:
                    for f in forms:
                        child = QTreeWidgetItem([f.name, f.forme or "Base"])
                        child.setData(0, Qt.ItemDataRole.UserRole, f.id)
                        parent.addChild(child)
                
                self.tree.addTopLevelItem(parent)
        finally:
            session.close()
            
    def on_pokemon_selected(self):
        items = self.tree.selectedItems()
        if not items:
            return
            
        pkmn_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        
        session = SessionLocal()
        try:
            sp = session.query(PokemonSpecies).filter_by(id=pkmn_id).first()
            if not sp:
                return
                
            self.lbl_name.setText(f"{sp.name} (#{sp.num})")
            
            types_str = " / ".join(sp.types) if sp.types else "Sconosciuto"
            self.lbl_types.setText(f"Tipi: {types_str}")
            
            stats = sp.base_stats if sp.base_stats else {}
            for stat_key, bar in self.bars.items():
                val = stats.get(stat_key, 0)
                bar.setValue(val)
                bar.setFormat(f"{val}")
                color = "#2ecc71" if val >= 100 else "#f39c12" if val >= 70 else "#e74c3c"
                bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; }}")
                
            # Usage
            usage_count = session.query(PokemonBuild).filter_by(species_id=pkmn_id).count()
            self.lbl_usage.setText(f"Utilizzi registrati in partita: {usage_count}")
                
        finally:
            session.close()

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()
