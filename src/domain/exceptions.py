"""
Eccezioni di dominio personalizzate per JAnalytics.
"""

class EntityNotFoundError(Exception):
    """
    Sollevata quando un'entità parsata (Specie, Mossa, Abilità, Strumento)
    non viene trovata nel database.
    """
    def __init__(self, entity_type: str, raw_name: str, context_pokemon: str):
        """
        :param entity_type: Tipo di entità mancante ('species', 'move', 'ability', 'item')
        :param raw_name: Il nome grezzo che ha fallito la validazione
        :param context_pokemon: Il nome del Pokémon su cui si è verificato l'errore
        """
        self.entity_type = entity_type
        self.raw_name = raw_name
        self.context_pokemon = context_pokemon
        super().__init__(f"Entità '{entity_type}' non trovata per '{raw_name}' sul Pokémon '{context_pokemon}'")
