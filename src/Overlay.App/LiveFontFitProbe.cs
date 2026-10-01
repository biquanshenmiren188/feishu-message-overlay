using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    internal void PrepareFitProbe(){Pin.IsChecked=false;Topmost=false;ShowActivated=false;}
    // Explicit local-only verification: read this application's displayed bodies directly
    // into memory. Never export body strings, source/group identities, screenshots or secrets.
    internal async Task MeasureCurrentWindowAsync(int pid,string output)
    {
        var process=System.Diagnostics.Process.GetProcessById(pid);
        if(process.ProcessName!="FeishuMessageOverlay")throw new InvalidOperationException("Wrong probe process");
        var roots=AutomationElement.RootElement.FindAll(TreeScope.Children,new PropertyCondition(AutomationElement.ProcessIdProperty,pid));
        var bodies=new List<string>();string? pinned=null;
        string ReadBody(AutomationElement element)
        {
            var pieces=new List<string>();var skippedClock=false;
            foreach(AutomationElement text in element.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.Text)))
            {
                if(text.Current.ClassName!="TextBlock")continue;
                var value=text.Current.Name;
                if(!skippedClock && Regex.IsMatch(value,@"^\d{2}:\d{2}:\d{2}$")){skippedClock=true;continue;}
                if(value.Length>0)pieces.Add(value);
            }
            return string.Join('\n',pieces);
        }
        foreach(AutomationElement root in roots)
        {
            var list=root.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"MessageList"));
            if(list is not null)
            {
                var transform=System.Windows.PresentationSource.FromVisual(this)?.CompositionTarget?.TransformFromDevice??System.Windows.Media.Matrix.Identity;
                Width=Math.Max(MinWidth,root.Current.BoundingRectangle.Width*transform.M11);
                foreach(AutomationElement item in list.FindAll(TreeScope.Descendants,new PropertyCondition(AutomationElement.ControlTypeProperty,ControlType.ListItem)))
                {if(bodies.Count<3){var body=ReadBody(item);if(body.Length>0)bodies.Add(body);}}
            }
            var pin=root.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"PinnedCard"))??root.FindFirst(TreeScope.Descendants,new PropertyCondition(AutomationElement.AutomationIdProperty,"PinnedArea"));
            if(pin is not null){var body=ReadBody(pin);if(body.Length>0)pinned=body;}
        }
        var now=DateTimeOffset.UtcNow;selectedChats=new(["live","live-pin"],StringComparer.Ordinal);store.Start(now);pinnedChatId="live-pin";pinnedLatest=null;renderedRevision=-1;
        initialFit=true;verifyContentFit=true;AutoScroll.IsChecked=false;
        for(var i=0;i<bodies.Count;i++)store.Add(new("live-"+i,"live","",bodies[i],now.AddMilliseconds(i+1),SenderKind.Bot),"live",now.AddSeconds(1));
        if(pinned is not null)store.Add(new("live-pin","live-pin","",pinned,now.AddMilliseconds(10),SenderKind.Bot),"live-pin",now.AddSeconds(1),true);
        Render();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        if(displayed.Count!=bodies.Count || (PinnedCard.Content is not null)!=(pinned is not null))throw new InvalidOperationException("Probe did not render complete captured set");
        var result=new{capturedRegular=bodies.Count,renderedRegular=displayed.Count,capturedPinned=pinned is not null,renderedPinned=PinnedCard.Content is not null,characterCounts=bodies.Select(s=>s.Length).ToArray(),pinnedCharacterCount=pinned?.Length??0,preferred=FontScale.Value,effective=MessageList.FontSize,minimum=MinimumFitFontSize,status=fitStatus,required=fitRequiredHeight,available=fitAvailableHeight,regularExtent=MessageScroll.ExtentHeight,regularViewport=MessageScroll.ViewportHeight,pinExtent=PinnedArea.ExtentHeight,pinViewport=PinnedArea.ViewportHeight,measurementPasses=fitPasses,privateContentSaved=false,automaticPaging=false};
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(result));
        bodies.Clear();pinned=null;store.Clear(DateTimeOffset.UtcNow);pinnedLatest=null;PinnedCard.Content=null;displayed.Clear();
    }
}
