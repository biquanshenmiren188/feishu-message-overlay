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
        App.SmokeStage="font_fit";
        contractFitHeight=Math.Min(720,CurrentWorkArea().Height);
        void Check(bool ok,string why){if(!ok)throw new InvalidOperationException(why);}
        async Task Layout(){await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();}
        var samples=new List<object>();
        void Sample(string stage)=>samples.Add(new{stage,at=DateTimeOffset.UtcNow,current=reader.Current,preferred=FontScale.Value,effective=MessageList.FontSize,fitStatus,fitPasses,total=fitRequiredHeight,available=fitAvailableHeight,height=ActualHeight,viewport=MessageScroll.ViewportHeight,extent=MessageScroll.ExtentHeight,offset=MessageScroll.VerticalOffset,regular=displayed.Count,pinned= PinnedCard.Content is not null});
        void Add(string id,string chat,int lines){var now=DateTimeOffset.UtcNow;Check(store.Add(new(id,chat,"hidden",string.Join('\n',Enumerable.Range(0,lines).Select(i=>"Synthetic field "+i+": readable value")),now,SenderKind.Bot),chat,now,chat==pinnedChatId),"fixture add");Render();}
        store.Start(DateTimeOffset.UtcNow);selectedChats=new(["demo","pin"],StringComparer.Ordinal);pinnedChatId="pin";pinnedLatest=null;renderedRevision=-1;
        AutoScroll.IsChecked=false;readingTimer.Stop();readingIdleTimer.Stop();followingPaused=false;
        Width=360;initialFit=true;verifyContentFit=true;FontScale.Value=13;reader.Configure(5,DateTimeOffset.UtcNow);await Layout();
        // Find a fixture that needs shrinking but can fit at the protected floor.
        // Fixed 26/26/28 lines only fit our large desktop, not CI's smaller desktop.
        var fixtureHeight=contractFitHeight.Value;
        var fixtureWidth=MessageScroll.ViewportWidth>0?MessageScroll.ViewportWidth:ActualWidth-11;
        double FixtureHeight(int lines,double font)
        {
            MessageList.FontSize=font;
            double Card(int count)=>MeasureCard(new IncomingMessage("measure-only","demo","hidden",string.Join('\n',Enumerable.Range(0,count).Select(i=>"Synthetic field "+i+": readable value")),DateTimeOffset.UtcNow,SenderKind.Bot),fixtureWidth);
            return Card(lines)*2+Card(lines+2)+Card(3)+40;
        }
        var fittingLines=3;
        while(fittingLines<200 && FixtureHeight(fittingLines,13)<=fixtureHeight)fittingLines++;
        Check(fittingLines<200 && FixtureHeight(fittingLines,MinimumFitFontSize)<=fixtureHeight,"fixture must require shrink and still fit the available desktop at protected minimum");
        MessageList.FontSize=13;
        Add("fit-a","demo",fittingLines);Add("fit-b","demo",fittingLines);await Layout();var beforeArrival=ActualHeight;
        Add("fit-c","demo",fittingLines+2);Add("pin-a","pin",3);await Layout();Sample("pin-plus-three-shrink");
        Check(displayed.Count==3 && PinnedCard.Content is not null && MessageList.FontSize<13 && MessageList.FontSize>=MinimumFitFontSize && fitStatus=="fully_fitted","pin plus three actual long containers shrink at readable floor");
        Check(MessageScroll.ScrollableHeight<2 && PinnedArea.ScrollableHeight<2 && ActualHeight<=CurrentWorkArea().Height+.5 && ActualHeight>beforeArrival,"new arrival final width remeasure fully shows all four bodies");
        var bmp=new System.Windows.Media.Imaging.RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,System.Windows.Media.PixelFormats.Pbgra32);bmp.Render(this);var encoder=new System.Windows.Media.Imaging.PngBitmapEncoder();encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));using(var image=File.Create(Path.Combine(output,"font-fit-preview.png")))encoder.Save(image);
        var path=Path.Combine(output,"fit-preference.json");Preferences.ContractPath=path;_=Preferences.Load();SavePreferences();Check(Preferences.Load().FontSize==13 && MessageList.FontSize<13,"effective fitted size never overwrites preferred persisted size");Preferences.ContractPath=null;
        Width=520;RequestContentLayout();await Layout();Sample("wider-restores-font");Check(fitStatus=="fully_fitted" && MessageScroll.ScrollableHeight<2 && MessageList.FontSize<=13,"width change refits without clipping");
        initialFit=false;Height=500;RequestContentLayout();await Layout();Sample("manual-small-window");Check(fitStatus=="manual_overflow_at_minimum" && MessageList.FontSize==MinimumFitFontSize,"too-small window has explicit readable floor rather than microscopic fit");
        // Explicitly reject automatic paging even when multiple extreme bodies cannot fit.
        store.Start(DateTimeOffset.UtcNow);pinnedLatest=null;pinnedChatId="";renderedRevision=-1;Width=360;Height=400;initialFit=false;
        Add("extreme-a","demo",200);Add("extreme-b","demo",200);Add("extreme-c","demo",200);await Layout();
        reader.Focus("extreme-a",DateTimeOffset.UtcNow);ShowReadingMessage("extreme-a");await Layout();AutoScroll.IsChecked=true;verifyReadingTimer=true;ScheduleReading();Sample("extreme-start");
        Check(fitStatus=="manual_overflow_at_minimum" && MessageList.FontSize==MinimumFitFontSize && fitPasses<=9,"extreme input remains bounded and explicitly cannot fit readably");
        var offset=MessageScroll.VerticalOffset;await Task.Delay(2200);await Layout();Check(reader.Current=="extreme-a" && Math.Abs(MessageScroll.VerticalOffset-offset)<.5,"no intra-message page movement before dwell");
        await Task.Delay(3050);await Layout();Sample("extreme-next-ID-only");Check(reader.Current=="extreme-b","five-second timer advances only to next message, never a page within same message");
        reader.Focus("extreme-c",DateTimeOffset.UtcNow);ShowReadingMessage("extreme-c");await Layout();ScheduleReading();offset=MessageScroll.VerticalOffset;
        Check(!readingTimer.IsEnabled,"last extreme message has no page timer");await Task.Delay(600);Check(Math.Abs(MessageScroll.VerticalOffset-offset)<.5,"tail never auto-pages");
        MessageScroll.ScrollToEnd();await Layout();Check(CurrentBottomRemaining()<2,"manual scroll still reaches complete extreme body");
        readingTimer.Stop();AutoScroll.IsChecked=false;verifyReadingTimer=false;
        // Short ordinary queue, real dwell and manual ten-second recovery retained.
        store.Start(DateTimeOffset.UtcNow);renderedRevision=-1;initialFit=true;Width=360;
        for(var i=0;i<5;i++)Add("short-"+i,"demo",2);await Layout();reader.Focus("short-0",DateTimeOffset.UtcNow);ShowReadingMessage("short-0");await Layout();AutoScroll.IsChecked=true;verifyReadingTimer=true;ScheduleReading();
        await Task.Delay(5250);await Layout();Check(reader.Current=="short-1" && displayed.Count==3,"real dwell advances regular range");
        MessageWheel(this,new(Mouse.PrimaryDevice,0,120){RoutedEvent=Mouse.MouseWheelEvent});await Layout();var paused=reader.Current;
        await Task.Delay(9100);Check(followingPaused && reader.Current==paused,"manual pause lasts ten seconds");await Task.Delay(1300);await Layout();Check(!followingPaused,"manual idle resumes");var resumed=reader.Current;
        await Task.Delay(5250);await Layout();Check(reader.Current!=resumed && displayed.Count==3,"resume starts full dwell before next message");Sample("short-after-resume");
        readingTimer.Stop();readingIdleTimer.Stop();AutoScroll.IsChecked=false;verifyReadingTimer=false;verifyContentFit=false;initialFit=false;
        contractFitHeight=null;
        File.WriteAllText(Path.Combine(output,"font-fit-runtime.json"),JsonSerializer.Serialize(new{passed=true,fixtureHeight,fittingLines,minimumFont=MinimumFitFontSize,maximumMeasurementPasses=9,automaticPaging=false,preferredFontPreserved=true,samples}));
    }
}
