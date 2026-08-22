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

    # Determina la cartella da cui è stato lanciato l'installer
    dest_dir = os.getcwd()
    print(f"\nLa cartella di destinazione sarà: {dest_dir}")

    # Determina il percorso dei file integrati (PyInstaller estrae in sys._MEIPASS)
    if not getattr(sys, 'frozen', False):
        print("Errore: questo installer deve essere eseguito come applicazione compilata.")
        input("Premi Invio per uscire...")
        return

    meipass = sys._MEIPASS
    source_exe = os.path.join(meipass, "Janalytics.exe")
    source_db = os.path.join(meipass, "vgc_replays.db")

    if not os.path.exists(source_exe):
        print("Errore: Janalytics.exe non trovato nel pacchetto di installazione.")
        input("Premi Invio per uscire...")
        return

    dest_exe = os.path.join(dest_dir, "Janalytics.exe")
    dest_db = os.path.join(dest_dir, "vgc_replays.db")

    try:
        print("\n[1/2] Estrazione dei file in corso...")
        shutil.copy2(source_exe, dest_exe)
        if os.path.exists(source_db):
            if not os.path.exists(dest_db): # Non sovrascrivere se esiste già
                shutil.copy2(source_db, dest_db)
            else:
                print("      - Database già presente, mantenuto per non perdere i dati.")
        print("      - File estratti con successo.")
    except Exception as e:
        print(f"Errore durante l'estrazione: {e}")
        input("Premi Invio per uscire...")
        return

    print("\n[2/2] Configurazione collegamento rapido")
    risposta = input("Vuoi creare un collegamento sul Desktop? (S/N) [S]: ").strip().lower()
    
    if risposta in ['', 's', 'si', 'y', 'yes']:
        try:
            desktop = winshell.desktop()
            shortcut_path = os.path.join(desktop, "Janalytics.lnk")
            create_shortcut(dest_exe, shortcut_path)
            print("      - Collegamento sul Desktop creato.")
        except Exception as e:
            print(f"      - Errore nella creazione del collegamento: {e}")

    print("\n" + "=" * 60)
    print(" Installazione completata con successo!")
    print(" Ora puoi avviare l'applicazione tramite l'eseguibile o il collegamento.")
    print("=" * 60)
    input("\nPremi Invio per uscire...")

if __name__ == "__main__":
    main()
