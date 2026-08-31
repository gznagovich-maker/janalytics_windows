import os
import sys
import subprocess
import urllib.request
import json
import base64
import time

def create_directories():
    dirs = [
        "assets/icons",
        "assets/logo",
        "assets/styles",
        "resources/icons",
        "database"
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"✅ Directory verificata/creata: {d}")

def run_install_script():
    try:
        print("\n⏳ Esecuzione dell'inizializzazione database e download metadata base...")
        import install
        install.main()
        print("✅ setup iniziale completato con successo.")
    except Exception as e:
        print(f"❌ Errore durante l'esecuzione del setup iniziale: {e}")

def write_main_qss():
    qss_content = """/* ═══════════════════════════════════════════════════════════════════
   main.qss — JAnalytics VGC
   Design: "Hisui Goodra" — Deep Violet + Bronze / Steel Lavender
   ─────────────────────────────────────────────────────────────────
   Palette:
     BG_APP              #0C0C10   Nero con tinta viola profonda
     BG_SURFACE          #101014   Superficie base
     BG_SIDEBAR          #111118   Sidebar leggermente più chiara
     BG_TOPBAR           #0E0E14   Top bar con profondità
     BG_SURFACE_ELEVATED #181820   Acciaio scuro elevato
     BG_CARD             #1E1E28   Card in primo piano
     PRIMARY             #C49A3C   Bronzo/Oro — accento principale
     GOODRA_PURPLE       #A69ACA   Viola Goodra — menu icons
     GOODRA_PURPLE_LT    #C8BEE8   Viola chiaro — hover icons
     SECONDARY           #8577A8   Lavanda acciaio — secondario
     TERTIARY            #607080   Grigio acciaio blu — terziario
     TEXT_PRIMARY        #DEDAD4   Bianco caldo (patina metallica)
     TEXT_MUTED          #6E7285   Grigio freddo
   ─────────────────────────────────────────────────────────────────
   Typography:
     UI:   Segoe UI Variable / Inter / Segoe UI
     Data: Cascadia Code / Consolas (tabular rendering)
   ═══════════════════════════════════════════════════════════════ */

/* ── Global Reset ─────────────────────────────────────────────── */
* {
    font-family: 'Segoe UI Variable', 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #DEDAD4;
    outline: none;
}

QWidget {
    background-color: #0C0C10;
}

QMainWindow, QDialog {
    background-color: #0C0C10;
}

/* ── Top Bar ─────────────────────────────────────────────────── */
#top_bar {
    background-color: #0E0E14;
    border-bottom: 1px solid #2A2835;
}

/* ── Sidebar ─────────────────────────────────────────────────── */
#sidebar {
    background-color: #111118;
    border-right: 1px solid #2A2835;
}

#sidebar QPushButton {
    background-color: transparent;
    color: #A69ACA;
    border: none;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 500;
    border-radius: 7px;
    margin: 1px 6px;
    min-height: 42px;
    letter-spacing: 0.1px;
}

#sidebar QPushButton:hover {
    background-color: rgba(166, 154, 202, 0.10);
    color: #C8BEE8;
}

#sidebar QPushButton:checked {
    background-color: rgba(166, 154, 202, 0.13);
    color: #C8BEE8;
    font-weight: 600;
    border-left: 2px solid #A69ACA;
    padding-left: 12px;
}

#sidebar QPushButton:pressed {
    background-color: rgba(134, 120, 168, 0.22);
    color: #C8BEE8;
}

/* Separatore sezione nella sidebar */
#sidebar_divider {
    background-color: #1C1F26;
    max-height: 1px;
    margin: 6px 14px;
    border: none;
}

/* ── Stacked / Main Content ──────────────────────────────────── */
QStackedWidget {
    background-color: #0C0C10;
}

/* ── Frame e Superfici ───────────────────────────────────────── */
QFrame {
    background-color: transparent;
    border: none;
    border-radius: 0px;
}

QGroupBox {
    background-color: #141420;
    border: 1px solid #2A2835;
    border-radius: 10px;
    margin-top: 22px;
    padding-top: 6px;
    font-weight: 600;
    font-size: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 3px 8px;
    left: 10px;
    top: -2px;
    color: #C49A3C;
    background-color: #141420;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background-color: transparent;
}

/* ── Buttons ─────────────────────────────────────────────────── */
QPushButton {
    background-color: #141420;
    border: 1px solid #2A2835;
    color: #DEDAD4;
    padding: 7px 14px;
    border-radius: 7px;
    font-weight: 500;
    font-size: 13px;
    min-height: 34px;
    letter-spacing: 0.1px;
}

QPushButton:hover {
    background-color: #1E1E28;
    border-color: #C49A3C;
    color: #C49A3C;
}

QPushButton:pressed {
    background-color: #141420;
    border-color: #7A6025;
    color: #D4AA52;
}

QPushButton:disabled {
    background-color: #0E0E14;
    border-color: #1E1E28;
    color: #3A3850;
}

/* Primary — bronzo pieno (azioni principali) */
QPushButton[class="primary"] {
    background-color: #C49A3C;
    color: #000000;
    border: none;
    font-weight: 700;
    letter-spacing: 0.2px;
}

QPushButton[class="primary"]:hover {
    background-color: #D4AA52;
    color: #000000;
    border: none;
}

QPushButton[class="primary"]:pressed {
    background-color: #7A6025;
    color: #DEDAD4;
    border: none;
}

QPushButton[class="primary"]:disabled {
    background-color: #2A2315;
    color: #4A3E20;
    border: none;
}

/* Danger — rosso desaturato (azioni distruttive) */
QPushButton[class="danger"] {
    background-color: #8A3838;
    color: #DEDAD4;
    border: none;
    font-weight: 600;
}

QPushButton[class="danger"]:hover {
    background-color: #B04545;
    color: #FFFFFF;
    border: none;
}

QPushButton[class="danger"]:pressed {
    background-color: #5E2020;
    border: none;
}

QPushButton[class="danger"]:disabled {
    background-color: #2A1515;
    color: #4A2525;
    border: none;
}

/* ── Inputs ─────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #0A0B0D;
    color: #DEDAD4;
    border: 1px solid #1C1F26;
    border-radius: 5px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: rgba(196, 154, 60, 0.20);
    selection-color: #DEDAD4;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #C49A3C;
    background-color: #0D0F14;
}

QLineEdit:disabled, QTextEdit:disabled {
    background-color: #080909;
    color: #2E3240;
    border-color: #131519;
}

/* ── Tables ─────────────────────────────────────────────────── */
QTableWidget, QTreeWidget, QListWidget, QListView {
    background-color: #101014;
    color: #DEDAD4;
    border: 1px solid #2A2835;
    border-radius: 8px;
    gridline-color: transparent;
    alternate-background-color: #141420;
    selection-background-color: rgba(166, 154, 202, 0.13);
    selection-color: #C8BEE8;
    font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
    font-size: 13px;
    padding: 0px;
    outline: none;
}

QTableWidget::item, QTreeWidget::item, QListWidget::item {
    padding: 5px 10px;
    border: none;
    color: #DEDAD4;
}

QTableWidget::item:selected,
QTreeWidget::item:selected,
QListWidget::item:selected {
    background-color: rgba(166, 154, 202, 0.13);
    color: #C8BEE8;
}

QTableWidget::item:hover,
QTreeWidget::item:hover,
QListWidget::item:hover {
    background-color: rgba(166, 154, 202, 0.06);
}

QHeaderView::section {
    background-color: #181820;
    color: #6E7285;
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid #2A2835;
    font-family: 'Segoe UI Variable', 'Inter', 'Segoe UI', sans-serif;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}

QHeaderView::section:hover {
    background-color: #1E1E28;
    color: #C49A3C;
}

QHeaderView {
    background-color: #181820;
    border: none;
}

QHeaderView::section:first {
    border-top-left-radius: 6px;
}

QHeaderView::section:last {
    border-top-right-radius: 6px;
}

/* ── Scrollbars ──────────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #1C1F26;
    min-height: 32px;
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background: #C49A3C;
}

QScrollBar::handle:vertical:pressed {
    background: #7A6025;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 6px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #1C1F26;
    min-width: 32px;
    border-radius: 3px;
}

QScrollBar::handle:horizontal:hover {
    background: #C49A3C;
}

QScrollBar::handle:horizontal:pressed {
    background: #7A6025;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* ── Dropdowns (QComboBox) ───────────────────────────────────── */
QComboBox {
    background-color: #0A0B0D;
    color: #DEDAD4;
    border: 1px solid #1C1F26;
    border-radius: 5px;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 34px;
}

QComboBox:hover {
    border-color: #252932;
    background-color: #0D1014;
}

QComboBox:focus {
    border-color: #C49A3C;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}

QComboBox QAbstractItemView {
    background-color: #131519;
    color: #DEDAD4;
    border: 1px solid #252932;
    border-radius: 6px;
    selection-background-color: rgba(196, 154, 60, 0.12);
    selection-color: #C49A3C;
    outline: none;
    padding: 4px;
}

QComboBox QAbstractItemView::item {
    padding: 7px 10px;
    border-radius: 4px;
    min-height: 30px;
    font-size: 13px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: rgba(196, 154, 60, 0.07);
    color: #C49A3C;
}

/* ── Tabs ───────────────────────────────────────────────────── */
QTabWidget::pane {
    background-color: #0C0C10;
    border: 1px solid #2A2835;
    border-top: none;
    border-radius: 0px 0px 8px 8px;
}

QTabBar {
    background-color: transparent;
}

QTabBar::tab {
    background-color: transparent;
    color: #5E6575;
    padding: 8px 16px;
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    margin-right: 0px;
    font-weight: 500;
    font-size: 13px;
    min-width: 70px;
    min-height: 36px;
    border: none;
    border-bottom: 2px solid transparent;
}

QTabBar::tab:selected {
    background-color: transparent;
    color: #C49A3C;
    border-bottom: 2px solid #C49A3C;
    font-weight: 700;
}

QTabBar::tab:hover:!selected {
    color: #8577A8;
    border-bottom: 2px solid #8577A8;
}

/* ── Checkboxes ─────────────────────────────────────────────── */
QCheckBox, QRadioButton {
    spacing: 8px;
    font-size: 13px;
    color: #DEDAD4;
    background: transparent;
}

QCheckBox::indicator,
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #252932;
    background-color: #0A0B0D;
}

QCheckBox::indicator:hover,
QRadioButton::indicator:hover {
    border-color: #C49A3C;
}

QCheckBox::indicator:checked {
    background-color: #C49A3C;
    border-color: #C49A3C;
}

QRadioButton::indicator {
    border-radius: 8px;
}

QRadioButton::indicator:checked {
    background-color: #C49A3C;
    border-color: #C49A3C;
}

/* ── Sliders ────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 3px;
    background: #1C1F26;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #C49A3C;
    border: 2px solid #C49A3C;
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}

QSlider::handle:horizontal:hover {
    background: #D4AA52;
    border-color: #D4AA52;
}

QSlider::sub-page:horizontal {
    background: rgba(196, 154, 60, 0.35);
    border-radius: 2px;
}

/* ── SpinBox ───────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background-color: #0A0B0D;
    color: #DEDAD4;
    border: 1px solid #1C1F26;
    border-radius: 5px;
    padding: 6px 6px;
    font-size: 13px;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    min-height: 34px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #C49A3C;
}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #131519;
    border: none;
    width: 18px;
}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: rgba(196, 154, 60, 0.08);
}

/* ── Progress Bar ────────────────────────────────────────────── */
QProgressBar {
    background-color: #131519;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #C49A3C;
    border-radius: 3px;
}

/* ── ToolTip ─────────────────────────────────────────────────── */
QToolTip {
    background-color: #131519;
    color: #DEDAD4;
    border: 1px solid #252932;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 12px;
}

/* ── MessageBox ──────────────────────────────────────────────── */
QMessageBox {
    background-color: #0A0B0D;
}

QMessageBox QLabel {
    color: #DEDAD4;
    font-size: 13px;
}

/* ── Dialog ──────────────────────────────────────────────────── */
QDialog {
    background-color: #0A0B0D;
    border: 1px solid #1C1F26;
}

/* ── Splitter ────────────────────────────────────────────────── */
QSplitter::handle {
    background-color: #1C1F26;
    width: 1px;
    height: 1px;
}

QSplitter::handle:hover {
    background-color: #C49A3C;
}

/* ── ChartView ───────────────────────────────────────────────── */
QChartView {
    background-color: #101014;
    border: 1px solid #2A2835;
    border-radius: 8px;
}

/* ══════════════════════════════════════════════════════════════
   DEPTH & SHADOW SYSTEM
   Contrasto e profondità tra i layer della UI
   ══════════════════════════════════════════════════════════════ */

/* Panel content area — leggermente più chiara della sidebar */
#content_area {
    background-color: #0C0C10;
}

/* Card elevated — massima profondità visiva */
#card_elevated {
    background-color: #1E1E28;
    border: 1px solid #32304A;
    border-radius: 10px;
}

/* Separatore con glow viola sottile */
#sidebar_divider {
    background-color: #2A2835;
    max-height: 1px;
    margin: 6px 14px;
    border: none;
}
"""
    with open("assets/styles/main.qss", "w", encoding="utf-8") as f:
        f.write(qss_content)
    print("✅ assets/styles/main.qss creato con successo.")

def generate_svg_icons():
    # Estrazione da bundle EXE
    if hasattr(sys, '_MEIPASS'):
        src_icons = os.path.join(sys._MEIPASS, "resources", "icons")
        if os.path.exists(src_icons):
            import shutil
            shutil.copytree(src_icons, "resources/icons", dirs_exist_ok=True)
            print("✅ Icone SVG originali estratte dal pacchetto d'installazione.")
            return

    # Base template for a simple SVG icon
    svg_template = '''<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="{path_d}" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

    icons = [
        "arrow-down-tray",
        "arrow-down-on-square-stack",
        "beaker",
        "chart-bar",
        "film",
        "puzzle-piece",
        "trophy",
        "user-group"
    ]

    # Some basic generic paths to satisfy the requirement if actual SVGs are missing
    generic_path = "M12 2L2 22h20L12 2z" 
    
    for icon in icons:
        # Normal
        normal_path = f"resources/icons/{icon}.svg"
        if not os.path.exists(normal_path):
            with open(normal_path, "w", encoding="utf-8") as f:
                f.write(svg_template.format(path_d=generic_path, color="#A69ACA"))
        
        # Hover
        hover_path = f"resources/icons/{icon}-hover.svg"
        if not os.path.exists(hover_path):
            with open(hover_path, "w", encoding="utf-8") as f:
                f.write(svg_template.format(path_d=generic_path, color="#C8BEE8"))
                
    print("✅ Icone SVG di base in resources/icons/ verificate/create.")

def generate_logos():
    # Estrazione da bundle EXE
    if hasattr(sys, '_MEIPASS'):
        src_logo = os.path.join(sys._MEIPASS, "assets", "logo")
        if os.path.exists(src_logo):
            import shutil
            shutil.copytree(src_logo, "assets/logo", dirs_exist_ok=True)
            print("✅ Loghi originali estratti dal pacchetto d'installazione.")
            return

    # 1x1 transparent PNG base64 for placeholders if they don't exist
    b64_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    logos = [
        "assets/logo/icon.ico",
        "assets/logo/home.png",
        "assets/logo/J.png"
    ]
    for logo in logos:
        if not os.path.exists(logo):
            with open(logo, "wb") as f:
                f.write(base64.b64decode(b64_png))
    print("✅ Placeholder per i loghi verificati/creati in assets/logo/.")

def download_pokemon_icons():
    if not os.path.exists("pokedex.json"):
        print("⚠️ pokedex.json non trovato. Scaricamento icone Pokémon ignorato.")
        return
        
    try:
        # Import the centralized utility
        import sys
        if os.path.abspath("src") not in sys.path:
            sys.path.insert(0, os.path.abspath("src"))
        from src.utils.icon_utils import get_pokemon_icon_path
        
        with open("pokedex.json", "r", encoding="utf-8") as f:
            pokedex = json.load(f)
            
        print(f"\n⏳ Avvio scaricamento di icone per {len(pokedex)} Pokémon (potrebbe richiedere qualche minuto)...")
        downloaded = 0
        for key, data in pokedex.items():
            species_name = data.get("name", key)
            icon_path = f"assets/icons/{key}.png"
            if os.path.exists(icon_path):
                continue
                
            # Use the robust logic from icon_utils
            path_returned = get_pokemon_icon_path(species_name)
            if path_returned and os.path.exists(path_returned):
                downloaded += 1
                if downloaded % 50 == 0:
                    print(f"  - {downloaded} icone scaricate...")
                time.sleep(0.1) # Be nice to the API
                
        print(f"✅ Download completato: {downloaded} nuove icone scaricate in assets/icons/")
        
    except Exception as e:
        print(f"❌ Errore durante il processing del pokedex: {e}")

def main():
    print("=" * 60)
    print(" 🚀 INIZIALIZZAZIONE AMBIENTE FRESCO - VGC Replay Analyzer")
    print("=" * 60)
    
    create_directories()
    run_install_script()
    write_main_qss()
    generate_svg_icons()
    generate_logos()
    download_pokemon_icons()
    
    print("\n⏳ Seeding del Database V2 con i metadati JSON...")
    try:
        from database.connection import init_db
        init_db()
        from database.seed_v2_metadata import seed_v2_metadata
        seed_v2_metadata()
    except Exception as e:
        print(f"❌ Errore durante il seeding del DB V2: {e}")
    
    print("\n" + "=" * 60)
    print(" 🎉 Installazione ambiente fresco completata!")
    print(" Ora puoi avviare il programma principale con: python main.py")
    print("=" * 60)

if __name__ == "__main__":
    main()
