using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    private async Task RunCardContractAsync(string output)
    {
        App.SmokeStage="structured_card";
        void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
        using(var meta=JsonDocument.Parse("{\"buttons\":1,\"targets\":0,\"header\":false,\"title\":true,\"callback\":true,\"shapes\":[\"behaviors:array\"],\"detail\":\"disabled\",\"code\":null,\"appSecret\":\"synthetic-private\"}"))
        {var safe=CardMetadata.Project(meta.RootElement);Check(safe is {Buttons:1,Targets:0,Code:null} && !JsonSerializer.Serialize(safe).Contains("synthetic-private"),"card field-shape whitelist accepts null code and excludes every payload/secret field");}
        async Task Layout(){await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();}
        var url="https://example.com/radar?combo=DEMO.A.B&query="+new string('x',120)+"&encoded=%E4%B8%AD%E6%96%87&tab=FF";
        IncomingMessage Card(string id,string chat,string tone="grey")
        {
            var content=JsonSerializer.Serialize(new{header=new{template=tone,title=new{tag="plain_text",content="Synthetic native title "+id}},elements=new object[]{new{tag="markdown",content="**First paragraph**\nSecond paragraph\nThird paragraph\n"+url},new{tag="action",actions=new[]{new{tag="button",text=new{tag="plain_text",content="View radar"},behaviors=new[]{new{type="open_url",default_url=url}}}}}}});
            var json=JsonSerializer.Serialize(new{header=new{event_type="im.message.receive_v1"},@event=new{sender=new{sender_type="bot",sender_id=new{open_id="fixture-bot"}},message=new{chat_id=chat,chat_type="group",message_id=id,message_type="interactive",create_time=DateTimeOffset.UtcNow.AddMilliseconds(5).ToUnixTimeMilliseconds().ToString(),content}}});
            return new BotEventFilter(["demo","pin"]).Parse(json)??throw new InvalidOperationException("Synthetic card failed parsing");
        }
        store.Start(DateTimeOffset.UtcNow);selectedChats=new(["demo","pin"],StringComparer.Ordinal);pinnedChatId="pin";pinnedLatest=null;renderedRevision=-1;
        Width=360;initialFit=true;verifyContentFit=true;AutoScroll.IsChecked=false;FontScale.Value=13;contractFitHeight=720;
        for(var i=0;i<6;i++){var m=Card("card-"+i,"demo",i%2==0?"red":"blue");Check(store.Add(m,"demo",DateTimeOffset.UtcNow.AddSeconds(1)),"card accepted");}
        var pin=Card("card-pin","pin");Check(store.Add(pin,"pin",DateTimeOffset.UtcNow.AddSeconds(1),true),"pin card accepted");Render();await Layout();
        Check(displayed.Count==readingQueue.Length && PinnedCard.Content is IncomingMessage{Card:not null},"native one pin plus continuous card history");
        File.WriteAllText(Path.Combine(output,"card-fit-check.json"),JsonSerializer.Serialize(new{fitStatus,font=MessageList.FontSize,total=fitRequiredHeight,available=fitAvailableHeight,regularExtent=MessageScroll.ExtentHeight,regularViewport=MessageScroll.ViewportHeight,pinExtent=PinnedArea.ExtentHeight,pinViewport=PinnedArea.ViewportHeight}));
        Check(MessageList.FontSize==13 && MessageScroll.ScrollableHeight>0 && PinnedArea.ScrollableHeight<2,"long structured history scrolls at preferred font with accessible pin");
        var first=displayed[0];var container=(FrameworkElement)MessageList.ItemContainerGenerator.ContainerFromItem(first);var view=Descendants<MessageView>(container).FirstOrDefault();
        Check(view is not null,"real card view instantiated");
        var captions=Descendants<TextBlock>(view!).Select(x=>x.Text).ToArray();Check(captions.Contains(first.Card!.Title) && !captions.Any(x=>x.Contains("未读取")),"source title preserved and requested appended warning absent");
        Check(Descendants<TextBlock>(view!).Any(x=>x.Inlines.OfType<System.Windows.Documents.Run>().Any(r=>r.Text=="First paragraph" && r.FontWeight==FontWeights.Bold)),"source markdown emphasis renders without modifying body text");
        var button=Descendants<Button>(view!).Single();Uri? launched=null;var previous=MessageText.Launch;MessageText.Launch=u=>launched=u;
        try{button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));Check(launched?.OriginalString==url,"actual card button click keeps complete long URI without network");}finally{MessageText.Launch=previous;}
        Check(Opacity==1,"foreground stays opaque");
        var screenshot=new System.Windows.Media.Imaging.RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,PixelFormats.Pbgra32);screenshot.Render(this);var encoder=new System.Windows.Media.Imaging.PngBitmapEncoder();encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(screenshot));using(var file=File.Create(Path.Combine(output,"card-preview.png")))encoder.Save(file);
        var samples=new List<object>();void Sample()=>samples.Add(new{at=DateTimeOffset.UtcNow,current=reader.Current,range=rangeStart,regular=displayed.Count,pin=PinnedCard.Content is not null,font=MessageList.FontSize,total=fitRequiredHeight,available=fitAvailableHeight,extent=MessageScroll.ExtentHeight,viewport=MessageScroll.ViewportHeight,offset=MessageScroll.VerticalOffset});
        reader.Configure(5,DateTimeOffset.UtcNow);reader.Focus(readingQueue[0].Id,DateTimeOffset.UtcNow);ShowReadingMessage(reader.Current!);AutoScroll.IsChecked=true;verifyReadingTimer=true;await Layout();ScheduleReading();Sample();
        for(var step=0;step<2;step++){var before=reader.Current;await Task.Delay(5250);await Layout();Check(reader.Current!=before && displayed.Any(m=>m.Id==reader.Current) && displayed.Count==readingQueue.Length && PinnedCard.Content is IncomingMessage,"actual five-second card range advances without losing pinned card");Sample();}
        AutoScroll.IsChecked=false;readingTimer.Stop();verifyReadingTimer=false;contractFitHeight=null;verifyContentFit=false;initialFit=false;
        File.WriteAllText(Path.Combine(output,"card-runtime.json"),JsonSerializer.Serialize(new{passed=true,buttonQueryPreserved=true,warningRemoved=true,privateContent=false,samples}));
    }
    private static IEnumerable<T> Descendants<T>(DependencyObject root) where T:DependencyObject
    {for(var i=0;i<VisualTreeHelper.GetChildrenCount(root);i++){var child=VisualTreeHelper.GetChild(root,i);if(child is T typed)yield return typed;foreach(var descendant in Descendants<T>(child))yield return descendant;}}
}
