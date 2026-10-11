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
        store.Prune(now.AddHours(24));Render();Check(readingQueue.Length==100 && displayed.Count==3,"quiet day never expires accepted history");
        AutoScroll.IsChecked=true;verifyReadingTimer=true;reader.Configure(1,now);
        HistoryClick(this,new());
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Check(browsingHistory && displayed[0].Id=="history-5" && !readingTimer.IsEnabled && !readingIdleTimer.IsEnabled && HistoryLabel.Text=="最新","history starts at oldest and holds reading");
        MessageWheel(this,new(System.Windows.Input.Mouse.PrimaryDevice,0,-120){RoutedEvent=System.Windows.Input.Mouse.MouseWheelEvent});
        Check(!readingIdleTimer.IsEnabled,"history scroll cannot arm idle resume");
        var before=reader.Current;
        Hide();Show();await Task.Delay(11000);await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        ReadingTick(); // A previously queued tick must also respect explicit history mode.
        Check(reader.Current==before && !readingTimer.IsEnabled && browsingHistory,"history remains paused after visibility and idle recovery interval");
        rangeStart=readingQueue[20].Id;DisplayRange(rangeStart,true);reader.Focus(rangeStart,DateTimeOffset.UtcNow);before=reader.Current;
        store.Add(new IncomingMessage("history-new","demo","","新推送",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();
        Check(reader.Current==before && displayed[0].Id==before && readingQueue.Length==100,"new push preserves history reading and capacity");
        HistoryClick(this,new());await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Check(!browsingHistory && displayed.Last().Id=="history-new" && HistoryLabel.Text=="历史","return to latest shows newest range");
        readingTimer.Stop();verifyReadingTimer=false;AutoScroll.IsChecked=false;
        Width=300;Height=400;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        Check(HistoryButton.ActualWidth==36 && HistoryButton.TranslatePoint(new Point(HistoryButton.ActualWidth,0),this).X<Sound.TranslatePoint(new Point(0,0),this).X,"history button fits minimum window width");
        var preview=new System.Windows.Media.Imaging.RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,System.Windows.Media.PixelFormats.Pbgra32);preview.Render(this);
        var png=new System.Windows.Media.Imaging.PngBitmapEncoder();png.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(preview));using(var file=File.Create(Path.Combine(output,"history-preview.png")))png.Save(file);
        store.Clear(DateTimeOffset.UtcNow);Render();Check(readingQueue.Length==0 && !HistoryButton.IsEnabled,"explicit clear still removes history");
        File.WriteAllText(Path.Combine(output,"history-contract.json"),JsonSerializer.Serialize(new{passed=true,capacity=100,idleHours=24,historyIdleSeconds=11,historyPaused=true,newArrivalPreservesPosition=true,minimumWidth=300,explicitClear=true,syntheticOnly=true}));
    }
}
