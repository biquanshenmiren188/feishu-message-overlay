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
    private readonly Func<object,CancellationToken,Task<JsonDocument>> request;
    private Dictionary<string,string>? known;
    private readonly Dictionary<string,JsonElement> cached=new(StringComparer.Ordinal);
    private readonly TimeSpan pollInterval;
    private readonly string pushCode;
    internal bool CanManage=>RulesConnected&&pushCode.Length>0;
    internal event Action? Activity;
    internal LinkState State{get;private set;}=LinkState.Connecting;
    internal bool StateLoaded{get;private set;}
    internal long ConnectionRevision{get;private set;}
    internal IReadOnlyDictionary<string,string> Groups{get;private set;}=new Dictionary<string,string>();
    internal IncomingMessage? Pinned{get;private set;}
    internal string PinnedGroupId{get;private set;}="";
    internal JsonElement? Opportunities{get;private set;}
    internal DesktopRuleDecisions Rules{get;private set;}=DesktopRuleDecisions.Empty;
    internal bool RulesConnected{get;private set;}
    internal bool TransportConnected{get;private set;}
    internal DateTimeOffset StartedAt{get;}=DateTimeOffset.UtcNow;
    public bool IsRealConnection=>State==LinkState.Connected;
    public string Mode=>pushCode.Length>0&&!RulesConnected&&State!=LinkState.Connecting?"推送码规则暂不可用 · 已暂停接收，请检查绑定或稍后重试":State==LinkState.Connected?"已连接 · 云端唯一接收源":State==LinkState.Connecting?"连接云端中":"云端暂不可用 · 不会启动本地飞书连接";
    internal CloudMessageSource(Func<object,Task<JsonDocument>>? transport=null,TimeSpan? interval=null,Func<object,CancellationToken,Task<JsonDocument>>? cancellableTransport=null,string pushCode="")
    {if(pushCode.Length!=0&&!DesktopPushBinding.Valid(pushCode))throw new ArgumentException("Invalid push code");this.pushCode=pushCode;Rules=pushCode.Length>0?DesktopRuleDecisions.Blocked:DesktopRuleDecisions.Empty;request=cancellableTransport??(transport is null?(payload,token)=>PublicWebPublisher.SendControlAsync("/radar/api/robot-push/control",payload,token):(payload,_)=>transport(payload));pollInterval=interval??TimeSpan.FromSeconds(3);worker=Task.Run(PollAsync);}
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
                object payload=known is null?new{action="state",desktopRules=1,pushCode}:(object)new{action="state",known,desktopRules=1,pushCode};
                using var result=await request(payload,stop.Token);
                var root=result.RootElement;if(!root.GetProperty("cloudMode").GetBoolean())throw new JsonException();
                var nextRules=DesktopPushBinding.ValidateState(root,pushCode);
                var conditional=root.TryGetProperty("protocol",out var protocol)&&protocol.ValueKind==JsonValueKind.Number&&protocol.GetInt32()==1;
                Dictionary<string,string>? nextKnown=null;
                if(conditional)
                {
                    nextKnown=new(StringComparer.Ordinal);
                    foreach(var part in new[]{"groups","messages","pin","opportunities"})
                    {
                        var revision=root.GetProperty("revisions").GetProperty(part).GetString()??"";
                        if(revision.Length!=64||!revision.All(Uri.IsHexDigit))throw new JsonException();
                        nextKnown[part]=revision;
                        foreach(var field in part=="pin"?new[]{"pinned","pinnedGroupId"}:new[]{part})
                            if(!root.TryGetProperty(field,out _) && (known?.GetValueOrDefault(part)!=revision||!cached.ContainsKey(field)))throw new JsonException();
                    }
                }
                JsonElement Field(string name)=>root.TryGetProperty(name,out var value)?value:conditional&&cached.TryGetValue(name,out value)?value:throw new JsonException();
                var groups=new Dictionary<string,string>(StringComparer.Ordinal);var mapping=new Dictionary<string,string>(StringComparer.Ordinal);
                foreach(var item in Field("groups").EnumerateArray().Take(2001))
                {
                    var id=item.GetProperty("id").GetString()??"";var hash=item.GetProperty("groupId").GetString()??"";var name=item.GetProperty("name").GetString()??"";
                    if(!id.StartsWith("oc_",StringComparison.Ordinal)||id.Length>256||name.Length>256||hash!=GroupHash(id))throw new JsonException();
                    groups[id]=name;mapping[hash]=id;
                }
                if(groups.Count>2000)throw new JsonException();
                var normal=Field("messages").EnumerateArray().Take(101).Select(m=>ParseMessage(m,mapping)).ToArray();
                if(normal.Length>100)throw new JsonException();
                var pinHash=Field("pinnedGroupId").GetString()??"";
                var pin=Field("pinned");var selected=mapping.GetValueOrDefault(pinHash)??"";
                var pinned=pin.ValueKind==JsonValueKind.Null?null:ParseMessage(pin,mapping);
                if(pinned is not null&&pinned.SourceId!=selected)throw new JsonException();
                lock(gate)
                {
                    RulesConnected=true;Rules=nextRules;
                    Groups=groups;Pinned=pinned;PinnedGroupId=selected;StateLoaded=true;
                    Opportunities=root.TryGetProperty("opportunities",out var cards)?cards.Clone():conditional?Opportunities:null;
                    TransportConnected=true;
                    foreach(var key in seen.Where(p=>DateTimeOffset.UtcNow-p.Value>TimeSpan.FromMinutes(30)).Select(p=>p.Key).ToArray())seen.Remove(key);
                    foreach(var message in normal.OrderBy(m=>m.SentAt))
                    {if(DateTimeOffset.UtcNow-message.SentAt>=TimeSpan.FromMinutes(30)||seen.ContainsKey(message.Id))continue;if(seen.Count>=10000)throw new JsonException();seen[message.Id]=DateTimeOffset.UtcNow;if(pending.Count==100)pending.Dequeue();pending.Enqueue(message);}
                    var connected=root.GetProperty("sourceConnected").GetBoolean();
                    if(connected && State!=LinkState.Connected)ConnectionRevision++;
                    State=connected?LinkState.Connected:LinkState.Reconnecting;
                }
                // Retain only validated components, without re-serializing unchanged data.
                if(conditional)
                {
                    foreach(var field in new[]{"groups","messages","pinned","pinnedGroupId","opportunities"})
                        if(root.TryGetProperty(field,out var value))cached[field]=value.Clone();
                }
                else cached.Clear();
                known=nextKnown;
                delay=3;Activity?.Invoke();
            }
            catch(OperationCanceledException) when(stop.IsCancellationRequested){break;}
            catch{known=null;cached.Clear();lock(gate){RulesConnected=false;if(pushCode.Length>0)Rules=DesktopRuleDecisions.Blocked;pending.Clear();seen.Clear();TransportConnected=false;State=LinkState.Reconnecting;}Activity?.Invoke();delay=Math.Min(30,delay*2);}
            try{await Task.Delay(delay==3?pollInterval:TimeSpan.FromSeconds(delay),stop.Token);}catch(OperationCanceledException){break;}
        }
    }
    internal async Task SelectPinAsync(string id)
    {using var result=await request(new{action="pin",pinnedGroupId=id.Length==0?"":GroupHash(id)},stop.Token);if(!result.RootElement.GetProperty("saved").GetBoolean())throw new InvalidOperationException();}
    public Task<IReadOnlyList<IncomingMessage>> ReadAsync(CancellationToken cancellationToken)
    {cancellationToken.ThrowIfCancellationRequested();lock(gate){IReadOnlyList<IncomingMessage> result=pending.ToArray();pending.Clear();return Task.FromResult(result);}}
    public async ValueTask DisposeAsync(){stop.Cancel();await worker;stop.Dispose();lock(gate)pending.Clear();}
}
