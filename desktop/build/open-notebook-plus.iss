#define MyAppName "Open Notebook Plus"
#define MyAppVersion "0.8.94"
#define MyAppPublisher "Antman1526"
#define MyAppExeName "Open Notebook Plus.exe"

[Setup]
SourceDir=..\..
AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Open Notebook Plus
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Open-Notebook-Plus-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
Uninstallable=yes
CloseApplications=yes

[Files]
Source: "dist\Open Notebook Plus\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
