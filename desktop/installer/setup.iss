; 餐饮综合管理系统 v5.0 安装脚本
; Inno Setup 7

#define MyAppName "餐饮综合管理系统"
#define MyAppVersion "5.0.2"
#define MyAppPublisher "CateringMgt"
#define MyAppExeName "餐饮综合管理系统.exe"

[Setup]
AppId={{CATERING-MGT-5000-CCCC-BBBB-AAAA00000500}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=D:\Program Files\CateringMgt
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\installer_output
OutputBaseFilename=餐饮综合管理系统_Setup_v5.0.2
SetupIconFile=..\assets\app_icon.ico
Compression=lzma2/Max
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
CloseApplications=force
RestartApplications=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} v{#MyAppVersion}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "附加图标:"; Flags: dontinheritcheck

[Files]
Source: "..\dist\餐饮综合管理系统.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config.ini"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app_icon.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\app_icon.ico"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]

// 按进程名杀进程（最可靠，不依赖路径编码）
procedure KillAppByName();
var
  ResultCode: Integer;
begin
  // taskkill 按进程名强制杀，/T 连带子进程
  Exec(ExpandConstant('{cmd}'), '/C taskkill /IM "{#MyAppExeName}" /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  KillAppByName();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillAppByName();
  Result := True;
end;
