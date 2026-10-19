using System.IO;
using System.Windows;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunBottomAlignmentContractAsync(string output)
    {
        AutoScroll.IsChecked=false;initialFit=false;Width=430;Height=630;
        selectedChats=new(["demo"],StringComparer.Ordinal);pinnedChatId="";
        var now=DateTimeOffset.UtcNow;store.Start(now.AddMinutes(-1));
        for(var i=0;i<40;i++)
        {
            var body="买 Bitget 永续 → 卖 Bybit 永续\n均值：净收益0.126%｜盘口差+0.344%｜指数差+0.007%"+(i%3==0?"\n⚠ 警告：Bybit 1h 成本：资金费计算方式不同":"");
            var card=new MessageCard("TOKEN｜FF｜V2收敛｜R0 +0.34%",body,[new CardLink("查看雷达","https://example.invalid/")]);
            store.Add(new IncomingMessage("bottom-"+i,"demo","",body,now.AddMilliseconds(i-100),SenderKind.Bot){Card=card},"demo",now);
        }
        Render();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        var checks=0;
        foreach(var font in new[]{13d,17d})
        foreach(var height in new[]{630d,850d})
        {
            FontScale.Value=font;Height=height;
            await Task.Delay(250);
            foreach(var offset in new[]{180d,440d,230d,710d})
            {
                MessageScroll.ScrollToVerticalOffset(offset);await Task.Delay(300);UpdateLayout();
                var viewport=MessageScroll.ViewportHeight;
                var last=displayed.Select(m=>MessageList.ItemContainerGenerator.ContainerFromItem(m)).OfType<FrameworkElement>()
                    .Last(el=>el.TranslatePoint(new Point(),MessageScroll).Y<viewport-.5);
                var top=last.TranslatePoint(new Point(),MessageScroll).Y;
                if(top<-.5 || top+last.ActualHeight>viewport+.5)throw new InvalidOperationException("Bottom compact message clipped");
                checks++;
            }
            foreach(var item in displayed.Take(5))
            {
                ShowReadingMessage(item.Id);await Task.Delay(300);UpdateLayout();
                var viewport=MessageScroll.ViewportHeight;
                var last=displayed.Select(m=>MessageList.ItemContainerGenerator.ContainerFromItem(m)).OfType<FrameworkElement>()
                    .Last(el=>el.TranslatePoint(new Point(),MessageScroll).Y<viewport-.5);
                if(last.TranslatePoint(new Point(0,last.ActualHeight),MessageScroll).Y>viewport+.5)throw new InvalidOperationException("Automatic reading clips bottom");
                checks++;
            }
        }
        await File.WriteAllTextAsync(output,System.Text.Json.JsonSerializer.Serialize(new{passed=true,checks,fonts=2,heights=2,includesWarnings=true}));
    }
}
