namespace Overlay.Core;
// Bounded metadata only: no bodies, sender identities, message IDs or credentials.
// Call only after the normal source/identity/time/dedup gates have accepted a message.
public sealed class GroupReceptionStatistics
{
    private sealed class Row(string id)
    {
        public string ChatId {get;}=id;
        public long BotMessages,SoundRequests;
        public DateTimeOffset? LastEventAt,LastReceivedAt;
        public string? LastType;
        public bool? LastReadableText;
        public string LastSoundResult="waiting";
        public readonly Dictionary<string,long> TypeCounts=[];
    }
    public sealed record SnapshotRow(string ChatId,long BotMessages,DateTimeOffset? LastEventAt,
        DateTimeOffset? LastReceivedAt,string? LastType,bool? LastReadableText,
        IReadOnlyDictionary<string,long> TypeCounts,long SoundRequests,string LastSoundResult);
    private Dictionary<string,Row> rows=new(StringComparer.Ordinal);
    public void Select(IEnumerable<string> chatIds)
    {
        var selected=chatIds.Distinct(StringComparer.Ordinal).ToArray();
        if(selected.Length is <1 or >5)throw new ArgumentException("Select one to five groups");
        rows=selected.ToDictionary(id=>id,id=>new Row(id),StringComparer.Ordinal);
    }
    public bool RecordAccepted(IncomingMessage message,bool accepted,bool readable,DateTimeOffset receivedAt)
    {
        if(!accepted || message.Kind!=SenderKind.Bot || !rows.TryGetValue(message.SourceId,out var row))return false;
        var type=message.MessageType is "text" or "post" or "interactive"?message.MessageType:"unsupported";
        row.BotMessages++;row.LastEventAt=message.SentAt;row.LastReceivedAt=receivedAt;
        row.LastType=type;row.LastReadableText=readable;
        row.TypeCounts[type]=row.TypeCounts.GetValueOrDefault(type)+1;return true;
    }
    public void RecordSound(IEnumerable<string> batchChatIds,bool requested,bool? waveAccepted,bool coalesced=false)
    {
        foreach(var id in batchChatIds.Distinct(StringComparer.Ordinal))
        {
            if(!rows.TryGetValue(id,out var row))continue;
            if(requested)row.SoundRequests++;
            row.LastSoundResult=!requested?(coalesced?"coalesced":"disabled"):waveAccepted==true?"accepted":waveAccepted==false?"request_failed":"not_verified";
        }
    }
    public IReadOnlyList<SnapshotRow> Snapshot()=>rows.Values.OrderBy(row=>row.ChatId,StringComparer.Ordinal)
        .Select(row=>new SnapshotRow(row.ChatId,row.BotMessages,row.LastEventAt,row.LastReceivedAt,row.LastType,
            row.LastReadableText,new Dictionary<string,long>(row.TypeCounts),row.SoundRequests,row.LastSoundResult)).ToArray();
}
