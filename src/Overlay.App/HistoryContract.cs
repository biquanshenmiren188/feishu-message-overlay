using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;

public partial class MainWindow
{
    private async Task RunHistoryContractAsync(string output)
    {
        void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
        var now=DateTimeOffset.UtcNow;
        store.Start(now.AddSeconds(-10));selectedChats=new(["demo"],StringComparer.Ordinal);pinnedChatId="";renderedRevision=-1;
        for(var i=0;i<105;i++)store.Add(new IncomingMessage("history-"+i,"demo","","历史推送 "+i,now.AddSeconds(-5).AddMilliseconds(i),SenderKind.Bot),"demo",now);
        Render();Check(readingQueue.Length==100 && readingQueue[0].Id=="history-5","history capacity evicts oldest only");
        store.Prune(now.AddHours(24));Render();Check(readingQueue.Length==100 && displayed.Count==readingQueue.Length,"quiet day never expires accepted history");
        AutoScroll.IsChecked=false;verifyReadingTimer=false;readingTimer.Stop();readingIdleTimer.Stop();
        DisplayRange(readingQueue[^1].Id,true);
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        MessageScroll.ScrollToTop();UpdateLayout();
        for(var i=0;i<100;i++)MessageWheel(this,new(System.Windows.Input.Mouse.PrimaryDevice,0,120){RoutedEvent=System.Windows.Input.Mouse.MouseWheelEvent});
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Check(displayed[0].Id=="history-5" && displayed.Count==readingQueue.Length,"original mouse wheel reaches oldest retained push after idle");
        rangeStart=readingQueue[20].Id;DisplayRange(rangeStart,true);reader.Focus(rangeStart,DateTimeOffset.UtcNow);var before=reader.Current;
        store.Add(new IncomingMessage("history-new","demo","","新推送",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        Check(reader.Current==before && displayed.Any(m=>m.Id==before) && readingQueue.Length==100,"new push preserves scrollback position and capacity");
        store.Clear(DateTimeOffset.UtcNow);Render();Check(readingQueue.Length==0,"explicit clear still removes history");
        File.WriteAllText(Path.Combine(output,"history-contract.json"),JsonSerializer.Serialize(new{passed=true,capacity=100,idleHours=24,originalWheelReachesOldest=true,newArrivalPreservesPosition=true,explicitClear=true,syntheticOnly=true}));
    }
}