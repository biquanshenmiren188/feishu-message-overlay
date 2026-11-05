using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using Overlay.Core;

namespace Overlay.App;

internal interface IDesktopUpdateTransport : IDisposable
{
    Task<DesktopRelease?> LatestAsync(string current,CancellationToken ct);
    Task DownloadAsync(DesktopRelease release,string zip,CancellationToken ct);
}

internal sealed class RadarUpdateTransport : IDesktopUpdateTransport
{
    // Reject redirects, including redirects to login pages or unrelated hosts.
    private readonly HttpClient client;
    internal RadarUpdateTransport(HttpMessageHandler? handler=null)
    {
        client=new(handler??new HttpClientHandler{AllowAutoRedirect=false}){Timeout=Timeout.InfiniteTimeSpan};
        client.DefaultRequestHeaders.UserAgent.ParseAdd("FeishuMessageOverlay/"+DesktopAutoUpdate.CurrentVersion[1..]);
    }
    public async Task<DesktopRelease?> LatestAsync(string current,CancellationToken ct)
    {
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromSeconds(30));
        using var request=new HttpRequestMessage(HttpMethod.Get,RadarDesktopUpdates.BaseUrl+"latest.json");
        request.Headers.CacheControl=new(){NoCache=true};
        using var response=await client.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,timeout.Token);
        response.EnsureSuccessStatusCode();
        using var data=new MemoryStream();
        await CopyBoundedAsync(await response.Content.ReadAsStreamAsync(timeout.Token),data,65536,timeout.Token);
        return RadarDesktopUpdates.SelectRelease(Encoding.UTF8.GetString(data.ToArray()),current);
    }
    public async Task DownloadAsync(DesktopRelease release,string zip,CancellationToken ct)
    {
        var expected=RadarDesktopUpdates.BaseUrl+release.Tag+"/FeishuMessageOverlay-"+release.Tag+"-win-x64.zip";
        if(release.Download.AbsoluteUri!=expected||release.Size<=0||release.Size>DesktopUpdates.MaximumDownload)throw new InvalidDataException("Invalid download destination");
        using var timeout=CancellationTokenSource.CreateLinkedTokenSource(ct);timeout.CancelAfter(TimeSpan.FromMinutes(5));
        try
        {
            using var response=await client.GetAsync(release.Download,HttpCompletionOption.ResponseHeadersRead,timeout.Token);
            response.EnsureSuccessStatusCode();
            if(response.Content.Headers.ContentLength is long size&&size!=release.Size)throw new InvalidDataException("Download size mismatch");
            await using(var output=File.Create(zip))
                await CopyBoundedAsync(await response.Content.ReadAsStreamAsync(timeout.Token),output,release.Size,timeout.Token);
            if(new FileInfo(zip).Length!=release.Size)throw new InvalidDataException("Incomplete download");
            DesktopUpdates.VerifyHash(zip,release.Sha256);
        }
        catch{if(File.Exists(zip))File.Delete(zip);throw;}
    }
    private static async Task CopyBoundedAsync(Stream source,Stream target,long limit,CancellationToken ct)
    {
        await using(source){var buffer=new byte[65536];long length=0;int n;while((n=await source.ReadAsync(buffer,ct))!=0){length+=n;if(length>limit)throw new InvalidDataException("Response too large");await target.WriteAsync(buffer.AsMemory(0,n),ct);}}
    }
    public void Dispose()=>client.Dispose();
    internal static async Task VerifySourceAsync(string outputDirectory)
    {
        Directory.CreateDirectory(outputDirectory);
        using var transport=new RadarUpdateTransport();
        var release=await transport.LatestAsync("v2000.01.01.1",CancellationToken.None)??throw new IOException("No release available");
        var zip=Path.Combine(outputDirectory,"package.zip");
        await transport.DownloadAsync(release,zip,CancellationToken.None);
        var manifest=DesktopUpdates.ExtractVerified(zip,Path.Combine(outputDirectory,"package"),release.Tag,release.Sha256,release.Size);
        await File.WriteAllTextAsync(Path.Combine(outputDirectory,"update-source-check.json"),JsonSerializer.Serialize(new{passed=true,release.Tag,release.Size,source="radar",signatureVerified=true,checksumVerified=true,filesVerified=manifest.Files.Count}));
    }
}
