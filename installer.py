import os
import sys
import shutil
import winshell
from win32com.client import Dispatch

def create_shortcut(target_exe, shortcut_path, description="VGC Replay Analyzer"):
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = target_exe
    shortcut.WorkingDirectory = os.path.dirname(target_exe)
    shortcut.IconLocation = target_exe
    shortcut.Description = description
    shortcut.save()

def main():
    print("=" * 60)
    print(" Installazione di Janalytics (VGC Replay Analyzer)")
    print("=" * 60)

    if not getattr(sys, 'frozen', False):
        print("Errore: questo installer deve essere eseguito come applicazione compilata.")
        input("Premi Invio per uscire...")
        return

    # 1. Chiedi il percorso di installazione
    default_path = os.path.join(os.getcwd(), "JAnalytics")
    user_path = input(f"\nInserisci il percorso di installazione [predefinito: {default_path}]: ").strip()
    install_dir = user_path if user_path else default_path

    # 2. Controllo se esiste già un'installazione
    if os.path.exists(install_dir) and os.path.exists(os.path.join(install_dir, "Janalytics.exe")):
        print(f"\nATTENZIONE: E' stata trovata un'installazione esistente in {install_dir}")
        sovrascrivi = input("Vuoi sovrascrivere l'installazione perdendo tutti i dati? (S/N) [N]: ").strip().lower()
        if sovrascrivi in ['s', 'si', 'y', 'yes']:
            try:
                print("Rimozione della vecchia installazione in corso...")
                shutil.rmtree(install_dir)
            except Exception as e:
                print(f"Errore durante la rimozione: {e}")
                input("Premi Invio per uscire...")
                return
        else:
            print("Installazione annullata.")
            input("Premi Invio per uscire...")
            return

    # 3. Chiedi per il collegamento sul desktop
    risposta_collegamento = input("\nVuoi creare un collegamento sul Desktop? (S/N) [S]: ").strip().lower()
    crea_collegamento = risposta_collegamento in ['', 's', 'si', 'y', 'yes']

    # Creazione della cartella
    if not os.path.exists(install_dir):
        os.makedirs(install_dir)

    print("\nCreazione dei file necessari all'applicazione...")
    
    meipass = sys._MEIPASS
    source_exe = os.path.join(meipass, "Janalytics.exe")
    source_db = os.path.join(meipass, "vgc_replays.db")

    if not os.path.exists(source_exe):
        print("Errore: Janalytics.exe non trovato nel pacchetto di installazione.")
        input("Premi Invio per uscire...")
        return

    dest_exe = os.path.join(install_dir, "Janalytics.exe")
    dest_db = os.path.join(install_dir, "vgc_replays.db")

    try:
        shutil.copy2(source_exe, dest_exe)
        if os.path.exists(source_db):
            shutil.copy2(source_db, dest_db)
        print("File creati con successo.")
    except Exception as e:
        print(f"Errore durante la creazione dei file: {e}")
        input("Premi Invio per uscire...")
        return

    # 4. Creazione collegamento
    if crea_collegamento:
        try:
            desktop = winshell.desktop()
            shortcut_path = os.path.join(desktop, "Janalytics.lnk")
            create_shortcut(dest_exe, shortcut_path)
            print("Collegamento sul Desktop creato.")
        except Exception as e:
            print(f"Errore nella creazione del collegamento: {e}")

    print("\n" + "=" * 60)
    print(" Installazione completata con successo!")
    print(f" Il programma è stato installato in: {install_dir}")
    print(" Ora puoi avviare l'applicazione tramite l'eseguibile o il collegamento.")
    print("=" * 60)
    input("\nPremi Invio per uscire...")

if __name__ == "__main__":
    main()
