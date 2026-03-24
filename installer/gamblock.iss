; GAMBLOCK — Inno Setup Script
; Compile with Inno Setup 6: https://jrsoftware.org/isdl.php

#define AppName    "GAMBLOCK"
#define AppVersion "1.0.0"
#define AppURL     "https://gamblock.xyz"
#define AppExe     "GAMBLOCK.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\GAMBLOCK
DefaultGroupName=GAMBLOCK
AllowNoIcons=yes
OutputDir=..\dist\installer
OutputBaseFilename=GAMBLOCK_Setup
SetupIconFile=gamblock.ico
WizardImageFile=wizard_panel.bmp
WizardSmallImageFile=wizard_small.bmp
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\GAMBLOCK.exe
DisableProgramGroupPage=yes
ChangesEnvironment=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce

[Files]
Source: "..\dist\GAMBLOCK.exe";         DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\GAMBLOCK_Server.exe";  DestDir: "{app}"; Flags: ignoreversion
Source: "gamblock.ico";                 DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\GAMBLOCK";              Filename: "{app}\GAMBLOCK.exe"; IconFilename: "{app}\gamblock.ico"
Name: "{group}\Uninstall GAMBLOCK";    Filename: "{uninstallexe}"
Name: "{commondesktop}\GAMBLOCK";      Filename: "{app}\GAMBLOCK.exe"; IconFilename: "{app}\gamblock.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\GAMBLOCK.exe"; Description: "Launch GAMBLOCK"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallRun]
Filename: "schtasks"; Parameters: "/delete /tn ""SiteBlockerServer"" /f"; Flags: runhidden
Filename: "certutil"; Parameters: "-delstore Root ""Site Blocker CA"""; Flags: runhidden

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  ConfigPath: String;
begin
  ConfigPath := ExpandConstant('{commonappdata}\GAMBLOCK\config.json');
  if FileExists(ConfigPath) then
  begin
    MsgBox(
      'GAMBLOCK is still active.' + #13#10 + #13#10 +
      'You must enter all 100 passwords to deactivate GAMBLOCK before uninstalling.' + #13#10 + #13#10 +
      'Open GAMBLOCK and choose "Unblock" to proceed.',
      mbError, MB_OK
    );
    Result := False;
  end
  else
    Result := True;
end;
