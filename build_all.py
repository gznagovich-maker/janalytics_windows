import os
import subprocess
import sys
import shutil

def run_command(command):
    print(f"Esecuzione: {' '.join(command)}")
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        print("Errore durante l'esecuzione del comando.")
        sys.exit(1)

def main():
    # Assicuriamoci di essere nella directory root
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    print("=" * 50)
    print(" 1. Compilazione dell'applicazione principale")
    print("=" * 50)
    
    # Specifica l'icona per l'app principale
    icon_path = os.path.join("assets", "logo", "icon.ico")
    
    main_build_cmd = [
        "venv\\Scripts\\pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed", # Non mostrare la console in background
        "--name", "Janalytics",
        "--add-data", f"assets{os.pathsep}assets",
        "--icon", icon_path,
        "main.py"
    ]
    run_command(main_build_cmd)

    print("\n" + "=" * 50)
    print(" 2. Verifica dei file da includere nell'installer")
    print("=" * 50)
    
    app_exe = os.path.join("dist", "Janalytics.exe")
    db_file = "vgc_replays.db"
    
    if not os.path.exists(app_exe):
        print("Errore: Janalytics.exe non trovato in dist/")
        sys.exit(1)
        
    if not os.path.exists(db_file):
        print(f"Attenzione: {db_file} non trovato. L'installer non includerà il DB precompilato.")
        db_file = None

    print("\n" + "=" * 50)
    print(" 3. Compilazione dell'installer")
    print("=" * 50)

    installer_build_cmd = [
        "venv\\Scripts\\pyinstaller",
        "--noconfirm",
        "--onefile",
        "--console", # L'installer è un'app console
        "--name", "Janalytics_Installer",
        "--icon", icon_path,
        "--add-data", f"{app_exe}{os.pathsep}.",
    ]
    
    if db_file:
        installer_build_cmd.extend(["--add-data", f"{db_file}{os.pathsep}."])
        
    installer_build_cmd.append("installer.py")
    
    run_command(installer_build_cmd)

    print("\n" + "=" * 50)
    print(" COMPILAZIONE COMPLETATA!")
    print(" L'installer si trova in: dist/Janalytics_Installer.exe")
    print("=" * 50)

if __name__ == "__main__":
    main()
