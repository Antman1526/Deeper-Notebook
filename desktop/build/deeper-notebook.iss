#define MyAppName "Deeper Notebook"
#define MyAppVersion "0.8.114"
#define MyAppPublisher "Antman1526"
#define MyAppExeName "Deeper Notebook.exe"

[Setup]
SourceDir=..\..
AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Deeper Notebook
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Deeper-Notebook-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
Uninstallable=yes
CloseApplications=yes

[Files]
Source: "dist\Deeper Notebook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Stable AppId upgrades remove the retired launcher name from the existing folder.
Type: files; Name: "{app}\Open Notebook Plus.exe"
; Remove only the exact retired per-user Start Menu shortcut.
Type: files; Name: "{autoprograms}\Open Notebook Plus.lnk"
; The internal bundle is app-owned. Replacing it atomically prevents runtime
; residue from older releases (.orig/.pyc) surviving an in-place upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[UninstallDelete]
; Remove runtime residue only from the reserved app-owned internal tree.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
