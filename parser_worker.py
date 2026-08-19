import requests
from PySide6.QtCore import QThread, Signal
# Importa la classe ShowdownParser e i modelli dati dal tuo script
from pokemon_parser import ShowdownParser, Match


class ParserWorker(QThread):
    finished = Signal(Match)
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()

            parser = ShowdownParser()
            match_data = parser.parse(response.text)

            self.finished.emit(match_data)
        except Exception as e:
            self.error.emit(str(e))
