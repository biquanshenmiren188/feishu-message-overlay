using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using Overlay.Core;

namespace Overlay.App;

internal sealed class GitHubUpdateTransport : IDisposable
{
    private readonly HttpClient client=new(new HttpClientHandler{AllowAutoRedirect=true}){Timeout=TimeSpan.FromSeconds(20)};
    internal GitHubUpdateTransport()
    {
        client.DefaultRequestHeaders.UserAgent.ParseAdd("FeishuMessageOverlay/"+DesktopAutoUpdate.CurrentVersion[1..]);
        client.DefaultRequestHeaders.Accept.ParseAdd("application/vnd.github+json");
    }
    internal async Task<(string Json,bool Private)> LatestAsync(CancellationToken ct)
    {
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(30));
        using var response=await client.GetAsync($"https://api.github.com/repos/{DesktopUpdates.Repository}/releases/latest",HttpCompletionOption.ResponseHeadersRead,timeout.Token);
        if(response.StatusCode==HttpStatusCode.NotFound)
        {
            // Existing gh login stays in its own credential store. Never export a token.
            var json=await RunGitHubAsync(["api",$"repos/{DesktopUpdates.Repository}/releases/latest"],timeout.Token);
            return (json,true);
        }
        response.EnsureSuccessStatusCode();
        using var metadata=new MemoryStream();
        await CopyBoundedAsync(await response.Content.ReadAsStreamAsync(timeout.Token),metadata,1024*1024,timeout.Token);
        return (Encoding.UTF8.GetString(metadata.ToArray()),false);
    }
    internal async Task DownloadAsync(DesktopRelease release,bool isPrivate,string zip,CancellationToken ct)
    {
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromMinutes(5));
        if(isPrivate)
        {
            // gh handles authenticated asset redirects without sharing credentials with this app.
            var folder=Path.GetDirectoryName(zip)!;
            var downloaded=Path.Combine(folder,release.AssetName);
            await RunGitHubAsync(["release","download",release.Tag,"--repo",DesktopUpdates.Repository,"--pattern",release.AssetName,"--dir",folder],timeout.Token,downloaded,release.Size);
            if(new FileInfo(downloaded).Length!=release.Size)throw new IOException("Downloaded asset size mismatch");
            File.Move(downloaded,zip);
            return;
        }
        using var download=await client.GetAsync(release.Download,HttpCompletionOption.ResponseHeadersRead,timeout.Token);
        download.EnsureSuccessStatusCode();
        var final=download.RequestMessage!.RequestUri!;
        if(final.Scheme!="https"||!(final.Host is "github.com" or "release-assets.githubusercontent.com" or "objects.githubusercontent.com"))throw new IOException("Unexpected download host");
        await using var output=File.Create(zip);
        await CopyBoundedAsync(await download.Content.ReadAsStreamAsync(timeout.Token),output,release.Size,timeout.Token);
    }
    private static async Task CopyBoundedAsync(Stream source,Stream target,long limit,CancellationToken ct)
    {
        await using(source){var buffer=new byte[65536];long length=0;int n;while((n=await source.ReadAsync(buffer,ct))!=0){length+=n;if(length>limit)throw new IOException("Download too large");await target.WriteAsync(buffer.AsMemory(0,n),ct);}}
    }
    private static string FindGitHubCli()
    {
        foreach(var directory in (Environment.GetEnvironmentVariable("PATH")??"").Split(Path.PathSeparator))
        {
            if(!Path.IsPathFullyQualified(directory.Trim('"')))continue;
            var path=Path.Combine(directory.Trim('"'),"gh.exe");
            if(File.Exists(path))return path;
        }
        throw new IOException("Private release requires an existing GitHub CLI login");
    }
    private static async Task<string> RunGitHubAsync(string[] arguments,CancellationToken ct,string? download=null,long maximum=0)
    {
        var start=new ProcessStartInfo(FindGitHubCli()){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
        start.Environment["GH_PROMPT_DISABLED"]="1";start.Environment["GIT_TERMINAL_PROMPT"]="0";start.Environment["GH_HOST"]="github.com";
        foreach(var argument in arguments)start.ArgumentList.Add(argument);
        using var process=Process.Start(start)??throw new IOException("GitHub CLI unavailable");
        void Stop(){try{if(!process.HasExited)process.Kill(entireProcessTree:true);}catch(InvalidOperationException){}catch(System.ComponentModel.Win32Exception){}}
        using var cancel=ct.Register(Stop);
        async Task<string> ReadAsync(StreamReader reader,int limit)
        {
            var result=new StringBuilder();var buffer=new char[4096];int count;
            while((count=await reader.ReadAsync(buffer.AsMemory(),ct))!=0)
            {
                if(result.Length+count>limit){Stop();throw new IOException("GitHub CLI response too large");}
                result.Append(buffer,0,count);
            }
            return result.ToString();
        }
        var stdout=ReadAsync(process.StandardOutput,1024*1024);var stderr=ReadAsync(process.StandardError,65536);
        try
        {
            while(!process.HasExited)
            {
                if(download is not null&&File.Exists(download)&&new FileInfo(download).Length>maximum)throw new IOException("Download too large");
                await Task.Delay(100,ct);
            }
            await Task.WhenAll(stdout,stderr);
            if(process.ExitCode!=0)throw new IOException("GitHub release unavailable; check existing CLI login");
            return await stdout;
        }
        finally
        {
            Stop();await process.WaitForExitAsync(CancellationToken.None);
            try{await Task.WhenAll(stdout,stderr);}catch{} // Observe cancelled or bounded reader failures.
        }
    }
    public void Dispose()=>client.Dispose();

    internal static async Task VerifySourceAsync(string outputDirectory)
    {
        Directory.CreateDirectory(outputDirectory);
        using var transport=new GitHubUpdateTransport();
        var metadata=await transport.LatestAsync(CancellationToken.None);
        var release=DesktopUpdates.SelectRelease(metadata.Json,"v2000.01.01.1")??throw new IOException("No release available");
        var zip=Path.Combine(outputDirectory,"package.zip");
        await transport.DownloadAsync(release,metadata.Private,zip,CancellationToken.None);
        DesktopUpdates.VerifyHash(zip,release.Sha256);
        await File.WriteAllTextAsync(Path.Combine(outputDirectory,"update-source-check.json"),System.Text.Json.JsonSerializer.Serialize(new{passed=true,release.Tag,release.Size,privateRepository=metadata.Private,checksumVerified=true}));
    }
}
