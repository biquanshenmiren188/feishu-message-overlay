param([Parameter(Mandatory)][string]$Executable,[switch]$Background)
$ErrorActionPreference='Stop'
$full=[IO.Path]::GetFullPath($Executable)
if(!(Test-Path -LiteralPath $full -PathType Leaf)-or [IO.Path]::GetFileName($full)-ne 'FeishuMessageOverlay.exe'){throw 'Application executable missing'}
$command='"'+$full+'"'+$(if($Background){' --background'}else{''})
# Public local Windows provider, same user/session. No job/security configuration is modified.
$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$command;CurrentDirectory=[IO.Path]::GetDirectoryName($full)}
if($r.ReturnValue-ne 0){throw 'Desktop application launch failed'}
[pscustomobject]@{pid=$r.ProcessId;created=$true}
