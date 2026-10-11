param([Parameter(Mandatory)][string]$Directory,[Parameter(Mandatory)][string]$Version)
$ErrorActionPreference='Stop'
if($Version -notmatch '^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]{1,6}$'){throw 'Invalid release version'}
$parts=$Version.Substring(1).Split('.')
$null=[datetime]::new([int]$parts[0],[int]$parts[1],[int]$parts[2])
$packageRoot=[IO.Path]::GetFullPath($Directory).TrimEnd([IO.Path]::DirectorySeparatorChar)
if(!(Test-Path -LiteralPath (Join-Path $packageRoot 'FeishuMessageOverlay.exe'))){throw 'Application missing'}
$files=[ordered]@{}
foreach($file in Get-ChildItem -LiteralPath $packageRoot -File -Recurse | Sort-Object FullName){
 $relative=$file.FullName.Substring($packageRoot.Length+1).Replace('\','/')
 if($relative -eq 'update-manifest.json'){continue}
 if($relative -eq 'storage-location.json' -or $file.Extension -eq '.dpapi' -or $file.Name -eq '.env'){throw 'Private configuration must not be packaged'}
 if($file.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Linked files must not be packaged'}
 $files[$relative]=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$json=@{Protocol=1;Version=$Version;Files=$files}|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $packageRoot 'update-manifest.json'),$json,[Text.UTF8Encoding]::new($false))
