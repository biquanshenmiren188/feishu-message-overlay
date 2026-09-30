param([switch]$SelfContained,[string]$OutputDirectory="artifacts/app")
$ErrorActionPreference = 'Stop'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
$root = Split-Path -Parent $PSScriptRoot
if (!(Test-Path -LiteralPath (Join-Path $root 'bridge/node_modules/@larksuiteoapi/node-sdk/package.json'))) { throw 'Run npm ci --prefix bridge --ignore-scripts first (official SDK dependency)' }
dotnet run --project (Join-Path $root 'tests/Overlay.Core.Tests') -c Release
if ($LASTEXITCODE -ne 0) { throw 'Core checks failed' }
dotnet publish (Join-Path $root 'src/Overlay.App') -c Release -r win-x64 --self-contained $SelfContained.IsPresent -p:PublishSingleFile=true -o (Join-Path $root $OutputDirectory)
if ($LASTEXITCODE -ne 0) { throw 'Publish failed' }
$bridgeTarget = Join-Path $root (Join-Path $OutputDirectory "bridge")
New-Item -ItemType Directory -Path $bridgeTarget -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'bridge/main.mjs'),(Join-Path $root 'bridge/register.mjs'),(Join-Path $root 'bridge/discover.mjs'),(Join-Path $root 'bridge/group-discover.mjs'),(Join-Path $root 'bridge/diagnostic-fixture.mjs'),(Join-Path $root 'bridge/filter.mjs'),(Join-Path $root 'bridge/contract-fixture.mjs'),(Join-Path $root 'bridge/package.json') -Destination $bridgeTarget -Force
Copy-Item -LiteralPath (Join-Path $root 'bridge/node_modules') -Destination $bridgeTarget -Recurse -Force
$process = Start-Process -FilePath (Join-Path $root (Join-Path $OutputDirectory "FeishuMessageOverlay.exe")) -ArgumentList @('--smoke-test', ('"' + (Join-Path $root 'artifacts/verification') + '"')) -WindowStyle Hidden -PassThru -Wait
if ($process.ExitCode -ne 0) { throw 'WPF runtime smoke failed' }
$diagnostic = Start-Process -FilePath (Join-Path $root (Join-Path $OutputDirectory "FeishuMessageOverlay.exe")) -ArgumentList @('--diagnostic-contract-tests', ('"' + (Join-Path $root 'artifacts/verification/diagnostic-contract.txt') + '"')) -WindowStyle Hidden -PassThru -Wait
if ($diagnostic.ExitCode -ne 0) { throw 'Diagnostic contracts failed' }
# No installation, signing, certificate trust, startup registration, or system permissions.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$packagePath = Join-Path $root 'artifacts/FeishuMessageOverlay-win-x64.zip'
[System.IO.File]::Delete($packagePath)
# ZipFile reads with shared access; Compress-Archive unnecessarily locks SDK files.
[System.IO.Compression.ZipFile]::CreateFromDirectory((Join-Path $root $OutputDirectory), $packagePath)
