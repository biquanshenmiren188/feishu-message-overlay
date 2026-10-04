using System.Text.Json;
using Overlay.Core;
namespace Overlay.App;
internal sealed class CloudMessageSource : IMessageSource
{
    private readonly CancellationTokenSource stop=new();
    private readonly object gate=new();
    private readonly Dictionary<string,DateTimeOffset> seen=new(StringComparer.Ordinal);
    private readonly Queue<IncomingMessage> pending=new();
    private readonly Task worker;
    private readonly Func<object,Task<JsonDocument>> request;
    private readonly TimeSpan pollInterval;
    internal event Action? Activity;
    internal LinkState State{get;private set;}=LinkState.Connecting;
    internal bool StateLoaded{get;private set;}
    internal long ConnectionRevision{get;private set;}
    internal IReadOnlyDictionary<string,string> Groups{get;private set;}=new Dictionary<string,string>();
    internal IncomingMessage? Pinned{get;private set;}
    internal string PinnedGroupId{get;private set;}="";
    internal DateTimeOffset StartedAt{get;}=DateTimeOffset.UtcNow;
    public bool IsRealConnection=>State==LinkState.Connected;
    public string Mode=>State==LinkState.Connected?"已连接 · 云端唯一接收源":State==LinkState.Connecting?"连接云端中":"云端暂不可用 · 不会启动本地飞书连接";
    internal CloudMessageSource(Func<object,Task<JsonDocument>>? transport=null,TimeSpan? interval=null)
    {request=transport??(payload=>PublicWebPublisher.SendControlAsync("/radar/api/robot-push/control",payload));pollInterval=interval??TimeSpan.FromSeconds(3);worker=Task.Run(PollAsync);}
    internal static string GroupHash(string id)=>id.Length==64 && id.All(Uri.IsHexDigit)?id.ToLowerInvariant():PublicWebPublisher.Digest(id);
    internal static IncomingMessage ParseMessage(JsonElement raw,IReadOnlyDictionary<string,string> mapping)
    {
        var group=raw.GetProperty("groupId").GetString()??"";
        if(!mapping.TryGetValue(group,out var source)||raw.GetProperty("senderType").GetString()!="bot")throw new JsonException();
        var id=raw.GetProperty("id").GetString()??"";var title=raw.GetProperty("title").GetString()??"";var body=raw.GetProperty("body").GetString()??"";
        if(id.Length!=64||!id.All(Uri.IsHexDigit)||body.Length>16000||title.Length>1024)throw new JsonException();
        var actions=raw.GetProperty("actions").EnumerateArray().Take(9).Select(a=>new CardLink(a.GetProperty("label").GetString()??"",a.GetProperty("url").GetString()??"")).ToArray();
        if(actions.Length>8||actions.Any(a=>a.Label.Length>128||!MessageCardParser.SafeUrl(a.Url)))throw new JsonException();
        var sent=raw.GetProperty("sentAt").GetDateTimeOffset();
        if(sent>DateTimeOffset.UtcNow.AddMinutes(1))throw new JsonException();
        return new(id,source,"",body,sent,SenderKind.Bot,"","cloud",new MessageCard(title,body,actions,raw.TryGetProperty("headerTone",out var tone)&&tone.ValueKind==JsonValueKind.String?MessageCard.SafeTone(tone.GetString()):"grey",IsMarkdown:true));
    }
    private async Task PollAsync()
    {
        var delay=3;
        while(!stop.IsCancellationRequested)
        {
            try
            {
                using var result=await request(new{action="state"});
                var root=result.RootElement;if(!root.GetProperty("cloudMode").GetBoolean())throw new JsonException();
                var groups=new Dictionary<string,string>(StringComparer.Ordinal);var mapping=new Dictionary<string,string>(StringComparer.Ordinal);
                foreach(var item in root.GetProperty("groups").EnumerateArray().Take(2001))
                {
                    var id=item.GetProperty("id").GetString()??"";var hash=item.GetProperty("groupId").GetString()??"";var name=item.GetProperty("name").GetString()??"";
                    if(!id.StartsWith("oc_",StringComparison.Ordinal)||id.Length>256||name.Length>256||hash!=GroupHash(id))throw new JsonException();
                    groups[id]=name;mapping[hash]=id;
                }
                if(groups.Count>2000)throw new JsonException();
                var normal=root.GetProperty("messages").EnumerateArray().Take(101).Select(m=>ParseMessage(m,mapping)).ToArray();
                if(normal.Length>100)throw new JsonException();
                var pinHash=root.GetProperty("pinnedGroupId").GetString()??"";
                var pin=root.GetProperty("pinned");var selected=mapping.GetValueOrDefault(pinHash)??"";
                var pinned=pin.ValueKind==JsonValueKind.Null?null:ParseMessage(pin,mapping);
                if(pinned is not null&&pinned.SourceId!=selected)throw new JsonException();
                lock(gate)
                {
                    Groups=groups;Pinned=pinned;PinnedGroupId=selected;StateLoaded=true;
                    foreach(var key in seen.Where(p=>DateTimeOffset.UtcNow-p.Value>TimeSpan.FromMinutes(30)).Select(p=>p.Key).ToArray())seen.Remove(key);
                    foreach(var message in normal.OrderBy(m=>m.SentAt))
                    {if(DateTimeOffset.UtcNow-message.SentAt>=TimeSpan.FromMinutes(30)||seen.ContainsKey(message.Id))continue;if(seen.Count>=10000)throw new JsonException();seen[message.Id]=DateTimeOffset.UtcNow;if(pending.Count==100)pending.Dequeue();pending.Enqueue(message);}
                    var connected=root.GetProperty("sourceConnected").GetBoolean();
                    if(connected && State!=LinkState.Connected)ConnectionRevision++;
                    State=connected?LinkState.Connected:LinkState.Reconnecting;
                }
                delay=3;Activity?.Invoke();
            }
            catch{State=LinkState.Reconnecting;Activity?.Invoke();delay=Math.Min(30,delay*2);}
            try{await Task.Delay(delay==3?pollInterval:TimeSpan.FromSeconds(delay),stop.Token);}catch(OperationCanceledException){break;}
        }
    }
    internal async Task SelectPinAsync(string id)
    {using var result=await request(new{action="pin",pinnedGroupId=id.Length==0?"":GroupHash(id)});if(!result.RootElement.GetProperty("saved").GetBoolean())throw new InvalidOperationException();}
    public Task<IReadOnlyList<IncomingMessage>> ReadAsync(CancellationToken cancellationToken)
    {cancellationToken.ThrowIfCancellationRequested();lock(gate){IReadOnlyList<IncomingMessage> result=pending.ToArray();pending.Clear();return Task.FromResult(result);}}
    public async ValueTask DisposeAsync(){stop.Cancel();await worker;stop.Dispose();lock(gate)pending.Clear();}
}
