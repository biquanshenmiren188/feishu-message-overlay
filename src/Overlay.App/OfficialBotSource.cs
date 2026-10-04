using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using Overlay.Core;
namespace Overlay.App;
public enum LinkState { Connecting, Connected, Reconnecting, Protected, Error, Stopped }
public sealed class OfficialBotSource : IMessageSource
{
    private readonly Process process;
    private readonly Channel<IncomingMessage> queue = Channel.CreateBounded<IncomingMessage>(100);
    private BotEventFilter filter;
    private readonly string[] botIds;
    public IReadOnlyDictionary<string,string> JoinedGroupNames {get;private set;}=new Dictionary<string,string>();
    public string[] JoinedChatIds {get;private set;}=[];
    public string MembershipState {get;private set;}="manual";
    private readonly CancellationTokenSource stop = new();
    private readonly Task pump;
    private readonly bool fixture;
    private volatile LinkState state = LinkState.Connecting;
    private bool disposed;
    private static int activeChildren;
    internal static int ActiveChildren => activeChildren;
    public LinkState State => state;
    public string? LastMessageType {get;private set;}
    public CardMetadata? LastCardMetadata {get;private set;}
    public CardMetadata? LastCardDetailsFailure {get;private set;}
    public event Action? Activity;
    public string Mode => MembershipState=="discovery_failed"?"群发现失败，已暂停群消息接收；稍后自动重试":state switch
    {
        LinkState.Connected => fixture ? "本地契约连接 · 非真实飞书" : "已连接 · 官方长连接",
        LinkState.Reconnecting => "连接中断 · 正在重连，只接收恢复后的新消息",
        LinkState.Protected => "保护暂停 · 去重窗口达到上限，请重新连接",
        LinkState.Error => "连接错误 · 请检查应用权限、密钥和网络后重新连接",
        LinkState.Stopped => "已暂停 · 连接已关闭",
        _ => "连接中 · 等待官方握手"
    };
    public bool IsRealConnection => !fixture && state == LinkState.Connected;
    private OfficialBotSource(Process process, IReadOnlyList<string> chatIds, IReadOnlyList<string> botIds, bool fixture)
    {
        this.process = process; this.fixture = fixture; this.botIds=botIds.ToArray();JoinedChatIds=chatIds.ToArray();filter = new BotEventFilter(chatIds, botIds); pump = PumpAsync();
    }
    public static async Task<OfficialBotSource> StartAsync(string nodePath, string bridgePath, string appId, string appSecret, IReadOnlyList<string> selectedChatIds, IReadOnlyList<string> selectedBotIds, CancellationToken cancellationToken, bool fixture = false,bool autoJoined=false)
    {
        if (fixture && !App.SmokeMode) throw new InvalidOperationException("契约测试仅允许测试模式");
        if (selectedChatIds.Count is < 1 or > 5) throw new ArgumentException("必须选择一至五个准确群 ID");
        var info = new ProcessStartInfo(nodePath) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = Path.GetDirectoryName(bridgePath)!, StandardInputEncoding=new UTF8Encoding(false), StandardOutputEncoding=new UTF8Encoding(false) };
        info.ArgumentList.Add(bridgePath);
        var child = Process.Start(info) ?? throw new InvalidOperationException("连接器启动失败");
        Interlocked.Increment(ref activeChildren);
        var source = new OfficialBotSource(child, selectedChatIds, selectedBotIds, fixture);
        try
        {
            await child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new { appId, appSecret, chatIds = selectedChatIds, botIds = selectedBotIds,autoJoined }).AsMemory(), cancellationToken);
            await child.StandardInput.FlushAsync(cancellationToken);
            return source;
        }
        catch { await source.DisposeAsync(); throw new InvalidOperationException("配置未完成；连接器已停止"); }
    }
    private async Task PumpAsync()
    {
        var stderr = DiscardErrorsAsync();
        try
        {
            while (!stop.IsCancellationRequested)
            {
                var line = await process.StandardOutput.ReadLineAsync(stop.Token);
                if (line is null) { state = LinkState.Error; break; }
                if (line.Length > 1_048_576) throw new InvalidOperationException();
                line=line.TrimStart('\uFEFF',' ','\t');
                if(!line.StartsWith('{'))continue;
                using var document = JsonDocument.Parse(line); var root = document.RootElement;
                if(root.GetProperty("kind").GetString()=="membership")
                {
                    var ids=root.GetProperty("chatIds").EnumerateArray().Select(v=>v.GetString()??"").ToArray();
                    if(ids.Length>2000 || ids.Any(v=>!System.Text.RegularExpressions.Regex.IsMatch(v,"^oc_[a-zA-Z0-9_-]+$")))throw new InvalidOperationException();
                    var names=new Dictionary<string,string>(StringComparer.Ordinal);
                    if(root.TryGetProperty("groups",out var groups))foreach(var group in groups.EnumerateArray().Take(2000))
                    {var id=group.GetProperty("chatId").GetString();var name=group.GetProperty("name").GetString();if(id is not null && ids.Contains(id) && name is not null && name.Length<=256)names[id]=name;}
                    JoinedGroupNames=names;JoinedChatIds=ids;filter=new BotEventFilter(ids,botIds);MembershipState=root.GetProperty("state").GetString()??"error";Activity?.Invoke();
                }
                else if(root.GetProperty("kind").GetString()=="card_meta")
                {if(root.TryGetProperty("meta",out var meta) && CardMetadata.Project(meta) is {} safe){LastCardMetadata=safe;if(safe.Detail is "api_rejected" or "identity_mismatch" or "detail_has_no_targets" or "timeout" or "request_failed")LastCardDetailsFailure=safe;}}
                else if (root.GetProperty("kind").GetString() == "status")
                {
                    state = root.GetProperty("state").GetString() switch { "connected" => LinkState.Connected, "reconnecting" => LinkState.Reconnecting, "protected" => LinkState.Protected, _ => LinkState.Error };
                    if (state != LinkState.Connected) while (queue.Reader.TryRead(out _)) { }
                    Activity?.Invoke();
                    if (state is LinkState.Error or LinkState.Protected) break;
                }
                else if (state == LinkState.Connected)
                {
                    var message = filter.Parse(root.GetProperty("payload").GetRawText());
                    if(message is not null)LastMessageType=root.GetProperty("payload").GetProperty("event").GetProperty("message").GetProperty("message_type").GetString();
                    if (message is not null && !queue.Writer.TryWrite(message)) { state = LinkState.Protected; break; }
                    if(message is not null)Activity?.Invoke();
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception) { state = LinkState.Error; }
        finally
        {
            Activity?.Invoke();
            queue.Writer.TryComplete(); stop.Cancel();
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
            await stderr;
        }
    }
    private async Task DiscardErrorsAsync()
    {
        var buffer = new char[4096];
        try { while (await process.StandardError.ReadAsync(buffer, stop.Token) > 0) Array.Clear(buffer); }
        catch (OperationCanceledException) { }
        catch (IOException) { }
        finally { Array.Clear(buffer); }
    }
    internal async Task ContractCommandAsync(string command) { if (!fixture) throw new InvalidOperationException(); await process.StandardInput.WriteLineAsync(command); await process.StandardInput.FlushAsync(); }
    public Task<IReadOnlyList<IncomingMessage>> ReadAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (state is LinkState.Error or LinkState.Protected or LinkState.Stopped) throw new InvalidOperationException(Mode);
        var messages = new List<IncomingMessage>(); while (queue.Reader.TryRead(out var message)) messages.Add(message);
        return Task.FromResult<IReadOnlyList<IncomingMessage>>(messages);
    }
    public async ValueTask DisposeAsync()
    {
        if (disposed) return; disposed = true; stop.Cancel();
        try { process.StandardInput.Close(); if (!process.HasExited) process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
        while (queue.Reader.TryRead(out _)) { }
        await pump; state = LinkState.Stopped; process.Dispose(); stop.Dispose(); Interlocked.Decrement(ref activeChildren);
    }
}
