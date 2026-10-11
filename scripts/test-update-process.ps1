param([Parameter(Mandatory)][string]$AppDirectory)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$testRoot=Join-Path $repo ('artifacts/update-process-'+[guid]::NewGuid().ToString('N'))
$fixture=Join-Path $testRoot 'fixture'
dotnet publish (Join-Path $repo 'tests/Overlay.UpdateFixture') -c Release -r win-x64 --self-contained false -p:UseSharedCompilation=false -o $fixture | Out-Null
if($LASTEXITCODE -ne 0){throw 'Updater fixture build failed'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$results=@()
foreach($mode in @('healthy','crash','bad-receipt','corrupt-download')){
 $caseRoot=Join-Path $testRoot $mode
 $install=Join-Path $caseRoot 'install'
 $session=Join-Path $caseRoot 'updates/session'
 $package=Join-Path $session 'package'
 New-Item -ItemType Directory -Path $install,$package -Force | Out-Null
 Get-ChildItem -LiteralPath $fixture -File | Copy-Item -Destination $install
 Get-ChildItem -LiteralPath $fixture -File | Copy-Item -Destination $package
 [IO.File]::WriteAllText((Join-Path $install 'fixture-mode.txt'),'old')
 [IO.File]::WriteAllText((Join-Path $install 'storage-location.json'),'synthetic pointer, not real settings')
 [IO.File]::WriteAllText((Join-Path $package 'fixture-mode.txt'),$mode)
 & (Join-Path $PSScriptRoot 'write-update-manifest.ps1') -Directory $package -Version v2026.10.12.1
 $zip=Join-Path $session 'package.zip'
 [IO.Compression.ZipFile]::CreateFromDirectory($package,$zip)
 $state=Join-Path $caseRoot 'updates/state.json'
 [IO.File]::WriteAllText($state,'{"Enabled":true}')
 $old=Start-Process -FilePath (Join-Path $install 'FeishuMessageOverlay.exe') -WindowStyle Hidden -PassThru
 $oldTicks=$old.StartTime.ToUniversalTime().Ticks
 # Stop only the synthetic process this test created, before running the updater.
 Stop-Process -Id $old.Id -Force
 $old.WaitForExit()
 $plan=@{Install=$install;Package=$package;Tag='v2026.10.12.1';Zip=$zip;Hash=(Get-FileHash -LiteralPath $zip).Hash;Size=(Get-Item -LiteralPath $zip).Length;OldPid=$old.Id;OldStartTicks=$oldTicks;Receipt=(Join-Path $session 'healthy.json');Background=$true;StatePath=$state}
 if($mode -eq 'corrupt-download'){$plan.Hash='0'*64}
 $planPath=Join-Path $session 'plan.json'
 [IO.File]::WriteAllText($planPath,($plan|ConvertTo-Json))
 $runner=Start-Process -FilePath (Join-Path $AppDirectory 'FeishuMessageOverlay.exe') -ArgumentList @('--apply-desktop-update',('"'+$planPath+'"')) -WindowStyle Hidden -PassThru
 try{
  if(!$runner.WaitForExit(90000)){throw 'Updater process timeout'}
  $expected=if($mode -eq 'healthy'){0}else{1}
  if($runner.ExitCode -ne $expected){throw "Unexpected updater exit: $mode / $($runner.ExitCode)"}
  $deadline=[datetime]::UtcNow.AddSeconds(10)
  do{
   $launchPath=Join-Path $install 'launched.json'
   if(Test-Path -LiteralPath $launchPath){$launch=Get-Content -LiteralPath $launchPath -Raw|ConvertFrom-Json;if(Get-Process -Id $launch.pid -ErrorAction SilentlyContinue){break}}
   Start-Sleep -Milliseconds 100
  }while([datetime]::UtcNow -lt $deadline)
  $expectedMode=if($mode -eq 'healthy'){'healthy'}else{'old'}
  if($launch.mode -ne $expectedMode -or !(Get-Process -Id $launch.pid -ErrorAction SilentlyContinue)){throw "Incorrect running version after $mode; see $session"}
  $running=@(Get-Process -Name FeishuMessageOverlay -ErrorAction SilentlyContinue | Where-Object {$_.Path -and $_.Path.StartsWith($caseRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)})
  if($running.Count -ne 1){throw 'Failed child was not stopped before rollback'}
  if((Get-Content -LiteralPath (Join-Path $install 'storage-location.json') -Raw) -ne 'synthetic pointer, not real settings'){throw 'Settings pointer overwritten'}
  $saved=Get-Content -LiteralPath $state -Raw|ConvertFrom-Json
  if(($mode -eq 'healthy' -and $saved.FailedTag) -or ($mode -ne 'healthy' -and $saved.FailedTag -ne 'v2026.10.12.1')){throw 'Incorrect failed-version retry state'}
  $results+=@{case=$mode;passed=$true;running=$launch.mode;exitCode=$runner.ExitCode}
  Write-Output "PASS updater process: $mode, configuration preserved, expected process running"
 }finally{
  # Only synthetic executables inside this exact test workspace may be terminated.
  Get-Process -Name FeishuMessageOverlay -ErrorAction SilentlyContinue | Where-Object {$_.Path -and $_.Path.StartsWith($testRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)} | Stop-Process -Force
  if(!$runner.HasExited){Stop-Process -Id $runner.Id -Force}
 }
}
[IO.File]::WriteAllText((Join-Path $testRoot 'results.json'),($results|ConvertTo-Json))
Write-Output "Updater process report: $testRoot/results.json"
