; Script Inno Setup cho dự án Pixel Drive Capture
; Đóng gói ứng dụng Flask/PyInstaller Desktop App thành một file Setup .exe cài đặt duy nhất.

#define MyAppName "MCP Shopee Khải Hoàn"
#ifndef MyAppVersion
#define MyAppVersion "2.2.2"
#endif
#define MyAppPublisher "datdtpl-maker"
#define MyAppURL "https://github.com/datdtpl-maker/Pixel-Drive-Capture"
#define MyAppExeName "MCPShopee.exe"

[Setup]
AppId={{5D0B2E2D-531A-48FA-A7A2-7E74972BC63E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={userappdata}\Programs\MCPShopee
DisableDirPage=no
ChangesAssociations=yes
DisableProgramGroupPage=yes
; Chạy ở chế độ không cần quyền Administrator (chỉ cài cho user hiện tại)
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MCPShopeeSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app_icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\MCPShopee\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
