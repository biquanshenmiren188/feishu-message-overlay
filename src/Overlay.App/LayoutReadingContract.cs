using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    private async Task RunLayoutReadingContractAsync(string output)
    {
        void Check(bool ok,string why){if(!ok)throw new InvalidOperationException(why);}
        async Task Layout(){await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();}
        var samples=new List<object>();
        void Sample(string stage)=>samples.Add(new{stage,at=DateTimeOffset.UtcNow,current=reader.Current,ids=displayed.Select(m=>m.Id).ToArray(),height=ActualHeight,viewport=MessageScroll.ViewportHeight,extent=MessageScroll.ExtentHeight,offset=MessageScroll.VerticalOffset,bottomRemaining=CurrentBottomRemaining(),paused=followingPaused,timer=readingTimer.IsEnabled});
        void Add(string id,string chat,string text){var now=DateTimeOffset.UtcNow;Check(store.Add(new(id,chat,"hidden",text,now,SenderKind.Bot),chat,now,chat==pinnedChatId),"fixture add");Render();}
        store.Start(DateTimeOffset.UtcNow);selectedChats=new(["demo","pin"],StringComparer.Ordinal);pinnedChatId="pin";pinnedLatest=null;renderedRevision=-1;
        AutoScroll.IsChecked=false;readingTimer.Stop();readingIdleTimer.Stop();followingPaused=false;
        Width=360;initialFit=true;verifyContentFit=true;reader.Configure(5,DateTimeOffset.UtcNow);
        Add("fit-a","demo","Short first\nSecond line");Add("fit-b","demo","Short second\nSecond line");await Layout();var shortHeight=ActualHeight;
        Add("fit-c","demo",string.Join('\n',Enumerable.Repeat("Readable synthetic longer line https://example.com/safe?a=1",10)));await Layout();
        Sample("new-third-long-fitted");Check(ActualHeight>shortHeight+100 && MessageScroll.ScrollableHeight<3,"new long arrival remeasures real final width and fully fits three bodies");
        Add("pin-a","pin","Pinned synthetic\nSecond line");await Layout();Sample("pinned-plus-three");var bmp=new System.Windows.Media.Imaging.RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,System.Windows.Media.PixelFormats.Pbgra32);bmp.Render(this);var encoder=new System.Windows.Media.Imaging.PngBitmapEncoder();encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));using(var image=File.Create(Path.Combine(output,"actual-fit-preview.png")))encoder.Save(image);Check(displayed.Count==3 && PinnedArea.Visibility==Visibility.Visible && MessageScroll.ScrollableHeight<3,"pin plus actual three bodies fit without bottom clipping");
        Width=520;RequestContentLayout();await Layout();Sample("width-remeasured");Check(MessageScroll.ScrollableHeight<3,"width change remeasures final text wrapping");
        // Manual-size mode: a single long body takes several pages; timer must show its bottom first.
        store.Start(DateTimeOffset.UtcNow);pinnedChatId="";pinnedLatest=null;renderedRevision=-1;initialFit=false;Width=360;Height=420;
        Add("page-a","demo",string.Join('\n',Enumerable.Range(0,27).Select(i=>"Synthetic readable line "+i)));
        Add("page-b","demo","Short second body");Add("page-c","demo","Third complete body");Add("page-d","demo","Fourth body");
        await Layout();reader.Focus("page-a",DateTimeOffset.UtcNow);ShowReadingMessage("page-a");await Layout();
        AutoScroll.IsChecked=true;verifyReadingTimer=true;ScheduleReading();Sample("long-start");var offset=MessageScroll.VerticalOffset;
        await Task.Delay(5250);await Layout();Sample("long-first-page");Check(reader.Current=="page-a" && MessageScroll.VerticalOffset>offset+20,"first real five-second tick scrolls within long body without skipping ID");
        Check(CurrentBottomRemaining()<2,"long body's bottom actually shown before next dwell");
        await Task.Delay(5250);await Layout();Sample("long-next-message");Check(reader.Current=="page-b","only after complete bottom page dwell advances ID");
        await Task.Delay(5250);await Layout();Sample("next-third");Check(reader.Current=="page-c" && displayed.Count==3,"second real visual cycle retains three at tail");
        AutoScroll.IsChecked=false;AutoScrollClick(this,new());var held=reader.Current;await Task.Delay(550);Check(reader.Current==held && !readingTimer.IsEnabled,"off no timer");
        AutoScroll.IsChecked=true;reader.Focus("page-b",DateTimeOffset.UtcNow);ShowReadingMessage("page-b");await Layout();ScheduleReading();
        MessageWheel(this,new(Mouse.PrimaryDevice,0,120){RoutedEvent=Mouse.MouseWheelEvent});Sample("manual-pause");var pausedId=reader.Current;await Layout();var resumeId=displayed.FirstOrDefault(item=>MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el && el.TranslatePoint(new Point(),MessageScroll).Y+el.ActualHeight>0)?.Id;
        await Task.Delay(9100);await Layout();Check(followingPaused && reader.Current==pausedId,"manual pause does not resume before ten seconds");
        await Task.Delay(1300);await Layout();Sample("ten-second-resume");File.WriteAllText(Path.Combine(output,"resume-debug.json"),JsonSerializer.Serialize(new{pausedId,resumeId,current=reader.Current,followingPaused,idleEnabled=readingIdleTimer.IsEnabled,visible=IsVisible,automatic=AutoScroll.IsChecked,samples}));Check(!followingPaused && reader.Current==resumeId,"ten-second recovery begins full dwell from visible item");
        await Task.Delay(5250);await Layout();Sample("resumed-full-dwell");Check(reader.Current==resumeId && MessageScroll.VerticalOffset>20 && CurrentBottomRemaining()<2,"resumed full five-second dwell advances to unread bottom page before ID");
        await Task.Delay(5250);await Layout();Sample("resumed-next-id");Check(reader.Current!=resumeId,"resumed long body advances only after bottom page dwell");
        readingTimer.Stop();AutoScroll.IsChecked=false;verifyReadingTimer=false;
        // Overscreen arrival remains readable at work-area clamp; tail keeps three containers.
        initialFit=true;Width=360;Add("huge-arrival","demo",string.Join('\n',Enumerable.Repeat("Long synthetic body",100)));reader.Focus("huge-arrival",DateTimeOffset.UtcNow);ShowReadingMessage("huge-arrival");await Layout();
        Sample("overscreen-tail");Check(ActualHeight<=CurrentWorkArea().Height+.5 && displayed.Count==3 && MessageScroll.ScrollableHeight>0,"overscreen content clamps height but remains scrollable with last three");
        MessageScroll.ScrollToEnd();await Layout();Check(CurrentBottomRemaining()<2,"overscreen last body can be read fully to bottom");
        File.WriteAllText(Path.Combine(output,"layout-reading-runtime.json"),JsonSerializer.Serialize(new{passed=true,samples,realDispatcherTimer=true,seconds=5,newArrivalMeasured=true,pinnedAndRegularMeasured=true,manualIdleSeconds=10}));
        verifyContentFit=false;initialFit=false;readingIdleTimer.Stop();
    }
}
