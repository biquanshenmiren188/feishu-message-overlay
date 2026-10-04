using System.IO;
using System.Text.Json;
namespace Overlay.App;
internal static class CloudSourceContract
{
    internal static async Task RunAsync(string output)
    {
        var checks=new List<string>();var group=CloudMessageSource.GroupHash("oc_fixture");var stamp=DateTimeOffset.UtcNow.AddSeconds(-1);
        object Message(string id)=>new{id=PublicWebPublisher.Digest(id),groupId=group,senderType="bot",sentAt=stamp,title="Synthetic title",headerTone="blue",body="First\nSecond",actions=new[]{new{label="Example",url="https://example.invalid/?x=1&y=2"}}};
        string State(object[] messages,object? pinned=null,bool connected=true)=>JsonSerializer.Serialize(new{cloudMode=true,sourceConnected=connected,groups=new[]{new{id="oc_fixture",groupId=group,name="Synthetic group"}},messages,pinned,pinnedGroupId=pinned is null?"":group});
        var state=State([Message("a")]);var polls=0;var pinCalled=false;
        Task<JsonDocument> Transport(object payload)
        {
            using var request=JsonDocument.Parse(JsonSerializer.Serialize(payload));
            if(request.RootElement.GetProperty("action").GetString()=="pin")
            {pinCalled=request.RootElement.GetProperty("pinnedGroupId").GetString()==group;return Task.FromResult(JsonDocument.Parse("{\"saved\":true}"));}
            Interlocked.Increment(ref polls);return Task.FromResult(JsonDocument.Parse(Volatile.Read(ref state)));
        }
        async Task Until(Func<bool> predicate){for(var i=0;i<150&&!predicate();i++)await Task.Delay(20);if(!predicate())throw new InvalidOperationException("Cloud source contract timeout");}
        await using(var source=new CloudMessageSource(Transport,TimeSpan.FromMilliseconds(25)))
        {
            await Until(()=>source.StateLoaded);var first=await source.ReadAsync(CancellationToken.None);
            if(first.Count!=1||first[0].SourceId!="oc_fixture"||first[0].Card?.Buttons.Count!=1||first[0].SentAt>=source.StartedAt)throw new InvalidOperationException("Hydration contract");
            if(first[0].Card?.HeaderTone!="blue")throw new InvalidOperationException("Cloud tone lost");checks.Add("cloud_header_template_preserved");
            checks.Add("snapshot_preserves_card_group_and_old_timestamp_for_mute");
            var count=Volatile.Read(ref polls);await Until(()=>Volatile.Read(ref polls)>=count+2);
            if((await source.ReadAsync(CancellationToken.None)).Count!=0)throw new InvalidOperationException("Duplicate replay");checks.Add("snapshot_dedup");
            Volatile.Write(ref state,State([Message("a"),Message("b")],Message("pin")));await Until(()=>source.Pinned is not null);
            if((await source.ReadAsync(CancellationToken.None)).Count!=1||source.PinnedGroupId!="oc_fixture")throw new InvalidOperationException("Pin separation");checks.Add("independent_pin_and_new_arrival");
            await source.SelectPinAsync("oc_fixture");if(!pinCalled)throw new InvalidOperationException("Unsigned pin");checks.Add("pin_uses_control_transport");
            Volatile.Write(ref state,State([],connected:false));await Until(()=>source.State==LinkState.Reconnecting);
            if(source.IsRealConnection)throw new InvalidOperationException("Offline status");checks.Add("offline_without_local_fallback");
        }
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,syntheticOnly=true,realCredentialUsed=false}));
    }
}
