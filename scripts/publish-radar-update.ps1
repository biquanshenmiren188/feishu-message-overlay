param(
 [Parameter(Mandatory)][string]$Package,
 [Parameter(Mandatory)][string]$Version,
 [Parameter(Mandatory)][string]$SourceCommit,
 [string]$SshTarget='radar-tencent',
 [string]$IdentityFile='',
 [string]$KnownHostsFile='',
 [switch]$UseAdminConnection
)
$ErrorActionPreference='Stop'
if($Version -notmatch '^v\d{4}\.\d{2}\.\d{2}\.\d{1,6}$' -or $SourceCommit -notmatch '^[a-f0-9]{40}$'){throw 'Invalid release identity'}
$file=Get-Item -LiteralPath $Package
if($file.Length -le 0 -or $file.Length -gt 256MB){throw 'Invalid package size'}
$meta=@{Version=$Version;SourceCommit=$SourceCommit;Size=$file.Length;Sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
$start=[Diagnostics.ProcessStartInfo]::new('ssh')
$start.UseShellExecute=$false;$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
if($IdentityFile -and $KnownHostsFile){$start.ArgumentList.Add('-F');$start.ArgumentList.Add('none')}
foreach($arg in @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=20')){$start.ArgumentList.Add($arg)}
if($IdentityFile){$start.ArgumentList.Add('-i');$start.ArgumentList.Add([IO.Path]::GetFullPath($IdentityFile));$start.ArgumentList.Add('-o');$start.ArgumentList.Add('IdentitiesOnly=yes')}
if($KnownHostsFile){$start.ArgumentList.Add('-o');$start.ArgumentList.Add('UserKnownHostsFile='+[IO.Path]::GetFullPath($KnownHostsFile))}
$start.ArgumentList.Add($SshTarget)
if($UseAdminConnection){$start.ArgumentList.Add('sudo -n /usr/local/sbin/radar-update-receiver')}
else{$start.ArgumentList.Add('publish-desktop-update')}
$process=[Diagnostics.Process]::Start($start)
$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
try{
 $header=[Text.Encoding]::UTF8.GetBytes(($meta | ConvertTo-Json -Compress)+"`n")
 $stream=$process.StandardInput.BaseStream;$stream.Write($header)
 $inputFile=[IO.File]::OpenRead($file.FullName)
 try{$inputFile.CopyTo($stream)}finally{$inputFile.Dispose()}
 $stream.Close()
 if(!$process.WaitForExit(600000)){throw 'Publication timed out'}
 $result=$stdout.GetAwaiter().GetResult();$errorText=$stderr.GetAwaiter().GetResult()
 if($process.ExitCode -ne 0){throw ('Radar publication failed: '+$errorText)}
 $receipt=$result | ConvertFrom-Json
 if($receipt.published -ne $Version -or $receipt.sha256 -ne $meta.Sha256 -or $receipt.sourceCommit -ne $SourceCommit){throw 'Publication receipt mismatch'}
 Write-Output $result
}finally{if(!$process.HasExited){$process.Kill($true)};$process.Dispose()}
