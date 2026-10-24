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
        string Snapshot(int count,string pin)=>JsonSerializer.Serialize(new{cloudMode=true,pushBinding=new{protocol=1,bound=true,canManage=true},desktopRules=new{revision=0,messages=new{},cards=new{},desktopEnabled=true,cardsEnabled=true},sourceConnected=true,groups=new[]{new{id="oc_normal",groupId=normalGroup,name="Normal fixture"},new{id="oc_pin",groupId=pinGroup,name="Pinned fixture"}},messages=Enumerable.Range(0,count).Select(i=>Message("normal"+i,normalGroup,old.AddSeconds(i))).ToArray(),pinned=Message(pin,pinGroup,old),pinnedGroupId=pinGroup});
        var snapshot=Snapshot(4,"pin1");
        var cloud=new CloudMessageSource(_=>Task.FromResult(JsonDocument.Parse(Volatile.Read(ref snapshot))),TimeSpan.FromMilliseconds(50),pushCode:"12345678");
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
        Sound.IsChecked=true;AutoScroll.IsChecked=false;
        var ruleCount=0;
        string WithRules(object[] fresh,Dictionary<string,string> decisions)
        {
            var node=System.Text.Json.Nodes.JsonNode.Parse(Snapshot(8,"pin3"))!.AsObject();
            foreach(var m in fresh)node["messages"]!.AsArray().Add(JsonSerializer.SerializeToNode(m));
            node["desktopRules"]=JsonSerializer.SerializeToNode(new{revision=++ruleCount,messages=decisions,cards=new{},desktopEnabled=true,cardsEnabled=true});
            return node.ToJsonString();
        }
        var beforeSound=soundRequests;
        var muteId=PublicWebPublisher.Digest("muted");var hideId=PublicWebPublisher.Digest("hidden");
        var muted=Message("muted",normalGroup,DateTimeOffset.UtcNow);
        Volatile.Write(ref snapshot,WithRules([muted],new(){{muteId,"mute"}}));
        await Until(()=>readingQueue.Any(m=>m.Id==muteId));
        if(soundRequests!=beforeSound)throw new InvalidOperationException("Muted message played sound");
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        if(MessageView.CountMuteBadges(this)!=1)throw new InvalidOperationException("Muted message must show exactly one leading badge");
        checks.Add("muted_message_has_leading_badge_in_actual_window");
        checks.Add("rule_mute_keeps_actual_message_visible_without_sound");
        var hidden=Message("hidden",normalGroup,DateTimeOffset.UtcNow);
        Volatile.Write(ref snapshot,WithRules([muted,hidden],new(){{muteId,"mute"},{hideId,"hide"},{PublicWebPublisher.Digest("pin3"),"hide"}}));
        await Until(()=>cloud.Rules.Revision==ruleCount&&PinnedCard.Content is null);
        if(readingQueue.Any(m=>m.Id==hideId)||soundRequests!=beforeSound)throw new InvalidOperationException("Hidden message rendered or sounded");
        checks.Add("rule_hide_suppresses_regular_and_pinned_display_and_sound");
        var audible=Message("audible",normalGroup,DateTimeOffset.UtcNow);
        Volatile.Write(ref snapshot,WithRules([muted,hidden,audible],new(){{muteId,"mute"},{hideId,"hide"}}));
        await Until(()=>soundRequests==beforeSound+1);
        if(!readingQueue.Any(m=>m.Id==PublicWebPublisher.Digest("audible")))throw new InvalidOperationException("Allowed message missing");
        checks.Add("unblocked_message_in_mixed_batch_still_sounds");
        Volatile.Write(ref snapshot,WithRules([muted,hidden,audible],new()));
        await Until(()=>readingQueue.Any(m=>m.Id==hideId));
        if(soundRequests!=beforeSound+1)throw new InvalidOperationException("Rule edit replayed historical sound");
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        if(MessageView.CountMuteBadges(this)!=0)throw new InvalidOperationException("Unmuted history retained a stale badge");
        checks.Add("removing_rule_restores_history_without_sound_replay");
        // Reproduce the card timer running before the message read callback.
        // No new message/store revision may be needed to apply changed rules.
        cloud.Activity-=ScheduleRead;
        var timerTarget=PublicWebPublisher.Digest("normal0");
        var stableStoreRevision=store.Revision;
        Volatile.Write(ref snapshot,WithRules([muted,hidden,audible],new(){{timerTarget,"hide"}}));
        await Until(()=>cloud.Rules.Revision==ruleCount);
        opportunityBoard.Rules=cloud.Rules;
        await ReadAsync();
        if(store.Revision!=stableStoreRevision||readingQueue.Any(m=>m.Id==timerTarget))throw new InvalidOperationException("Timer-first rules failed to invalidate message rendering");
        checks.Add("timer_first_rule_change_hides_existing_message_without_new_data");
        Volatile.Write(ref snapshot,"{}");await Until(()=>!cloud.RulesConnected);
        opportunityBoard.Rules=cloud.Rules;
        await ReadAsync();
        if(store.Revision!=stableStoreRevision||readingQueue.Length!=0||PinnedCard.Content is not null)throw new InvalidOperationException("Timer-first rule failure left existing private messages visible");
        checks.Add("timer_first_connection_failure_hides_existing_messages_and_pin_without_new_data");
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,regularVisible=displayed.Count,pinnedVisible=PinnedCard.Content is not null,syntheticOnly=true,realCredentialUsed=false}));
        verifyReadingTimer=false;
    }
}
