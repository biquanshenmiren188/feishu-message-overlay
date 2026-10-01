param([switch]$SelfContained,[string]$OutputDirectory="artifacts/app")
$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path -LiteralPath (Join-Path $root 'bridge/node_modules/@larksuiteoapi/node-sdk/package.json'))) { throw 'Run npm ci --prefix bridge --ignore-scripts first (official SDK dependency)' }
dotnet run --project (Join-Path $root 'tests/Overlay.Core.Tests') -c Release -p:BuildInParallel=false -p:UseSharedCompilation=false
if ($LASTEXITCODE -ne 0) { throw 'Core checks failed' }
dotnet publish (Join-Path $root 'src/Overlay.App') -c Release -r win-x64 --self-contained $SelfContained.IsPresent -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=$($SelfContained.IsPresent.ToString().ToLowerInvariant()) -p:BuildInParallel=false -p:UseSharedCompilation=false -m:1 -o (Join-Path $root $OutputDirectory)
if ($LASTEXITCODE -ne 0) { throw 'Publish failed' }
$bridgeTarget = Join-Path $root (Join-Path $OutputDirectory "bridge")
New-Item -ItemType Directory -Path $bridgeTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'bridge/main.mjs'),(Join-Path $root 'bridge/register.mjs'),(Join-Path $root 'bridge/discover.mjs'),(Join-Path $root 'bridge/group-discover.mjs'),(Join-Path $root 'bridge/diagnostic-fixture.mjs'),(Join-Path $root 'bridge/filter.mjs'),(Join-Path $root 'bridge/contract-fixture.mjs'),(Join-Path $root 'bridge/package.json') -Destination $bridgeTarget -Force
Copy-Item -LiteralPath (Join-Path $root 'bridge/node_modules') -Destination $bridgeTarget -Recurse -Force
# Only prune the owned publish copy, never source dependencies; retain licenses.
$dependencies=Join-Path $bridgeTarget 'node_modules'
Get-ChildItem -LiteralPath $dependencies -Recurse -File -Filter '*.d.ts' | Remove-Item -Force
$sdkPackage=Get-Content -LiteralPath (Join-Path $dependencies '@larksuiteoapi/node-sdk/package.json') -Raw | ConvertFrom-Json
if($sdkPackage.main -eq './lib/index.js'){
 foreach($relative in @('@larksuiteoapi/node-sdk/es','@types')){
  $unused=[IO.Path]::GetFullPath((Join-Path $dependencies $relative))
  if(!$unused.StartsWith([IO.Path]::GetFullPath($dependencies)+[IO.Path]::DirectorySeparatorChar)){throw 'Publish prune escaped dependencies'}
  if(Test-Path -LiteralPath $unused){Remove-Item -LiteralPath $unused -Recurse -Force}
 }
}
$smokeDirectory=Join-Path $root 'artifacts/verification/ci-smoke'
New-Item -ItemType Directory -Path $smokeDirectory -Force | Out-Null
$smokeReport=Join-Path $smokeDirectory 'ui-smoke.txt'
# Do not mistake a stale passing report for this process's result.
if(Test-Path -LiteralPath $smokeReport){Remove-Item -LiteralPath $smokeReport}
$process = Start-Process -FilePath (Join-Path $root (Join-Path $OutputDirectory "FeishuMessageOverlay.exe")) -ArgumentList @('--smoke-test', ('"' + $smokeDirectory + '"')) -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $smokeDirectory 'stdout.txt') -RedirectStandardError (Join-Path $smokeDirectory 'stderr.txt')
if ($process.ExitCode -ne 0) {
 foreach($report in @('ui-smoke.txt','stderr.txt','stdout.txt')){
  $reportPath=Join-Path $smokeDirectory $report
  if(Test-Path -LiteralPath $reportPath){Write-Output $report;Get-Content -LiteralPath $reportPath}
 }
 throw "WPF runtime smoke failed (exit $($process.ExitCode)); see artifacts/verification/ci-smoke"
}
if(!(Test-Path -LiteralPath $smokeReport) -or !(Get-Content -LiteralPath $smokeReport -Raw).StartsWith('PASS ')){throw 'WPF smoke did not produce its passing report'}
$diagnostic = Start-Process -FilePath (Join-Path $root (Join-Path $OutputDirectory "FeishuMessageOverlay.exe")) -ArgumentList @('--diagnostic-contract-tests', ('"' + (Join-Path $root 'artifacts/verification/diagnostic-contract.txt') + '"')) -WindowStyle Hidden -PassThru -Wait
if ($diagnostic.ExitCode -ne 0) { throw 'Diagnostic contracts failed' }
# No installation, signing, certificate trust, startup registration, or system permissions.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$packagePath = Join-Path $root 'artifacts/FeishuMessageOverlay-win-x64.zip'
[System.IO.File]::Delete($packagePath)
# ZipFile reads with shared access; Compress-Archive unnecessarily locks SDK files.
[System.IO.Compression.ZipFile]::CreateFromDirectory((Join-Path $root $OutputDirectory), $packagePath)

