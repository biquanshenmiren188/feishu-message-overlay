using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunCloudWindowContractAsync(string output)
    {
        var checks=new List<string>();var normalGroup=PublicWebPublisher.Digest("oc_normal");var pinGroup=PublicWebPublisher.Digest("oc_pin");
        var old=DateTimeOffset.UtcNow.AddMinutes(-1);
        object Message(string id,string group,DateTimeOffset sent)=>new{id=PublicWebPublisher.Digest(id),groupId=group,senderType="bot",sentAt=sent,title="Synthetic",headerTone="blue",body="First line\nSecond line\nThird line",actions=new[]{new{label="Example",url="https://example.invalid/"}}};
        string Snapshot(int count,string pin)=>JsonSerializer.Serialize(new{cloudMode=true,sourceConnected=true,groups=new[]{new{id="oc_normal",groupId=normalGroup,name="Normal fixture"},new{id="oc_pin",groupId=pinGroup,name="Pinned fixture"}},messages=Enumerable.Range(0,count).Select(i=>Message("normal"+i,normalGroup,old.AddSeconds(i))).ToArray(),pinned=Message(pin,pinGroup,old),pinnedGroupId=pinGroup});
        var snapshot=Snapshot(4,"pin1");
        var cloud=new CloudMessageSource(_=>Task.FromResult(JsonDocument.Parse(Volatile.Read(ref snapshot))),TimeSpan.FromMilliseconds(50));
        source=cloud;cloud.Activity+=ScheduleRead;store.Start(DateTimeOffset.UtcNow.AddMinutes(-30));
        AutoJoined.IsChecked=true;reader.Configure(5,DateTimeOffset.UtcNow);AutoScroll.IsChecked=true;verifyReadingTimer=true;
        async Task Until(Func<bool> predicate){for(var i=0;i<150&&!predicate();i++)await Task.Delay(20);if(!predicate())throw new InvalidOperationException("Cloud WPF contract timeout");await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);}
        await Until(()=>displayed.Count==4&&PinnedCard.Content is not null);
        if(readingQueue.Length!=4||pinnedChatId!="oc_pin"||soundRequests!=0)throw new InvalidOperationException("Cloud initial rendering");
        if(!displayed.Select(m=>m.Id).SequenceEqual(readingQueue.Select(m=>m.Id)) || Math.Abs(MessageScroll.VerticalOffset-MessageScroll.ScrollableHeight)>2)throw new InvalidOperationException("Cloud must open at latest full viewport messages");
        checks.Add("initial_cloud_snapshot_starts_at_latest_viewport");
        var view=new MessageView{Message=displayed[0]};
        var border=(System.Windows.Controls.Border)view.Children[0];var stack=(System.Windows.Controls.StackPanel)border.Child;
        var header=(System.Windows.Controls.Border)stack.Children[0];var row=(System.Windows.Controls.Grid)header.Child;var title=(System.Windows.Controls.TextBlock)row.Children[0];
        var fg=((System.Windows.Media.SolidColorBrush)title.Foreground).Color;var bg=((System.Windows.Media.SolidColorBrush)header.Background).Color;
        if(fg.B<=fg.R||bg.R<220||fg==System.Windows.Media.Colors.White)throw new InvalidOperationException("Blue title / pale background contract");checks.Add("actual_wpf_blue_title_pale_background");
        checks.Add("actual_wpf_continuous_regular_plus_one_pin_initial_snapshot_muted");
        var first=reader.Current;await Task.Delay(5300);await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        if(reader.Current==first||displayed.Count!=4)throw new InvalidOperationException("Cloud five second reading");
        checks.Add("actual_dispatcher_five_second_reader_advanced");
        var reading=reader.Current;Volatile.Write(ref snapshot,Snapshot(5,"pin2"));await Until(()=>pinnedLatest?.Id==PublicWebPublisher.Digest("pin2")&&readingQueue.Length==5);
        if(reader.Current!=reading||displayed.Count!=5||PinnedCard.Content is null)throw new InvalidOperationException("Cloud pin interrupted reader");
        checks.Add("new_snapshot_and_pin_replace_preserve_reader_and_continuous_history");
        Volatile.Write(ref snapshot,Snapshot(5,"pin2").Replace("\"sourceConnected\":true","\"sourceConnected\":false"));
        await Until(()=>cloud.State==LinkState.Reconnecting);
        Volatile.Write(ref snapshot,Snapshot(8,"pin3"));
        await Until(()=>readingQueue.Length==8 && displayed.LastOrDefault()?.Id==readingQueue.Last().Id);
        if(Math.Abs(MessageScroll.VerticalOffset-MessageScroll.ScrollableHeight)>2 || !displayed.Select(m=>m.Id).SequenceEqual(readingQueue.Select(m=>m.Id)))throw new InvalidOperationException("Cloud reconnect must show latest full viewport");
        checks.Add("reconnected_cloud_skips_backlog_and_shows_latest_viewport");
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,regularVisible=displayed.Count,pinnedVisible=PinnedCard.Content is not null,syntheticOnly=true,realCredentialUsed=false}));
        verifyReadingTimer=false;
    }
}
