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
    
    db_file = "vgc_replays.db"
    db_backup = "vgc_replays_backup.db"

    print("=" * 50)
    print(" 0. Preparazione di un Database pulito per l'Installer")
    print("=" * 50)
    if os.path.exists(db_file):
        print(f"Eseguo il backup di {db_file} in {db_backup}...")
        shutil.move(db_file, db_backup)
        
    print("Esecuzione di install.py per generare un DB nuovo con i metadata (Abilità, Mosse, ecc.)...")
    python_exec = sys.executable
    if os.path.exists(os.path.join("venv", "Scripts", "python.exe")):
        python_exec = os.path.join("venv", "Scripts", "python.exe")
    run_command([python_exec, "install.py"])

    print("\n" + "=" * 50)
    print(" 1. Compilazione dell'applicazione principale")
    print("=" * 50)
    
    # Specifica l'icona per l'app principale
    icon_path = os.path.join("assets", "logo", "icon.ico")
    
    pyinstaller_exec = os.path.join("venv", "Scripts", "pyinstaller")
    if not os.path.exists(pyinstaller_exec + ".exe"):
        pyinstaller_exec = "pyinstaller"

    main_build_cmd = [
        pyinstaller_exec,
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
    
    if not os.path.exists(app_exe):
        print("Errore: Janalytics.exe non trovato in dist/")
        sys.exit(1)
        
    if not os.path.exists(db_file):
        print(f"Attenzione: {db_file} non trovato. L'installer non includerà il DB precompilato.")
        db_to_pack = None
    else:
        db_to_pack = db_file

    print("\n" + "=" * 50)
    print(" 3. Compilazione dell'installer")
    print("=" * 50)

    installer_build_cmd = [
        pyinstaller_exec,
        "--noconfirm",
        "--onefile",
        "--console", # L'installer è un'app console
        "--name", "Janalytics_Installer",
        "--icon", icon_path,
        "--add-data", f"{app_exe}{os.pathsep}.",
        "--add-data", f"assets/logo{os.pathsep}assets/logo",
        "--add-data", f"resources/icons{os.pathsep}resources/icons",
    ]
    
    if db_to_pack:
        installer_build_cmd.extend(["--add-data", f"{db_to_pack}{os.pathsep}."])
        
    installer_build_cmd.append("installer.py")
    
    run_command(installer_build_cmd)
    
    print("\n" + "=" * 50)
    print(" 4. Ripristino del Database originale")
    print("=" * 50)
    if os.path.exists(db_file):
        os.remove(db_file)
    if os.path.exists(db_backup):
        print(f"Ripristino di {db_backup} in {db_file}...")
        shutil.move(db_backup, db_file)

    print("\n" + "=" * 50)
    print(" COMPILAZIONE COMPLETATA!")
    print(" L'installer si trova in: dist/Janalytics_Installer.exe")
    print("=" * 50)

if __name__ == "__main__":
    main()
