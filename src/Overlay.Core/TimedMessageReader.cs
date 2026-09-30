namespace Overlay.Core;
// IDs only, bounded by the message store. Reading never causes a sound or deletion.
public sealed class TimedMessageReader
{
    private string[] ids=[];
    private string? current;
    private DateTimeOffset due;
    public int Seconds {get;private set;}=15;
    public string? Current=>current;
    public TimeSpan? DelayUntilNext(DateTimeOffset now)
    {var index=Array.IndexOf(ids,current);return index<0 || index+1>=ids.Length?null:due>now?due-now:TimeSpan.Zero;}
    public void Configure(int seconds,DateTimeOffset now)
    {Seconds=Math.Clamp(seconds,1,300);due=now.AddSeconds(Seconds);}
    public void Synchronize(IEnumerable<string> messageIds,DateTimeOffset now)
    {
        ids=messageIds.Take(100).ToArray();
        if(current is null || !ids.Contains(current,StringComparer.Ordinal))
        {current=ids.FirstOrDefault();due=now.AddSeconds(Seconds);}
    }
    public void Focus(string? id,DateTimeOffset now)
    {if(id is not null && ids.Contains(id,StringComparer.Ordinal))current=id;due=now.AddSeconds(Seconds);}
    public string? Advance(DateTimeOffset now,bool enabled,bool suspended)
    {
        if(!enabled || suspended){due=now.AddSeconds(Seconds);return null;}
        if(current is null || now<due)return null;
        var index=Array.IndexOf(ids,current);
        if(index<0 || index+1>=ids.Length)return null;
        current=ids[index+1];due=now.AddSeconds(Seconds);return current;
    }
}
