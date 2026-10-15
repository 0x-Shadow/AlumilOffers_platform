; AluminaOffers — professional Windows installer (Inno Setup 6)
; Build: iscc installer.iss   ->  Setup_AluminaOffers_1.1.0.exe

#define MyAppName "AluminaOffers"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "AluminaOffers"
#define MyAppURL "https://github.com/0x-Shadow/AlumilOffers_platform"
#define MyAppExeName "AluminaOffers.exe"

[Setup]
AppId={{8E4B1C2A-7F3D-4A9B-9C1E-5F2A9C4D8E01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\AluminaOffers
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=Setup_AluminaOffers_1.1.0
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=LICENSE
InfoBeforeFile=README.md
SetupIconFile=
UninstallDisplayName={#MyAppName} {#MyAppVersion}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
