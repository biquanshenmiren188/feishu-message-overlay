param([Parameter(Mandatory)][string]$ApplicationDirectory,[string]$RuntimeDirectory=(Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'FeishuWeixinRuntime'))
$ErrorActionPreference='Stop'
throw '微信ClawBot试验已按用户要求卸载；当前发行不提供微信转发安装或启动。'
$source=Join-Path (Split-Path -Parent $PSScriptRoot) 'weixin'
$runtime=[IO.Path]::GetFullPath($RuntimeDirectory)
if(Test-Path -LiteralPath $runtime){throw 'Use a new empty runtime directory; existing installation and bindings are preserved'}
$app=[IO.Path]::GetFullPath($ApplicationDirectory)
if(!(Test-Path -LiteralPath (Join-Path $app 'FeishuMessageOverlay.exe'))){throw 'Application executable missing'}
New-Item -ItemType Directory -Path $runtime | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $runtime -Recurse
$release='node-v22.22.3-win-x64'
$zip=Join-Path $runtime ($release+'.zip')
Invoke-WebRequest -Uri ('https://nodejs.org/dist/v22.22.3/'+$release+'.zip') -OutFile $zip
$manifest=(Invoke-WebRequest -Uri 'https://nodejs.org/dist/v22.22.3/SHASUMS256.txt').Content
$expected=($manifest -split "`n" | Where-Object {$_ -match ([regex]::Escape($release+'.zip')+'$')}) -split '\s+'
if($expected.Count-lt 2 -or (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()-ne $expected[0].ToLowerInvariant()){throw 'Official Node checksum mismatch'}
Expand-Archive -LiteralPath $zip -DestinationPath $runtime
$node=Join-Path $runtime ($release+'/node.exe');$npm=Join-Path $runtime ($release+'/node_modules/npm/bin/npm-cli.js')
Push-Location $runtime
try{& $node $npm ci --ignore-scripts --omit=optional --no-audit --no-fund --registry=https://registry.npmjs.org --userconfig=NUL;if($LASTEXITCODE-ne 0){throw 'Pinned dependency installation failed'};& $node (Join-Path $runtime 'apply-privacy-guard.mjs');if($LASTEXITCODE-ne 0){throw 'Privacy guard failed'}}finally{Pop-Location}
dotnet publish (Join-Path $runtime 'setup-ui/WeixinSetup.csproj') -c Release -o (Join-Path $runtime 'setup-ui-app') -p:UseSharedCompilation=false -m:1
if($LASTEXITCODE-ne 0){throw 'Local setup build failed'}
$root=Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'FeishuWeixinForwarder'
@{directory=$root;runtime=$runtime;host=(Join-Path $runtime 'setup-ui-app/WeixinSetup.exe')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $app 'weixin-location.json') -Encoding utf8
# Visible official QR interaction. Only the user scans/confirms. No forwarding is enabled by installation.
Start-Process -FilePath (Join-Path $runtime 'setup-ui-app/WeixinSetup.exe') -ArgumentList ('"'+$runtime+'"')
