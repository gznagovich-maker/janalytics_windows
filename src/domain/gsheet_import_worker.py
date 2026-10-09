"""
gsheet_import_worker.py
=======================
QThread worker per l'importazione asincrona dei team dal Google Sheet.

Esecuzione in background:
  1. Per ogni foglio selezionato, scarica il CSV
  2. Per ogni riga con Pokepaste URL valido, scarica e parsa il paste
  3. Genera le build con EVs risolti (dal paste o auto-generati)
  4. Emette segnali di progresso e risultati alla UI

Pattern identico a MassImportWorker in views/mass_import_view.py.
"""

from PySide6.QtCore import QThread, Signal
from typing import List

from src.domain.gsheet_import_service import (
    SheetInfo, ImportedTeam,
    fetch_sheet_data, fetch_pokepaste_text, build_team_with_evs,
    SPREADSHEET_ID,
)


class GSheetImportWorker(QThread):
    """
    Worker che scarica e processa team dal Google Spreadsheet VGCPastes.

    Signals:
        progress(current, total, message): Aggiornamento stato elaborazione
        team_ready(ImportedTeam): Singolo team processato con successo
        finished(List[ImportedTeam]): Tutti i team processati
        error(str): Errore fatale che interrompe l'elaborazione
    """
    progress = Signal(int, int, str)
    team_ready = Signal(object)
    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        selected_sheets: List[SheetInfo],
        format_mode: str,
        spreadsheet_id: str = SPREADSHEET_ID,
    ):
        super().__init__()
        self.selected_sheets = selected_sheets
        self.format_mode = format_mode
        self.spreadsheet_id = spreadsheet_id
        self._is_cancelled = False

    def cancel(self):
        """Richiede la cancellazione del worker."""
        self._is_cancelled = True

    def run(self):
        all_teams: List[ImportedTeam] = []

        try:
            # Fase 1: Scarica i dati CSV da tutti i fogli selezionati
            all_rows = []
            for sheet in self.selected_sheets:
                if self._is_cancelled:
                    return

                self.progress.emit(0, 0, f"Scaricamento foglio '{sheet.name}'...")
                try:
                    rows = fetch_sheet_data(self.spreadsheet_id, sheet.gid)
                    for row in rows:
                        all_rows.append((sheet.name, row))
                except Exception as e:
                    self.progress.emit(
                        0, 0,
                        f"⚠ Errore nel foglio '{sheet.name}': {e}"
                    )

            total = len(all_rows)
            if total == 0:
                self.progress.emit(0, 0, "Nessun team trovato nei fogli selezionati.")
                self.finished.emit([])
                return

            self.progress.emit(0, total, f"Trovati {total} team. Inizio elaborazione...")

            # Fase 2: Per ogni riga, scarica il Pokepaste e genera la build
            for i, (sheet_name, row) in enumerate(all_rows):
                if self._is_cancelled:
                    return

                self.progress.emit(
                    i, total,
                    f"[{i+1}/{total}] {row.team_name} — download paste..."
                )

                try:
                    # Scarica il testo del Pokepaste
                    paste_text = fetch_pokepaste_text(row.pokepaste_url)

                    self.progress.emit(
                        i, total,
                        f"[{i+1}/{total}] {row.team_name} — parsing e calcolo EVs..."
                    )

                    # Genera le build con EVs risolti
                    members = build_team_with_evs(
                        paste_text=paste_text,
                        has_evs=row.has_evs,
                        format_mode=self.format_mode,
                    )

                    team = ImportedTeam(
                        team_name=row.team_name,
                        pokepaste_url=row.pokepaste_url,
                        members=members,
                        source_sheet=sheet_name,
                        has_evs=row.has_evs,
                    )

                    all_teams.append(team)
                    self.team_ready.emit(team)

                    self.progress.emit(
                        i + 1, total,
                        f"[{i+1}/{total}] ✓ {row.team_name} — "
                        f"{len(members)} Pokémon importati"
                    )

                except Exception as e:
                    self.progress.emit(
                        i + 1, total,
                        f"[{i+1}/{total}] ✗ {row.team_name} — Errore: {e}"
                    )

            # Completato
            imported = len(all_teams)
            skipped = total - imported
            msg = f"Importazione completata: {imported} team importati"
            if skipped > 0:
                msg += f", {skipped} saltati per errori"
            self.progress.emit(total, total, msg)
            self.finished.emit(all_teams)

        except Exception as e:
            self.error.emit(f"Errore fatale durante l'importazione: {e}")
