import json
import urllib.request
import urllib.error
import urllib.parse
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QSpinBox, QPushButton, QProgressBar, QTextEdit, QMessageBox,
    QLineEdit
)
from PySide6.QtCore import QThread, Signal, Qt
from src.parser.showdown import parse_showdown_log
from database.repository_v2 import save_parsed_match_to_db_v2
from database.materialized_views import refresh_all_views

class MassImportWorker(QThread):
    progress = Signal(int, str)  # (current_count, message)
    finished = Signal()
    error = Signal(str)

    def __init__(self, format_id: str, count: int, user: str = "", user2: str = ""):
        super().__init__()
        self.format_id = format_id
        self.count = count
        self.user = urllib.parse.quote(user.strip()) if user else ""
        self.user2 = urllib.parse.quote(user2.strip()) if user2 else ""

    def run(self):
        try:
            self.progress.emit(0, f"Ricerca degli ultimi replays per il formato '{self.format_id}'...")
            
            replays_found = []
            
            def build_url(before=None):
                url = f"https://replay.pokemonshowdown.com/search.json?format={self.format_id}"
                if self.user:
                    url += f"&user={self.user}"
                if self.user2:
                    url += f"&user2={self.user2}"
                if before:
                    url += f"&before={before}"
                return url
                
            page_url = build_url()
            
            while len(replays_found) < self.count:
                req = urllib.request.Request(page_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                if not data:
                    break
                
                for item in data:
                    if len(replays_found) < self.count:
                        if item['id'] not in [r['id'] for r in replays_found]:
                            replays_found.append(item)
                    else:
                        break
                
                if len(replays_found) >= self.count or len(data) < 51:
                    break
                
                # Paginate using the last element's upload time
                last_upload_time = data[-1]['uploadtime']
                page_url = build_url(before=last_upload_time)

            total_to_import = len(replays_found)
            self.progress.emit(0, f"Trovati {total_to_import} replays. Inizio download e importazione...")
            
            for i, replay in enumerate(replays_found):
                replay_id = replay['id']
                log_url = f"https://replay.pokemonshowdown.com/{replay_id}.log"
                
                try:
                    self.progress.emit(i, f"[{i+1}/{total_to_import}] Download di {replay_id}...")
                    req = urllib.request.Request(log_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        log_content = response.read().decode('utf-8')
                    
                    self.progress.emit(i, f"[{i+1}/{total_to_import}] Parsing di {replay_id}...")
                    
                    # Skip replays without |showteam| — these are BO3 games played without OTS
                    # (marked with '!Force Open Team Sheets'), only containing |poke| tags
                    # with no ability/item/moves data. Importing them creates incomplete builds.
                    if "|showteam|" not in log_content:
                        self.progress.emit(i + 1, f"[{i+1}/{total_to_import}] Skip {replay_id} (nessun tag showteam — no OTS)")
                        continue
                    
                    parsed_data = parse_showdown_log(log_content)
                    save_parsed_match_to_db_v2(parsed_data, replay_id)
                    
                    self.progress.emit(i + 1, f"[{i+1}/{total_to_import}] Completato {replay_id}")
                except Exception as e:
                    self.progress.emit(i + 1, f"[{i+1}/{total_to_import}] Errore in {replay_id}: {str(e)}")

            self.progress.emit(total_to_import, "Importazione multipla terminata!")
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


class RefreshMVWorker(QThread):
    """
    Worker leggero che esegue il refresh delle Materialized Views
    in background dopo un bulk import, senza bloccare la UI.
    """
    finished = Signal(int)   # numero di secondi impiegati
    error    = Signal(str)

    def run(self):
        import time
        t0 = time.time()
        try:
            refresh_all_views(concurrently=False)
            elapsed = int(time.time() - t0)
            self.finished.emit(elapsed)
        except Exception as e:
            self.error.emit(str(e))


class MassImportWidget(QWidget):
    def __init__(self, parent_main=None):
        super().__init__()
        self.parent_main = parent_main

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Top controls
        top_layout = QHBoxLayout()
        
        top_layout.addWidget(QLabel("Formato:"))
        self.combo_format = QComboBox()
        self.combo_format.setEditable(True)
        
        current_year = datetime.datetime.now().year
        
        # Formati predefiniti popolari (inclusi i Champions dinamici)
        self.combo_format.addItems([
            f"gen9championsvgc{current_year}regma",
            f"gen9championsvgc{current_year}regmb",
            "gen9vgc2024regg",
            "gen9vgc2024regf",
            "gen9vgc2025regi",
            "gen9vgc2023regc",
            "gen9vgc2023regd"
        ])
        top_layout.addWidget(self.combo_format)

        top_layout.addWidget(QLabel("Giocatore 1:"))
        self.edit_user = QLineEdit()
        self.edit_user.setPlaceholderText("Es: 7upikid")
        top_layout.addWidget(self.edit_user)

        top_layout.addWidget(QLabel("Giocatore 2 (opz):"))
        self.edit_user2 = QLineEdit()
        self.edit_user2.setPlaceholderText("Es: jirkunow")
        top_layout.addWidget(self.edit_user2)

        top_layout.addWidget(QLabel("Numero Replays:"))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 999999999)
        self.spin_count.setValue(10)
        top_layout.addWidget(self.spin_count)

        self.btn_start = QPushButton("Avvia Importazione")
        self.btn_start.clicked.connect(self.start_import)
        top_layout.addWidget(self.btn_start)

        layout.addLayout(top_layout)

        # Progress bar and log
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_console = QTextEdit()
        self.log_console.setReadOnly(True)
        layout.addWidget(self.log_console)

        self.worker = None

    def start_import(self):
        format_id = self.combo_format.currentText().strip()
        count = self.spin_count.value()
        user = self.edit_user.text().strip()
        user2 = self.edit_user2.text().strip()

        if not format_id:
            QMessageBox.warning(self, "Attenzione", "Inserisci un formato valido!")
            return

        self.btn_start.setEnabled(False)
        self.combo_format.setEnabled(False)
        self.spin_count.setEnabled(False)
        self.edit_user.setEnabled(False)
        self.edit_user2.setEnabled(False)
        
        self.progress_bar.setMaximum(count)
        self.progress_bar.setValue(0)
        self.log_console.clear()
        self.log_console.append(f"Inizio operazione: Formato '{format_id}', Giocatore 1 '{user}', Giocatore 2 '{user2}', Quantità {count}")

        self.worker = MassImportWorker(format_id, count, user, user2)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.import_finished)
        self.worker.error.connect(self.import_error)
        self.worker.start()

    def update_progress(self, current, message):
        self.progress_bar.setValue(current)
        self.log_console.append(message)

    def import_finished(self):
        self.btn_start.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.spin_count.setEnabled(True)
        self.edit_user.setEnabled(True)
        self.edit_user2.setEnabled(True)
        QMessageBox.information(self, "Successo", "Importazione multipla completata!")
        if self.parent_main and hasattr(self.parent_main, 'list_view'):
            self.parent_main.list_view.load_replays()

        # Avvia il refresh automatico delle Materialized Views in background
        self.log_console.append("\n[MV] Aggiornamento statistiche in corso (background)...")
        self._mv_worker = RefreshMVWorker()
        self._mv_worker.finished.connect(self._on_mv_refreshed)
        self._mv_worker.error.connect(self._on_mv_error)
        self._mv_worker.start()

    def _on_mv_refreshed(self, elapsed_seconds: int):
        self.log_console.append(f"[MV] Statistiche aggiornate in {elapsed_seconds}s. Le analisi riflettono i nuovi replay.")

    def _on_mv_error(self, error_msg: str):
        # Il refresh MV è non-critico: logga l'errore senza mostrare popup
        self.log_console.append(f"[MV] Attenzione: aggiornamento statistiche fallito — {error_msg}")

    def import_error(self, error_msg):
        self.btn_start.setEnabled(True)
        self.combo_format.setEnabled(True)
        self.spin_count.setEnabled(True)
        self.edit_user.setEnabled(True)
        self.edit_user2.setEnabled(True)
        QMessageBox.critical(self, "Errore", f"Errore durante l'importazione:\n{error_msg}")
