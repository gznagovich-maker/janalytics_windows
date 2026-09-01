; Script per Inno Setup
#define MyAppName "JAnalytics"
#define MyAppVersion "1.0"
#define MyAppPublisher "Jorkcorp"
#define MyAppExeName "JAnalytics.exe"
; Sostituisci il percorso con quello esatto della tua icona se ne hai una
; #define MyAppIcon "assets\logo\icon.ico"

[Setup]
; Un GUID univoco per l'applicazione. Generalo in Inno Setup (Tools -> Generate GUID) se vuoi usarne uno personalizzato.
AppId={{5E2B5A0C-8D4F-4C8E-A4E8-C1B5A2F0E8C4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
; Permessi utente: 'lowest' installa solo per l'utente corrente (AppData\Local\Programs). Usa 'admin' per Program Files.
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=JAnalytics_Setup
Compression=lzma

SolidCompression=yes
WizardStyle=modern
; SetupIconFile={#MyAppIcon} ; Scommenta se hai un'icona per l'installer

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copia l'eseguibile e TUTTE le sottocartelle generate da PyInstaller (dalla cartella JAnalytics dentro dist)
Source: "dist\JAnalytics\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Aggiungi certificati o altri file extra se necessario qui, anche se PyInstaller dovrebbe averli già inglobati.

[Icons]
; Menu Start
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Collegamento sul Desktop (selezionabile)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
