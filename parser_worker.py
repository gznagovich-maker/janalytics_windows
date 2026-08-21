from PySide6.QtCore import QThread, Signal
from src.parser.showdown import ShowdownParser, parse_showdown_log
from database.repository import save_parsed_match_to_db


class ParserWorker(QThread):
    finished = Signal(object)  # Emette i dati parsati in caso di successo
    error = Signal(str)  # Emette il messaggio di errore in caso di fallimento

    def __init__(self, log_content: str, match_name: str):
        super().__init__()
        self.log_content = log_content
        self.match_name = match_name  # <-- Salviamo il nome personalizzato

    def run(self):
        try:
            parser = ShowdownParser()
            parsed_data = parse_showdown_log(self.log_content)

            # Salvataggio nel Database usando il nome scelto dall'utente
            save_parsed_match_to_db(parsed_data, self.match_name)

            self.finished.emit(parsed_data)
        except Exception as e:
            self.error.emit(str(e))