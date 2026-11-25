; Europa — professional Windows installer (Inno Setup 6)
; Build: iscc /DMyAppVersion=1.5.2 installer.iss
; CI passes the version read from app.py, so the installer never drifts.

#ifndef MyAppVersion
  #define MyAppVersion "1.5.2"
#endif
#define MyAppName "Europa"
#define MyAppPublisher "Europa"
#define MyAppURL "https://github.com/0x-Shadow/AlumilOffers_platform"
#define MyAppExeName "Europa.exe"

[Setup]
AppId={{8E4B1C2A-7F3D-4A9B-9C1E-5F2A9C4D8E01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; User data lives in %APPDATA%\Europa, so updates/uninstalls never touch it.
DefaultDirName={localappdata}\Europa
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
; Clean rename: new installs go to their own Europa folder; old data is migrated
; by the app itself on first launch, so the old folder is intentionally preserved.
UsePreviousAppDir=no
DisableDirPage=auto
DisableProgramGroupPage=yes
; Allow the in-app updater to install silently while the app is running.
CloseApplications=yes
RestartApplications=no
OutputDir=.
OutputBaseFilename=Setup_Europa_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
SetupIconFile=
UninstallDisplayName={#MyAppName} {#MyAppVersion}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; Remove shortcuts from the old AluminaOffers name; its install folder (and any
; old data in it) is left untouched for the app's one-time data migration.
[InstallDelete]
Type: files; Name: "{autoprograms}\AluminaOffers.lnk"
Type: files; Name: "{autodesktop}\AluminaOffers.lnk"
Type: filesandordirs; Name: "{autoprograms}\AluminaOffers"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
