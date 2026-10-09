"""
dashboard_worker.py
===================
Worker QThread per la Sheet Dashboard (il caricamento fa I/O di rete).
"""

from PySide6.QtCore import QThread, Signal

from src.domain.sheet_dashboard.dashboard_loader import load_dashboard
from src.domain.sheet_dashboard.replay_resolver import ensure_in_db


class SheetDashboardWorker(QThread):
    progress = Signal(int, int, str)      # (fatti, totale, messaggio)
    finished_ok = Signal(object)          # DashboardData
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            data = load_dashboard(self.url, lambda a, b, m: self.progress.emit(a, b, m))
            self.finished_ok.emit(data)
        except Exception as e:
            self.failed.emit(str(e))


class ReplayImportWorker(QThread):
    """Importa on-demand un replay nel DB interno prima di aprirlo nel viewer."""
    finished_ok = Signal(str)             # match_id
    failed = Signal(str)

    def __init__(self, slug: str, parent=None):
        super().__init__(parent)
        self.slug = slug

    def run(self):
        try:
            self.finished_ok.emit(ensure_in_db(self.slug))
        except Exception as e:
            self.failed.emit(str(e))
