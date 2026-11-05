using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using Overlay.Core;

namespace Overlay.App;

internal static class RadarUpdateTransportContract
{
    private sealed class Handler(Func<HttpRequestMessage,HttpResponseMessage> respond):HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)=>Task.FromResult(respond(request));
    }
    internal static async Task RunAsync(string directory)
    {
        Directory.CreateDirectory(directory);var checks=new List<string>();
        void Check(bool condition,string name){if(!condition)throw new InvalidOperationException(name);checks.Add(name);}
        var data=new byte[]{1,2,3,4};var tag="v2099.01.01.1";var name=$"FeishuMessageOverlay-{tag}-win-x64.zip";
        var release=new DesktopRelease(tag,name,new Uri(RadarDesktopUpdates.BaseUrl+tag+"/"+name),data.Length,Convert.ToHexString(SHA256.HashData(data)));
        var zip=Path.Combine(directory,"download.zip");
        using(var transport=new RadarUpdateTransport(new Handler(request=>
        {
            Check(request.RequestUri==release.Download,"only fixed radar package URL requested");
            Check(request.Headers.Authorization is null,"no GitHub or other bearer credentials sent");
            return new(HttpStatusCode.OK){Content=new ByteArrayContent(data)};
        })))
        {await transport.DownloadAsync(release,zip,CancellationToken.None);Check(File.ReadAllBytes(zip).SequenceEqual(data),"complete download verified");}
        File.Delete(zip);
        foreach(var failure in new[]{"forbidden","redirect","truncated","oversized","checksum","html"})
        {
            using var transport=new RadarUpdateTransport(new Handler(_=>failure switch
            {
                "forbidden"=>new(HttpStatusCode.Forbidden){Content=new StringContent("denied")},
                "redirect"=>new(HttpStatusCode.Redirect){Content=new StringContent("login")},
                "truncated"=>new(HttpStatusCode.OK){Content=new ByteArrayContent(data[..2])},
                "oversized"=>new(HttpStatusCode.OK){Content=new ByteArrayContent(new byte[10])},
                "html"=>new(HttpStatusCode.OK){Content=new StringContent("<html>login</html>")},
                _=>new(HttpStatusCode.OK){Content=new ByteArrayContent(new byte[4])}
            }));
            var rejected=false;
            try{await transport.DownloadAsync(release,zip,CancellationToken.None);}catch(Exception e) when(e is HttpRequestException or InvalidDataException){rejected=true;}
            Check(rejected&&!File.Exists(zip),failure+" rejected without retaining partial package");
        }
        using(var transport=new RadarUpdateTransport(new Handler(_=>throw new InvalidOperationException("must not contact unrelated host"))))
        {
            var rejected=false;try{await transport.DownloadAsync(release with{Download=new Uri("https://example.com/package.zip")},zip,CancellationToken.None);}catch(InvalidDataException){rejected=true;}
            Check(rejected,"unrelated URL rejected before network");
        }
        using(var transport=new RadarUpdateTransport(new Handler(request=>
        {
            Check(request.RequestUri!.AbsoluteUri==RadarDesktopUpdates.BaseUrl+"latest.json","check uses radar latest endpoint");
            return new(HttpStatusCode.OK){Content=new StringContent("<html>login</html>")};
        })))
        {
            var rejected=false;try{await transport.LatestAsync(tag,CancellationToken.None);}catch(InvalidDataException){rejected=true;}
            Check(rejected,"HTML metadata cannot become an update");
        }
        await File.WriteAllTextAsync(Path.Combine(directory,"radar-transport-contract.json"),JsonSerializer.Serialize(new{passed=true,checks}));
    }
}
