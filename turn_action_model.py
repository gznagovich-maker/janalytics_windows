from PySide6.QtCore import QAbstractTableModel, Qt
from pokemon_parser import Match


class TurnActionModel(QAbstractTableModel):
    def __init__(self, match_data: Match = None):
        super().__init__()
        self._data = []
        self._headers = ["Turno", "Azione", "Attore", "Target", "Dettagli"]

        if match_data:
            # Appiattisce il dizionario dei turni in una lista lineare per la tabella
            for turn_num, actions in match_data.turns.items():
                for action in actions:
                    self._data.append((turn_num, action.action_type, action.actor, action.target, action.details))

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        return str(self._data[index.row()][index.column()])

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
        return None
