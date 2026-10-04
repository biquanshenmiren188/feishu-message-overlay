param([Parameter(Mandatory)][string]$Directory,[Parameter(Mandatory)][string]$Shortcut)
$ErrorActionPreference='Stop'
$install=[IO.Path]::GetFullPath($Directory)
$linkPath=[IO.Path]::GetFullPath($Shortcut)
$exe=Join-Path $install 'FeishuMessageOverlay.exe'
if(!(Test-Path -LiteralPath $exe -PathType Leaf)){throw 'Application executable missing'}
$powershell=Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/powershell.exe'
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut($linkPath)
if ((Test-Path -LiteralPath $linkPath) -and ($link.TargetPath -ne $exe) -and
    !(($link.TargetPath -eq $powershell) -and ($link.Description -eq 'FeishuMessageOverlay independent desktop launcher'))) {
    throw 'Existing unrelated shortcut preserved'
}
function Literal([string]$text){return "'"+$text.Replace("'","''")+"'"}
# Encodes only a fixed local launch command and file paths, never credentials.
# No execution-policy override, elevation, service, scheduled task or watcher.
$commandLine='"'+$exe+'"'
$command='Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='+(Literal $commandLine)+';CurrentDirectory='+(Literal $install)+'} | Out-Null'
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$link.TargetPath=$powershell
$link.Arguments='-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+$encoded
$link.WorkingDirectory=$install;$link.WindowStyle=7;$link.IconLocation=$exe+',0'
$link.Description='FeishuMessageOverlay independent desktop launcher';$link.Save()
[pscustomobject]@{installed=$true;shortcut=$linkPath;startsExpectedExe=$true;containsCredential=$false}
