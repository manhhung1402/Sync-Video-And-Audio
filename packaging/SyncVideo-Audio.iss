#define MyAppName "SyncVideo-Audio"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "YudgnuH (Nguyễn Duy Hưng)"
#define MyAppExeName "SyncVideo-Audio.exe"

[Setup]
AppId={{B45B6B80-7EB4-4F58-BEC6-7C9BD3D9E5F8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist-installer
OutputBaseFilename=SyncVideo-Audio-Setup-{#MyAppVersion}
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest

[Files]
Source: "..\dist-full\SyncVideo-Audio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\logo.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\logo.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở {#MyAppName}"; Flags: nowait postinstall skipifsilent
