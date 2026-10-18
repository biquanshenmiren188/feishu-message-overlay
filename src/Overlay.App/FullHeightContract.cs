using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    internal int ViewportMessageCount()=>displayed.Count(item=>MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el && el.TranslatePoint(new Point(),MessageScroll).Y<MessageScroll.ViewportHeight && el.TranslatePoint(new Point(0,el.ActualHeight),MessageScroll).Y>0);
    internal async Task RunFullHeightContractAsync(string output)
    {
        var checks=new List<string>();var samples=new List<object>();
        void Check(bool ok,string why){if(!ok)throw new InvalidOperationException(why);checks.Add(why);}
        async Task Layout(){for(var pass=0;pass<4;pass++){await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();}}
        var now=DateTimeOffset.UtcNow;store.Start(now.AddMinutes(-5));selectedChats=new(["demo","pin"],StringComparer.Ordinal);pinnedChatId="pin";renderedRevision=-1;
        AutoScroll.IsChecked=false;readingTimer.Stop();readingIdleTimer.Stop();initialFit=true;verifyContentFit=true;Width=360;FontScale.Value=13;lastFitKey=null;
        void Add(int i)
        {
            var body="买 Bitget 永续 → 卖 Bybit 永续\n均值：净收益0.126%｜盘口差+0.344%｜指数差+0.007%\n"+(i%3==0?"⚠ 警告：Bybit 1h 成本：资金费计算方式不同":"");
            var card=new MessageCard("TOKEN"+i+"｜FF｜V2收敛｜R0 +0.34%",body,[new("查看雷达","https://example.invalid/radar/?q=TOKEN"+i)]);
            store.Add(new IncomingMessage("fill-"+i,"demo","",body,now.AddSeconds(-120+i),SenderKind.Bot){Card=card},"demo",now);
        }
        for(var i=0;i<30;i++)Add(i);
        var pin=new MessageCard("强信号｜TOKEN｜2组","R0｜FF｜买 BINANCE → 卖 BYBIT\n净均 +0.24%\nR0｜FF｜买 BITGET → 卖 BYBIT\n净均 +0.20%",[new("查看组合","https://example.invalid/radar/?combo=fixture")],"red");
        store.Add(new IncomingMessage("pin","pin","",pin.Body,now,SenderKind.Bot){Card=pin},"pin",now,true);
        alignLatestAfterLayout=true;Render();await Layout();
        Check(Math.Abs(ActualHeight-CurrentWorkArea().Height)<2,"window fills monitor work area height");
        Check(displayed.Count==30 && ViewportMessageCount()>3,"viewport shows more than three real messages");
        Check(Math.Abs(MessageScroll.VerticalOffset-MessageScroll.ScrollableHeight)<2,"initial viewport includes latest message and fills bottom");
        Check(MessageList.FontSize==13 && FontScale.Value==13,"history does not shrink chosen font");
        samples.Add(new{stage="initial",height=ActualHeight,viewport=MessageScroll.ViewportHeight,visible=ViewportMessageCount(),retained=displayed.Count,font=MessageList.FontSize});
        var image=new RenderTargetBitmap((int)Math.Ceiling(ActualWidth),(int)Math.Ceiling(ActualHeight),96,96,PixelFormats.Pbgra32);image.Render(this);var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(image));using(var file=File.Create(output+".png"))png.Save(file);
        // Preserve an actual on-screen anchor when old entries are evicted.
        for(var i=30;i<99;i++)Add(i);Render();await Layout();
        ShowReadingMessage("fill-50");await Layout();var item=displayed.Single(m=>m.Id=="fill-50");
        double Y()=>((FrameworkElement)MessageList.ItemContainerGenerator.ContainerFromItem(item)).TranslatePoint(new Point(),MessageScroll).Y;
        var oldY=Y();followingPaused=true;
        for(var i=99;i<106;i++)Add(i);Render();await Layout();
        Check(Math.Abs(Y()-oldY)<2,"arrival and oldest eviction preserve reading position");
        Check(readingQueue.Length<=100 && displayed.Count==readingQueue.Length,"history remains bounded without three-slot truncation");
        followingPaused=false;initialFit=false;Height=500;RequestContentLayout();await Layout();
        Check(Math.Abs(ActualHeight-500)<2 && MessageList.FontSize==13,"manual resize scrolls without shrinking text");
        Width=300;RequestContentLayout();await Layout();
        Check(MessageScroll.ExtentWidth<=MessageScroll.ViewportWidth+1,"narrow message pane has no horizontal overflow");
        var longPin=new MessageCard("Long pinned fixture",string.Join('\n',Enumerable.Repeat("Long pinned content",100)),[]);
        pinnedLatest=new IncomingMessage("long-pin","pin","",longPin.Body,now,SenderKind.Bot){Card=longPin};PinnedCard.Content=pinnedLatest;lastFitKey=null;RequestContentLayout();await Layout();
        Check(PinnedArea.ActualHeight<=Math.Max(32,(ActualHeight-40)*.4)+1 && MessageScroll.ViewportHeight>100,"long pin leaves regular messages usable");
        MessageScroll.ScrollToEnd();await Layout();Check(Math.Abs(MessageScroll.VerticalOffset-MessageScroll.ScrollableHeight)<2,"all retained history remains reachable");
        initialFit=true;lastFitKey=null;RequestContentLayout();await Layout();Check(Math.Abs(ActualHeight-CurrentWorkArea().Height)<2,"automatic mode restores full work area height");
        verifyContentFit=false;
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,samples,syntheticOnly=true}));
    }
}
