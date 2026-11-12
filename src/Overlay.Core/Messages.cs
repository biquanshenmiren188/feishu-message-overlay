namespace Overlay.Core;

public enum SenderKind { Unknown, Person, Bot }
public sealed class DedupCapacityException : Exception { }
public record IncomingMessage(string Id, string SourceId, string Sender, string Text, DateTimeOffset SentAt,
    SenderKind Kind = SenderKind.Unknown, string SenderId = "", string MessageType = "text", MessageCard? Card = null);
public interface IMessageSource : IAsyncDisposable
{
    string Mode { get; }
    bool IsRealConnection { get; }
    Task<IReadOnlyList<IncomingMessage>> ReadAsync(CancellationToken cancellationToken);
}

// Delivery adapters must restrict authorized group IDs before reading message bodies.
// This store contains no disk/network/logging code.
public sealed class MessageStore(int capacity = 100, TimeSpan? lifetime = null, bool expireMessages = true)
{
    private readonly List<IncomingMessage> messages = [];
    private readonly Dictionary<string, DateTimeOffset> seen = [];
    private readonly TimeSpan ttl = lifetime ?? TimeSpan.FromMinutes(30);
    private readonly int limit = Math.Clamp(capacity, 1, 1000);
    private DateTimeOffset cutoff = DateTimeOffset.MinValue;
    public long Revision {get;private set;}
    public IReadOnlyList<IncomingMessage> Items => messages.ToArray();
    public void Start(DateTimeOffset now) { Clear(now); }
    public void Clear(DateTimeOffset now) { messages.Clear(); seen.Clear(); cutoff = now; Revision++; }
    public void Prune(DateTimeOffset now)
    {
        // Admission/dedup freshness is separate from the user's retained reading history.
        if(expireMessages && messages.RemoveAll(m => now - m.SentAt >= ttl)>0)Revision++;
        foreach (var key in seen.Where(p => now - p.Value >= ttl).Select(p => p.Key).ToArray()) seen.Remove(key);
    }
    public void KeepLatest(string groupId)
    {
        var latest=messages.Where(m=>m.SourceId==groupId).OrderByDescending(m=>m.SentAt).FirstOrDefault();
        if(latest is not null && messages.RemoveAll(m=>m.SourceId==groupId && m.Id!=latest.Id)>0)Revision++;
    }
    public bool Add(IncomingMessage message, string selectedSource, DateTimeOffset now,bool latestOnly=false,bool retainedSnapshot=false)
    {
        Prune(now);
        if (message.SourceId != selectedSource || message.Kind != SenderKind.Bot || string.IsNullOrWhiteSpace(message.Id) ||
            (!retainedSnapshot && message.SentAt <= cutoff) || message.SentAt > now.AddMinutes(1) || (!retainedSnapshot && now - message.SentAt >= ttl)) return false;
        var key = message.SourceId + "\0" + message.Id;
        if (seen.ContainsKey(key) || messages.Any(m=>m.SourceId==message.SourceId && m.Id==message.Id)) return false;
        // Bound both message history and the deduplication window.
        // Never evict recent IDs: eviction could replay a duplicated delivery.
        // Refuse excess traffic until expiry instead of violating bounded deduplication.
        if (seen.Count >= limit * 10) throw new DedupCapacityException();
        seen[key] = now;
        if(latestOnly)messages.RemoveAll(m=>m.SourceId==selectedSource);
        messages.Insert(0, message with { Sender = Bound(message.Sender, 256), Text = Bound(message.Text, 16000) });
        Revision++;
        if (messages.Count > limit) messages.RemoveAt(messages.Count - 1);
        return true;
    }
    private static string Bound(string value, int length) => value.Length <= length ? value : value[..length] + "\n[本软件已限制显示长度]";
}

public sealed class DemoSource : IMessageSource
{
    private int count;
    public string Mode => "模拟演示（非真实飞书消息）";
    public bool IsRealConnection => false;
    public Task<IReadOnlyList<IncomingMessage>> ReadAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var number = ++count;
        IReadOnlyList<IncomingMessage> result = [new($"demo-{number}", "demo", "演示发送人", number % 3 == 0
            ? string.Concat(Enumerable.Repeat("这是一条中文长消息，用于检查换行、滚动和字体调整。", 20))
            : $"模拟消息 {number}：窗口可以拖动、缩放，声音使用系统音量。", DateTimeOffset.UtcNow, SenderKind.Bot, "demo-bot")];
        return Task.FromResult(result);
    }
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}
