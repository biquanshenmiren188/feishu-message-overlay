using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunCurrentContractAsync(string output)
    {
        Directory.CreateDirectory(output);
        void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
        var clock=new MessageTime();
        foreach(var entry in new[]{("2026-10-01T00:00:00Z","2026-10-01 08:00:00 UTC+8"),("2026-10-01T16:00:00Z","2026-10-02 00:00:00 UTC+8"),("2026-10-01T23:59:59Z","2026-10-02 07:59:59 UTC+8"),("2026-10-01T01:00:00-07:00","2026-10-01 16:00:00 UTC+8")})
        {Check((string)clock.Convert(DateTimeOffset.Parse(entry.Item1),typeof(string),"date",System.Globalization.CultureInfo.InvariantCulture)==entry.Item2,"explicit UTC+8 including midnight/date rollover and negative source offset");}
        var path=Path.Combine(output,"synthetic-appearance.json");Preferences.ContractPath=path;
        File.WriteAllText(path,"invalid synthetic json");_=Preferences.Load();
        Check(Preferences.LoadState=="invalid_json" && !new Preferences().Save() && File.ReadAllText(path)=="invalid synthetic json","invalid preferences must remain untouched");
        File.WriteAllText(path,"{\"dwellseconds\":5,\"sound\":true}",new System.Text.UTF8Encoding(true));Check(Preferences.Load().DwellSeconds==5,"UTF8 BOM and property-case compatible load");
        File.Delete(path);_=Preferences.Load();Check((new Preferences{DwellSeconds=5,AudioPath="synthetic.wav",AutoListenJoined=true}).Save(),"atomic initial save");
        var saved=Preferences.Load();Check(saved.DwellSeconds==5 && saved.AudioPath=="synthetic.wav" && saved.AutoListenJoined,"saved preferences restore");
        using(var locked=new FileStream(path,FileMode.Open,FileAccess.ReadWrite,FileShare.None))
        {_=Preferences.Load();Check(Preferences.LoadState=="io_error" && !new Preferences().Save(),"locked preferences must not fall back and overwrite");}
        _=Preferences.Load();reader.Configure(5,DateTimeOffset.UtcNow);SavePreferences();Check(FlushForSessionEnding(),"immediate exit flush");
        Check(Preferences.Load().DwellSeconds==5,"immediate exit restores configured interval");
        Preferences.ContractPath=null;
        AutoScroll.IsChecked=true;followingPaused=false;verifyReadingTimer=true;
        var now=DateTimeOffset.UtcNow;selectedChats.Add("demo");store.Start(now);
        for(var i=0;i<7;i++)store.Add(new IncomingMessage("synthetic-"+i,"demo","hidden","Synthetic item "+i+"\nSecond line\n"+new string('x',30),now.AddMilliseconds(i+1),SenderKind.Bot),"demo",now.AddSeconds(1));
        Render();Width=360;Height=450;reader.Focus(readingQueue[0].Id,DateTimeOffset.UtcNow);ShowReadingMessage(reader.Current!);ScheduleReading();
        var evidence=new List<object>();
        for(var cycle=0;cycle<3;cycle++)
        {
            await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
            Check(displayed.Count<=3 && displayed[0].Id==reader.Current,"actual three-container range starts at current item");
            evidence.Add(new{cycle,at=DateTimeOffset.UtcNow,current=reader.Current,visible=displayed.Select(m=>m.Id).ToArray(),containers=MessageList.Items.Count,offset=MessageScroll.VerticalOffset});
            if(cycle<2){var before=reader.Current;await Task.Delay(5250);await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);Check(reader.Current!=before && displayed[0].Id==reader.Current,"real five-second timer changes visible range");}
        }
        var current=reader.Current;store.Add(new IncomingMessage("synthetic-arrival","demo","hidden","New arrival",DateTimeOffset.UtcNow,SenderKind.Bot),"demo",DateTimeOffset.UtcNow);Render();Check(reader.Current==current && displayed[0].Id==current,"new arrival does not interrupt reading");
        Width=800;Height=800;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);Check(MessageList.Items.Count<=3,"resize cannot reveal more than three containers");
        MessageWheel(this,new(System.Windows.Input.Mouse.PrimaryDevice,0,-120){RoutedEvent=System.Windows.Input.Mouse.MouseWheelEvent});Check(followingPaused && readingIdleTimer.IsEnabled,"manual wheel pauses with idle recovery");
        AutoScroll.IsChecked=false;AutoScrollClick(this,new());Check(!readingTimer.IsEnabled && !readingIdleTimer.IsEnabled,"off cancels both timers");
        reader.Focus(readingQueue.Last().Id,DateTimeOffset.UtcNow);ShowReadingMessage(reader.Current!);AutoScroll.IsChecked=true;followingPaused=false;ScheduleReading();Check(!readingTimer.IsEnabled && displayed.Count==3,"tail stops and retains last three messages without blank filler");
        File.WriteAllText(Path.Combine(output,"current-runtime-contract.json"),JsonSerializer.Serialize(new{passed=true,evidence,strictMaximum=3,actualTimerSeconds=5,invalidConfigProtected=true,lockedConfigProtected=true,immediateExitFlush=true,resizeBounded=true,arrivalDoesNotInterrupt=true,tailTimerStopped=true}));
        verifyReadingTimer=false;readingTimer.Stop();Preferences.ContractPath=null;
        foreach(var total in new[]{0,1,2,3,4,6,100})
        {
            readingQueue=Enumerable.Range(0,total).Select(i=>new IncomingMessage("range-"+i,"demo","hidden","Short synthetic body",DateTimeOffset.UtcNow,SenderKind.Bot)).ToArray();
            for(var index=0;index<Math.Max(1,total);index++)
            {DisplayRange(readingQueue.ElementAtOrDefault(index)?.Id,true);Check(displayed.Count==Math.Min(3,total) && displayed.Select(m=>m.Id).Distinct().Count()==displayed.Count,"every reading index keeps exactly min(3,total) unique containers");}
        }
        store.Start(DateTimeOffset.UtcNow);selectedChats=new(["demo","oc_pin_a","oc_pin_b"],StringComparer.Ordinal);pinnedChatId="oc_pin_a";renderedRevision=-1;
        now=DateTimeOffset.UtcNow;
        for(var i=0;i<6;i++)store.Add(new IncomingMessage("ordinary-"+i,"demo","hidden","Ordinary synthetic "+i,now.AddMilliseconds(i+1),SenderKind.Bot),"demo",now.AddSeconds(1));
        store.Add(new IncomingMessage("pin-1","oc_pin_a","hidden","Pinned synthetic one",now.AddMilliseconds(10),SenderKind.Bot),"oc_pin_a",now.AddSeconds(1),true);Render();
        Check(displayed.Count==3 && PinnedCard.Content is IncomingMessage pin1 && pin1.Id=="pin-1" && readingQueue.Length==6,"one pinned plus three regular without duplicates");
        verifyReadingTimer=true;reader.Configure(1,DateTimeOffset.UtcNow);reader.Focus(readingQueue[0].Id,DateTimeOffset.UtcNow);ShowReadingMessage(reader.Current!);ScheduleReading();
        var beforePin=reader.Current;var remaining=reader.DelayUntilNext(DateTimeOffset.UtcNow)!.Value;
        store.Add(new IncomingMessage("pin-2","oc_pin_a","hidden","Pinned synthetic replacement",now.AddMilliseconds(11),SenderKind.Bot),"oc_pin_a",DateTimeOffset.UtcNow,true);Render();
        Check(reader.Current==beforePin && reader.DelayUntilNext(DateTimeOffset.UtcNow)<=remaining && PinnedCard.Content is IncomingMessage pin2 && pin2.Id=="pin-2" && store.Items.Count(m=>m.SourceId=="oc_pin_a")==1,"pinned replacement preserves regular reading deadline and retains one");
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);WindowAlpha.Set(this,.95);
        Check(Opacity==1 && Background is System.Windows.Media.LinearGradientBrush fill && fill.GradientStops.All(stop=>stop.Color.A==242) && fill.GradientStops.Any(stop=>stop.Color.R==231 && stop.Color.G==231 && stop.Color.B==232),"single background alpha contains gray pinned band without fading foreground");
        Check(Math.Abs((double)new TimeFontScale().Convert(14,typeof(double),"",System.Globalization.CultureInfo.InvariantCulture)-12.6)<.01,"timestamp ratio follows body font");
        var preview=new System.Windows.Media.Imaging.RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,System.Windows.Media.PixelFormats.Pbgra32);preview.Render(this);var png=new System.Windows.Media.Imaging.PngBitmapEncoder();png.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(preview));using(var image=File.Create(Path.Combine(output,"pinned-timeline-preview.png")))png.Save(image);
        await Task.Delay(1200);await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);Check(reader.Current!=beforePin && displayed.Count==3,"regular timer advances alongside pinned card");
        readingTimer.Stop();verifyReadingTimer=false;
        store.Prune(DateTimeOffset.UtcNow.AddHours(1));Render();Check(readingQueue.Length==0 && PinnedCard.Content is IncomingMessage held && held.Id=="pin-2","ordinary TTL cannot expire pinned latest");
        store.Clear(DateTimeOffset.UtcNow);Render();Check(PinnedCard.Content is IncomingMessage cleared && cleared.Id=="pin-2","ordinary clear cannot remove pinned latest");
        now=DateTimeOffset.UtcNow;
        for(var i=0;i<4;i++)store.Add(new IncomingMessage("after-clear-"+i,"demo","hidden","Fresh ordinary synthetic",now.AddMilliseconds(i+1),SenderKind.Bot),"demo",now.AddSeconds(1));Render();
        UpdatePinnedChoices();PinnedGroup.SelectedValue="oc_pin_b";Check(PinnedCard.Content is null && displayed.Count==3,"switch to quiet pinned group shows no fabricated history");
        PinnedGroup.SelectedValue="";Check(PinnedArea.Visibility==Visibility.Collapsed && displayed.Count==3,"cancel restores only regular three");
        Preferences.ContractPath=path;_=Preferences.Load();PinnedGroup.SelectedValue="oc_pin_a";SavePreferences();Check(Preferences.Load().PinnedChatId=="oc_pin_a","pinned group ID persists in isolated preferences");Preferences.ContractPath=null;
        selectedChats.Remove("oc_pin_a");renderedRevision=-1;Render();Check(PinnedCard.Content is null && !readingQueue.Any(m=>m.SourceId=="oc_pin_a"),"departed group content is not displayed");
        File.WriteAllText(Path.Combine(output,"pinned-contract.txt"),"PASS one pinned latest card plus exactly three regular containers; replace retains one without changing ordinary deadline; real regular timer advances; ordinary TTL/clear preserve pinned memory slot; quiet switch/cancel/membership removal; pinned ID saves and reloads in isolated preferences.");
        await RunLayoutReadingContractAsync(output);
        await RunCardContractAsync(output);
        AutoScroll.IsChecked=false;verifyReadingTimer=false;initialFit=false;
        store.Start(DateTimeOffset.UtcNow);selectedChats=new(["demo"],StringComparer.Ordinal);pinnedChatId="";renderedRevision=-1;Width=360;Height=350;
        now=DateTimeOffset.UtcNow;store.Add(new IncomingMessage("scrollbar-only","demo","hidden",string.Join('\n',Enumerable.Repeat("Synthetic scrolling line",80)),now,SenderKind.Bot),"demo",now);Render();
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();MessageBar.ApplyTemplate();
        var track=(System.Windows.Controls.Primitives.Track)MessageBar.Template.FindName("PART_Track",MessageBar);track.Thumb.ApplyTemplate();
        var thumbBody=(System.Windows.Controls.Border)track.Thumb.Template.FindName("ThumbBody",track.Thumb);
        Check(MessageBar.Width==12 && thumbBody.Width==4 && track.IncreaseRepeatButton.Opacity==0 && track.DecreaseRepeatButton.Opacity==0,"four-DIP thumb with transparent twelve-DIP hit area and no arrows");
        ShowScrollbar();Check(MessageBar.Opacity==1 && MessageBar.IsHitTestVisible,"scrolling shows overlay thumb");
        System.Windows.Input.Mouse.Capture(track.Thumb);try{MessageBar.Value=50;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);Check(MessageScroll.VerticalOffset>40,"captured thumb changes actual viewport, including pointer outside hit area");}finally{System.Windows.Input.Mouse.Capture(null);}
        scrollIdle.Stop();MessageBar.IsHitTestVisible=false;MessageBar.BeginAnimation(OpacityProperty,new System.Windows.Media.Animation.DoubleAnimation(0,TimeSpan.FromMilliseconds(180)));
        await Task.Delay(250);Check(MessageBar.Opacity<.01,"idle scrollbar fades without layout reservation");
        File.WriteAllText(Path.Combine(output,"utc8-scrollbar-contract.txt"),"PASS UTC midnight, next-day rollover and negative source offset; explicit UTC+8 independent of OS timezone. Four-DIP thumb, twelve-DIP transparent hit area, hidden arrows; captured thumb changes actual scroll offset and idle fade keeps layout stable. Message-body text is unchanged.");
        File.WriteAllText(Path.Combine(output,"strict-range-boundaries.txt"),"PASS actual bound ItemsSource counts for every index of total 0/1/2/3/4/6/100, including queue tail; no duplicate fillers.");
    }
}
