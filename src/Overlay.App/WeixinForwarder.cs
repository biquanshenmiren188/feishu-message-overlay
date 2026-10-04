using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using System.Diagnostics;
using Overlay.Core;
namespace Overlay.App;
// Receives only newly accepted real bot messages; never enumerates display/history.
internal sealed class WeixinForwarder:IAsyncDisposable
{
    private sealed record Pending(IncomingMessage Message,IncomingMessage? Pinned,bool IsPinnedUpdate);
    private readonly Channel<Pending> queue=Channel.CreateBounded<Pending>(64);
    private readonly HttpClient http;
    private readonly CancellationTokenSource stop=new();
    private readonly Task runner;
    private bool configured;private volatile bool enabled;
    private long generation;
    internal string State {get;private set;}="未配置";
    internal bool Enabled=>enabled;
    internal long Sent {get;private set;}
    internal long Failed {get;private set;}
    internal WeixinForwarder(HttpMessageHandler? fixture=null,bool fixtureEnabled=false){http=fixture is null?new(new HttpClientHandler{UseProxy=false}):new(fixture);http.BaseAddress=new Uri("http://127.0.0.1:18882");http.Timeout=TimeSpan.FromSeconds(15);configured=fixture is not null;enabled=configured&&fixtureEnabled;runner=Task.Run(RunAsync);}
    internal void QueueAccepted(IncomingMessage message,IncomingMessage? pinned=null,bool isPinnedUpdate=false)
    {var now=DateTimeOffset.UtcNow;if(enabled&&message.Kind==SenderKind.Bot&&now-message.SentAt<TimeSpan.FromMinutes(2)&&message.SentAt<=now.AddSeconds(30))queue.Writer.TryWrite(new(message,pinned,isPinnedUpdate));}
    internal void Reset(){Interlocked.Increment(ref generation);while(queue.Reader.TryRead(out _)){} }
    internal async Task<bool> SetEnabledAsync(bool value)
    {
        if(!configured)return false;
        try{using var response=await http.PostAsync(value?"/enable":"/disable",null,stop.Token);enabled=response.IsSuccessStatusCode&&value;State=enabled?"已开启":value?"等待微信测试消息":"已关闭";if(!enabled)Reset();return response.IsSuccessStatusCode;}
        catch(Exception e) when(e is HttpRequestException or OperationCanceledException){State="微信网关不可用";enabled=false;Reset();return false;}
    }
    private async Task RunAsync()
    {
        try{
            if(!configured){
            if(App.SmokeMode)return;
            var marker=Path.Combine(AppContext.BaseDirectory,"weixin-location.json");if(!File.Exists(marker))return;
            using var location=JsonDocument.Parse(File.ReadAllText(marker));var root=Path.GetFullPath(location.RootElement.GetProperty("directory").GetString()!);
            var own=Path.GetFullPath(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"AppData","Local","FeishuWeixinForwarder"));
            if(!string.Equals(root,own,StringComparison.OrdinalIgnoreCase))return;
            using var config=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"gateway.json")));
            http.DefaultRequestHeaders.Authorization=new AuthenticationHeaderValue("Bearer",config.RootElement.GetProperty("gateway").GetProperty("auth").GetProperty("token").GetString());
            configured=true;
            try{using var response=await http.GetAsync("/status",stop.Token);using var status=JsonDocument.Parse(await response.Content.ReadAsStringAsync(stop.Token));enabled=response.IsSuccessStatusCode&&status.RootElement.TryGetProperty("enabled",out var flag)&&flag.GetBoolean();State=enabled?"已开启":"已关闭 / 等待微信测试";}
            catch(Exception e) when(e is HttpRequestException or OperationCanceledException){
                State="微信网关启动中";
                if(location.RootElement.TryGetProperty("host",out var host)&&location.RootElement.TryGetProperty("runtime",out var runtime)){
                    var executable=Path.GetFullPath(host.GetString()!);var folder=Path.GetFullPath(runtime.GetString()!);
                    var user=Path.GetFullPath(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile))+Path.DirectorySeparatorChar;
                    if(executable.StartsWith(user,StringComparison.OrdinalIgnoreCase)&&folder.StartsWith(user,StringComparison.OrdinalIgnoreCase)&&Path.GetFileName(executable)=="WeixinSetup.exe"&&File.Exists(executable)){
                        var info=new ProcessStartInfo(executable){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=folder};info.ArgumentList.Add("--gateway-host");info.ArgumentList.Add(folder);info.ArgumentList.Add(root);using var child=Process.Start(info);
                        for(var attempt=0;attempt<6;attempt++){await Task.Delay(2000,stop.Token);try{using var response=await http.GetAsync("/status",stop.Token);using var status=JsonDocument.Parse(await response.Content.ReadAsStringAsync(stop.Token));enabled=response.IsSuccessStatusCode&&status.RootElement.TryGetProperty("enabled",out var flag)&&flag.GetBoolean();State=enabled?"已开启":"已关闭 / 等待微信测试";break;}catch(HttpRequestException){}}
                    }
                }
            }
            }
            await foreach(var pending in queue.Reader.ReadAllAsync(stop.Token)){
                var message=pending.Message;
                if(!enabled||DateTimeOffset.UtcNow-message.SentAt>=TimeSpan.FromMinutes(2))continue;
                var version=Interlocked.Read(ref generation);
                IReadOnlyList<string> parts;
                try{parts=WeixinText.Parts(WeixinText.Compose(message,pending.Pinned,pending.IsPinnedUpdate));}
                catch(ArgumentException){Failed++;State="单条链接超过微信长度限制，未拆坏链接；电脑小窗可看完整内容";continue;}
                if(version!=Interlocked.Read(ref generation))continue;
                var completed=true;
                try{
                    for(var part=0;part<parts.Count;part++){
                    var body=JsonSerializer.Serialize(new{id=message.SourceId+":"+message.Id+":"+part,text=parts[part],sentAt=message.SentAt.ToUnixTimeMilliseconds()});
                    var sent=false;
                    for(var attempt=0;attempt<3;attempt++){
                        if(!enabled||version!=Interlocked.Read(ref generation)||DateTimeOffset.UtcNow-message.SentAt>=TimeSpan.FromMinutes(2))break;
                        using var content=new StringContent(body,Encoding.UTF8,"application/json");using var response=await http.PostAsync("/forward",content,stop.Token);
                        if(response.IsSuccessStatusCode){sent=true;State="已开启";break;}
                        // Only 429 means the local sender did not attempt delivery. Never retry uncertain sends.
                        if((int)response.StatusCode==429&&attempt<2){await Task.Delay(500*(attempt+1),stop.Token);continue;}
                        State="转发失败 / 不补发旧消息";break;
                    }
                    if(!sent){completed=false;Failed++;State=part>0?"部分分段发送失败 / 不重复已发送段":"转发失败 / 不补发旧消息";break;}
                    }
                    if(completed)Sent++;
                }
                catch(Exception e) when(e is HttpRequestException or OperationCanceledException){Failed++;State="微信连接中断 / 不补发旧消息";}
            }
        }catch(Exception e) when(e is IOException or JsonException or InvalidOperationException or ArgumentException or HttpRequestException or OperationCanceledException){State="微信配置或连接不可用";enabled=false;}
    }
    internal static string Compose(IncomingMessage message)
    {
        return WeixinText.Compose(message);
    }
    public async ValueTask DisposeAsync(){enabled=false;Reset();queue.Writer.TryComplete();stop.Cancel();try{await runner;}catch(OperationCanceledException){}http.Dispose();stop.Dispose();}
}
