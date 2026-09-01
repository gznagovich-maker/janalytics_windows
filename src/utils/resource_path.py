import os
import sys

def get_resource_path(relative_path: str) -> str:
    """
    Ottiene il percorso assoluto della risorsa specificata.
    Gestisce correttamente i percorsi sia in ambiente di sviluppo 
    sia quando l'applicazione è pacchettizzata tramite PyInstaller.
    
    In PyInstaller 'onedir' (modalità directory), le risorse non vengono 
    estratte in una cartella temporanea, ma risiedono direttamente 
    nella cartella dell'eseguibile, che corrisponde a sys._MEIPASS.
    
    :param relative_path: Percorso relativo della risorsa (es. 'assets/logo/icon.ico')
    :return: Percorso assoluto pronto all'uso
    """
    try:
        # Quando pacchettizzato da PyInstaller (sia onedir che onefile)
        # i path partono da sys._MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # In fase di sviluppo, assume che il punto di partenza sia la root del progetto
        # (da dove lanci main.py)
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
