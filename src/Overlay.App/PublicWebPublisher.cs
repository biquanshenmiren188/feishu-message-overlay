using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Overlay.Core;
namespace Overlay.App;
internal sealed class PublicWebPublisher : IAsyncDisposable
{
    internal const string PublishPath="/radar/api/robot-push/publish";
    private const string Endpoint="https://47.79.37.237"+PublishPath;
    internal const string CloudControlEndpoint="https://leida.shenmiren.work/radar/api/robot-push/control";
    private static readonly JsonSerializerOptions Json=new(){PropertyNamingPolicy=JsonNamingPolicy.CamelCase};
    private static readonly HttpClient ControlHttp=new(new HttpClientHandler{AllowAutoRedirect=false,AutomaticDecompression=System.Net.DecompressionMethods.GZip}){Timeout=TimeSpan.FromSeconds(15)};
    private static string KeyPath=>Path.Combine(LocalStorage.DirectoryPath,"publisher-signing.dpapi");
    internal record ActionLink(string Label,string Url);
    internal record WebMessage(string Id,string GroupId,string SenderType,string SentAt,string Title,string Body,ActionLink[] Actions);
    private record Snapshot(bool Connected,string[] Groups,string PinGroup,WebMessage[] Messages,WebMessage? Pin);
    private readonly object gate=new();private Snapshot? desired;
    private readonly SemaphoreSlim changed=new(0,1);private readonly CancellationTokenSource stop=new();
    private readonly Task worker;private bool disposing;
    internal string State{get;private set;}="not_configured";
    internal int LastHttp{get;private set;}
    internal long SuccessfulBatches{get;private set;}
    internal long AcknowledgedMessages{get;private set;}
    internal DateTimeOffset? LastSuccess{get;private set;}
    internal int RemoteNormalCount{get;private set;}
    internal bool RemotePinned{get;private set;}
    internal static string Digest(string value)=>Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    internal static byte[] Canonical(string stamp,string nonce,byte[] body,string path=PublishPath)=>Encoding.UTF8.GetBytes($"robot-push-v1\nPOST\n{path}\n{stamp}\n{nonce}\n{Convert.ToHexStringLower(SHA256.HashData(body))}");
    internal static async Task<JsonDocument> SendControlAsync(string path,object payload,CancellationToken cancellationToken=default)
    {
        if(path is not ("/radar/api/robot-push/configure" or "/radar/api/robot-push/control"))throw new InvalidOperationException();
        var body=JsonSerializer.SerializeToUtf8Bytes(payload,Json);
        try
        {
            if(body.Length>8192)throw new InvalidOperationException();
            using var key=ECDsa.Create();LoadInto(key);
            var stamp=DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(System.Globalization.CultureInfo.InvariantCulture);
            var nonce=Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));
            // Only the existing signed cloud-reader route is migrated. Setup and publishing
            // remain separate; never follow an Access login redirect with signed requests.
            var endpoint=path=="/radar/api/robot-push/control"?CloudControlEndpoint:"https://47.79.37.237"+path;
            using var request=new HttpRequestMessage(HttpMethod.Post,endpoint){Content=new ByteArrayContent(body)};
            request.Content.Headers.ContentType=new("application/json");
            request.Headers.Add("X-Publish-Key",Convert.ToHexStringLower(SHA256.HashData(key.ExportSubjectPublicKeyInfo()))[..16]);
            request.Headers.Add("X-Publish-Time",stamp);request.Headers.Add("X-Publish-Nonce",nonce);
            request.Headers.Add("X-Publish-Signature",Convert.ToBase64String(key.SignData(Canonical(stamp,nonce,body,path),HashAlgorithmName.SHA256,DSASignatureFormat.Rfc3279DerSequence)));
            using var response=await ControlHttp.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,cancellationToken);
            if(!response.IsSuccessStatusCode)throw new HttpRequestException("Control request rejected",null,response.StatusCode);
            using var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);timeout.CancelAfter(TimeSpan.FromSeconds(10));
            await using var stream=await response.Content.ReadAsStreamAsync(timeout.Token);
            using var output=new MemoryStream();var buffer=new byte[4096];int count;
            var limit=path.EndsWith("/control",StringComparison.Ordinal)?8*1024*1024:32768;
            while((count=await stream.ReadAsync(buffer,timeout.Token))>0){if(output.Length+count>limit)throw new InvalidOperationException();output.Write(buffer,0,count);}
            return JsonDocument.Parse(output.ToArray());
        }
        finally{CryptographicOperations.ZeroMemory(body);}
    }
    internal static object Configure(string publicPath)
    {
        if(App.SmokeMode)throw new InvalidOperationException();
        using var key=ECDsa.Create(ECCurve.NamedCurves.nistP256);bool created=!File.Exists(KeyPath);
        if(created){var plain=key.ExportPkcs8PrivateKey();try{LocalStorage.AtomicWrite(KeyPath,CredentialVault.TransformPublisherKey(plain,true));}finally{CryptographicOperations.ZeroMemory(plain);}}
        else LoadInto(key);
        File.WriteAllText(publicPath,key.ExportSubjectPublicKeyInfoPem(),new UTF8Encoding(false));
        return new{configured=true,created,keyId=Convert.ToHexStringLower(SHA256.HashData(key.ExportSubjectPublicKeyInfo()))[..16],privateKeyExported=false};
    }
    private static void LoadInto(ECDsa key)
    {var plain=CredentialVault.TransformPublisherKey(File.ReadAllBytes(KeyPath),false);try{key.ImportPkcs8PrivateKey(plain,out _);}finally{CryptographicOperations.ZeroMemory(plain);}}
    private static WebMessage Project(IncomingMessage m)=>new(Digest(m.SourceId+"\n"+m.Id),Digest(m.SourceId),"bot",m.SentAt.ToUniversalTime().ToString("O"),m.Card?.Title??"",m.Card?.Body??m.Text,(m.Card?.Buttons??[]).Where(a=>MessageCardParser.SafeUrl(a.Url)).Take(8).Select(a=>new ActionLink(a.Label,a.Url)).ToArray());
    public PublicWebPublisher()
    {if(App.SmokeMode||CloudMode.Enabled||!File.Exists(KeyPath)){worker=Task.CompletedTask;return;}State="starting";worker=Task.Run(RunAsync);}
    public void Update(bool connected,IEnumerable<string> allowed,string pinGroup,IEnumerable<IncomingMessage> messages,IncomingMessage? pin)
    {
        if(disposing||worker.IsCompleted)return;
        var groups=allowed.Distinct(StringComparer.Ordinal).ToHashSet(StringComparer.Ordinal);
        var regular=messages.Where(m=>m.Kind==SenderKind.Bot&&groups.Contains(m.SourceId)&&m.SourceId!=pinGroup).Take(100).Select(Project).ToArray();
        var selected=groups.Contains(pinGroup)?Digest(pinGroup):"";
        var pinned=pin is {Kind:SenderKind.Bot}&&pin.SourceId==pinGroup&&groups.Contains(pin.SourceId)?Project(pin):null;
        lock(gate)desired=new(connected,groups.Select(Digest).Order(StringComparer.Ordinal).ToArray(),selected,regular,pinned);Signal();
    }
    public void Offline(){if(worker.IsCompleted)return;lock(gate){if(desired is not null)desired=desired with{Connected=false};}Signal();}
    private void Signal(){try{if(changed.CurrentCount==0)changed.Release();}catch(ObjectDisposedException){}catch(SemaphoreFullException){}}
    private async Task RunAsync()
    {
        try
        {
            using var key=ECDsa.Create();LoadInto(key);var keyId=Convert.ToHexStringLower(SHA256.HashData(key.ExportSubjectPublicKeyInfo()))[..16];
            using var http=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false}){Timeout=TimeSpan.FromSeconds(8)};
            var acknowledged=new HashSet<string>(StringComparer.Ordinal);string? pinAck=null;var next=DateTimeOffset.MinValue;var retry=2;
            while(!stop.IsCancellationRequested)
            {
                await changed.WaitAsync(TimeSpan.FromSeconds(20),stop.Token);var wait=next-DateTimeOffset.UtcNow;if(wait>TimeSpan.Zero)await Task.Delay(wait,stop.Token);
                Snapshot? current;lock(gate)current=desired;if(current is null)continue;
                current=current with{Messages=current.Messages.Where(m=>DateTimeOffset.TryParse(m.SentAt,out var sent)&&DateTimeOffset.UtcNow-sent<TimeSpan.FromMinutes(30)).ToArray()};
                var batch=current.Messages.Where(m=>!acknowledged.Contains(m.Id)).Take(8).ToArray();
                var payload=new{sourceConnected=current.Connected,allowedGroups=current.Groups,pinnedGroupId=current.PinGroup,normalIds=current.Messages.Select(m=>m.Id).ToArray(),messages=batch,pinned=current.Pin?.Id!=pinAck?current.Pin:null};
                var body=JsonSerializer.SerializeToUtf8Bytes(payload,Json);if(body.Length>512*1024){State="payload_limit";next=DateTimeOffset.UtcNow.AddSeconds(20);continue;}
                var stamp=DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString(System.Globalization.CultureInfo.InvariantCulture);var nonce=Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));
                using var request=new HttpRequestMessage(HttpMethod.Post,Endpoint){Content=new ByteArrayContent(body)};
                request.Content.Headers.ContentType=new("application/json");request.Headers.Add("X-Publish-Key",keyId);request.Headers.Add("X-Publish-Time",stamp);request.Headers.Add("X-Publish-Nonce",nonce);request.Headers.Add("X-Publish-Signature",Convert.ToBase64String(key.SignData(Canonical(stamp,nonce,body),HashAlgorithmName.SHA256,DSASignatureFormat.Rfc3279DerSequence)));
                try
                {
                    using var response=await http.SendAsync(request,stop.Token);LastHttp=(int)response.StatusCode;
                    if(!response.IsSuccessStatusCode){State="http_"+LastHttp;next=DateTimeOffset.UtcNow.AddSeconds(retry);retry=Math.Min(60,retry*2);Signal();continue;}
                    var data=await response.Content.ReadAsByteArrayAsync(stop.Token);if(data.Length>32768)throw new IOException();using var json=JsonDocument.Parse(data);var root=json.RootElement;
                    acknowledged=root.GetProperty("ackIds").EnumerateArray().Select(x=>x.GetString()??"").Take(100).ToHashSet(StringComparer.Ordinal);pinAck=root.GetProperty("pinAck").GetString();RemoteNormalCount=root.GetProperty("normalCount").GetInt32();RemotePinned=root.GetProperty("pinned").GetBoolean();AcknowledgedMessages+=root.GetProperty("accepted").GetInt32();SuccessfulBatches++;LastSuccess=DateTimeOffset.UtcNow;State=current.Connected?"connected":"source_offline";retry=2;next=DateTimeOffset.UtcNow.AddSeconds(2.1);
                    if(current.Messages.Any(m=>!acknowledged.Contains(m.Id)))Signal();
                }
                catch(Exception e) when(e is HttpRequestException or IOException or JsonException or TaskCanceledException)
                {if(stop.IsCancellationRequested)break;State="transport_error";next=DateTimeOffset.UtcNow.AddSeconds(retry);retry=Math.Min(60,retry*2);Signal();}
            }
        }
        catch(OperationCanceledException){}
        catch(Exception){State="publisher_unavailable";}
    }
    internal static void WriteContractVectors(string output)
    {
        using var key=ECDsa.Create(ECCurve.NamedCurves.nistP256);File.WriteAllText(output+".public.pem",key.ExportSubjectPublicKeyInfoPem(),new UTF8Encoding(false));var stamp=DateTimeOffset.UtcNow.ToUnixTimeSeconds().ToString();var group=Digest("fixture-group");var normal=Enumerable.Range(0,9).Select(i=>new WebMessage(Digest("fixture-"+i),group,"bot",DateTimeOffset.UtcNow.ToString("O"),"Synthetic","Synthetic test only\n完整文本保留",[new("Example","https://example.invalid/?x=%E4%B8%AD&y=2")])).ToArray();var keyId=Convert.ToHexStringLower(SHA256.HashData(key.ExportSubjectPublicKeyInfo()))[..16];
        object Vector(object payload){var body=JsonSerializer.SerializeToUtf8Bytes(payload,Json);var nonce=Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));return new{headers=new Dictionary<string,string>{{"X-Publish-Key",keyId},{"X-Publish-Time",stamp},{"X-Publish-Nonce",nonce},{"X-Publish-Signature",Convert.ToBase64String(key.SignData(Canonical(stamp,nonce,body),HashAlgorithmName.SHA256,DSASignatureFormat.Rfc3279DerSequence))}},body=Convert.ToBase64String(body)};}
        object Payload(WebMessage[] messages,string pinGroup="",WebMessage? pinned=null,bool connected=true)=>new{sourceConnected=connected,allowedGroups=new[]{group},pinnedGroupId=pinGroup,normalIds=messages.Select(m=>m.Id).ToArray(),messages,pinned};
        var vectors=new Dictionary<string,object>{{"valid",Vector(Payload([normal[0]]))},{"duplicate",Vector(Payload([normal[0]]))},{"batchLimit",Vector(Payload(normal))},{"human",Vector(Payload([normal[1] with{SenderType="user"}]))},{"pin",Vector(Payload([],group,normal[0]))},{"pinClearNormal",Vector(Payload([],group,null))},{"offline",Vector(Payload([],group,null,false))}};
        File.WriteAllText(output,JsonSerializer.Serialize(vectors,Json),new UTF8Encoding(false));
    }
    public async ValueTask DisposeAsync(){if(disposing)return;disposing=true;Offline();if(!worker.IsCompleted){await Task.Delay(500);stop.Cancel();Signal();await worker;}changed.Dispose();stop.Dispose();}
}
