#define MyAppName "DigitalAfarin GSC Connector"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "DigitalAfarin"

[Setup]
AppId={{D26D4E2C-5589-4D32-9F1D-356D2D6FA103}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\DigitalAfarin GSC Connector
DefaultGroupName=DigitalAfarin
OutputDir=output
OutputBaseFilename=DigitalAfarin-GSC-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
WizardStyle=modern
UninstallDisplayName={#MyAppName}
DisableProgramGroupPage=yes

[Files]
Source: "stage\runtime\node.exe"; DestDir: "{app}\runtime"; Flags: ignoreversion
Source: "stage\dist\*"; DestDir: "{app}\dist"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "stage\node_modules\*"; DestDir: "{app}\node_modules"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "stage\package.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "stage\scripts\register-claude.mjs"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "launch-settings.vbs"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\DigitalAfarin GSC Connector"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch-settings.vbs"""; WorkingDir: "{app}"
Name: "{autodesktop}\DigitalAfarin GSC Connector"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch-settings.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: unchecked
Name: "registerclaude"; Description: "Register/update digitalafarin-gsc in Claude Desktop (backup existing config)"; Flags: unchecked

[Run]
Filename: "{app}\runtime\node.exe"; Parameters: """{app}\scripts\register-claude.mjs"" --update"; WorkingDir: "{app}"; Description: "Register the Claude Desktop MCP"; Flags: runhidden waituntilterminated; Tasks: registerclaude
Filename: "{sys}\wscript.exe"; Parameters: """{app}\launch-settings.vbs"""; Description: "Open DigitalAfarin GSC settings"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; User Google accounts and DPAPI-protected tokens under LOCALAPPDATA\DigitalAfarin\GSC
; are deliberately preserved. Claude config and unrelated MCPs are not modified.
