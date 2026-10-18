using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
internal static class CompactSummaryContract
{
    internal static async Task RunAsync(string directory)
    {
        Directory.CreateDirectory(directory);
        const string combo="https://example.invalid/radar/?combo=FF.TOKEN.bitget.bybit&mode=FF&q=token&tab=FF";
        const string radar="https://example.invalid/radar/?q=token&tab=FF";
        var actions=new[]{new CardLink("查看组合",combo),new CardLink("查看雷达",radar)};
        var samples=new[]{
            new MessageCard("🚨🚨 强信号聚集｜TOKEN｜3 组同时 ACTIVE","涉及4所 · 已持续0s\nR1｜SF｜买 GATE → 卖 BITGET\n净均 +0.28% · ACTIVE 1s\nR0｜FF｜买 BYBIT → 卖 BITGET\n净均 +0.17% · ACTIVE 59s\nR0｜FF｜买 BYBIT → 卖 BINANCE\n净均 +0.24% · ACTIVE 22s\n⚠ 警告：Bybit 1h 成本：资金费计算方式不同",actions,"red"),
            new MessageCard("TOKEN｜FF｜V2收敛｜R0 +0.34%","买 Bitget 永续 → 卖 Bybit 永续\n均值：净收益0.126%｜盘口差+0.344%｜指数差+0.007%\nBitget：资费-0.297%/2h\n⚠ 警告：Bybit 1h 成本：资金费计算方式不同",actions),
            new MessageCard("","1. [P3][期期] TOKEN | 多 Binance / 空 Aster\ntake: 0.3759% / 0.4298%\n质量: 样本少",actions),
            new MessageCard("🟣 Bitget 溢价指数突变提醒","1. 🟢 TOKENUSDT / USDT-FUTURES | 5分钟 close持续突降 | -0.3029 个百分点 | close -0.1884% -> -0.4913%",actions,"purple")};
        var content=new StackPanel{Margin=new Thickness(8)};
        content.Children.Add(new TextBlock{Text="桌面摘要预览（虚构样例）",FontWeight=FontWeights.Bold,Margin=new Thickness(0,0,0,8)});
        var window=new Window{Content=content,Width=430,SizeToContent=SizeToContent.Height,FontSize=13,FontFamily=new FontFamily("Microsoft YaHei"),ShowActivated=false,ShowInTaskbar=false,Left=-12000,Top=-12000,Background=Brushes.White};
        var views=new List<MessageView>();
        foreach(var card in samples){var view=new MessageView{Message=new IncomingMessage(Guid.NewGuid().ToString(),"fixture","",card.Body,DateTimeOffset.UtcNow,SenderKind.Bot){Card=card},Margin=new Thickness(0,0,0,8)};views.Add(view);content.Children.Add(view);}
        window.Show();await window.Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);window.UpdateLayout();
        void Check(bool ok,string label){if(!ok)throw new InvalidOperationException(label);}
        IEnumerable<T> Children<T>(DependencyObject obj) where T:DependencyObject
        {for(var i=0;i<VisualTreeHelper.GetChildrenCount(obj);i++){var child=VisualTreeHelper.GetChild(obj,i);if(child is T typed)yield return typed;foreach(var item in Children<T>(child))yield return item;}}
        var launched=new List<string>();var previous=MessageText.Launch;MessageText.Launch=uri=>launched.Add(uri.OriginalString);
        try
        {
            foreach(var view in views)
            {
                var buttons=Children<Button>(view).Where(b=>b.Tag is string).ToArray();Check(buttons.Length==2,"two unchanged action buttons");
                Check(buttons.Select(b=>b.Content).OrderBy(x=>x).SequenceEqual(actions.Select(a=>(object)a.Label).OrderBy(x=>x)),"button labels preserved");
                foreach(var button in buttons)button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                Check(launched.TakeLast(2).Order().SequenceEqual(new[]{combo,radar}.Order()),"exact original action URLs");
                Check(!view.IsExpanded && !Children<Expander>(view).Any(),"no full-text row; actions do not expand message");
                Check(MessageText.GetContent(view.FullBody!)==view.Message!.Card!.Body,"full original content retained");
                var surface=(Border)view.Children[0];
                surface.RaiseEvent(new System.Windows.Input.MouseButtonEventArgs(System.Windows.Input.Mouse.PrimaryDevice,0,System.Windows.Input.MouseButton.Left){RoutedEvent=UIElement.MouseLeftButtonUpEvent});
                window.UpdateLayout();Check(view.IsExpanded && view.FullBody!.IsVisible,"click message expands original text");
                surface.RaiseEvent(new System.Windows.Input.KeyEventArgs(System.Windows.Input.Keyboard.PrimaryDevice,PresentationSource.FromVisual(window),0,System.Windows.Input.Key.Enter){RoutedEvent=UIElement.KeyDownEvent});
                Check(!view.IsExpanded,"keyboard collapses original text");
                window.UpdateLayout();
                var summary=CompactMessage.From(view.Message!.Card!.Title,view.Message.Card.Body);
                var radarButton=buttons.Single(b=>(string)b.Content=="查看雷达");
                var comboButton=buttons.Single(b=>(string)b.Content=="查看组合");
                var footer=(WrapPanel)comboButton.Parent;var stack=(StackPanel)footer.Parent;
                Check(stack.Children[stack.Children.Count-1]==footer && footer.HorizontalAlignment==HorizontalAlignment.Right,"other actions remain bottom-right");
                if(summary.Spread.Length>0)
                {
                    var actionsRow=(WrapPanel)radarButton.Parent;var row=(Grid)actionsRow.Parent;
                    Check(Grid.GetColumn(actionsRow)==1 && row.Children[0] is TextBlock text && MessageText.GetContent(text)==summary.Spread,"radar shares spread row");
                    Check(Math.Abs(radarButton.TranslatePoint(new Point(radarButton.ActualWidth,0),row).X-row.ActualWidth)<2,"radar aligns to row right edge");
                }
                else Check(radarButton.Parent==footer,"no spread keeps radar in bottom-right footer");
                Check(Children<TextBlock>(view).Any(t=>t.Text==MessageView.RankFirstTitle(CompactMessage.From(view.Message!.Card!.Title,view.Message.Card.Body).Title)),"rank and value lead rendered title");
            }
            const string raw="[Dex 套利监控命中][最高P3]\n价格最大延迟: 45s\nsymbol黑名单: MEME, ONE\n1. [P3][现期] TOKEN | 多 Bitget 现货 / 空 OKX 合约\ntake: 0.9107% / 1.3489%, 30m 0.9107% (1)\n资金费: OKX 0.0825% / 4h\n质量: 瞬时，价差强\n查看详情: https://example.invalid/radar/?tab=SF&mode=SF&q=token";
            var plain=new MessageView{Message=new IncomingMessage("plain-dex","fixture","",raw,DateTimeOffset.UtcNow,SenderKind.Bot)};
            content.Children.Add(plain);window.UpdateLayout();
            Check(plain.FullBody is not null && !plain.IsExpanded,"plain-text DEX starts collapsed");
            Check(Children<TextBlock>(plain).Any(t=>t.Text=="P3｜TOKEN｜SF｜BG→OK"),"plain-text DEX gets instrument summary title");
            Check(MessageText.GetContent(plain.FullBody!)==raw,"plain-text DEX original is intact");
            var plainSurface=(Border)plain.Children[0];
            plainSurface.RaiseEvent(new System.Windows.Input.MouseButtonEventArgs(System.Windows.Input.Mouse.PrimaryDevice,0,System.Windows.Input.MouseButton.Left){RoutedEvent=UIElement.MouseLeftButtonUpEvent});
            window.UpdateLayout();Check(plain.IsExpanded && plain.FullBody!.IsVisible,"plain-text DEX click expands original");
            plainSurface.RaiseEvent(new System.Windows.Input.MouseButtonEventArgs(System.Windows.Input.Mouse.PrimaryDevice,0,System.Windows.Input.MouseButton.Left){RoutedEvent=UIElement.MouseLeftButtonUpEvent});
            Check(!plain.IsExpanded,"plain-text DEX click collapses original");
            window.UpdateLayout();
            var image=new RenderTargetBitmap((int)Math.Ceiling(window.ActualWidth),(int)Math.Ceiling(window.ActualHeight),96,96,PixelFormats.Pbgra32);image.Render(window);var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(image));using(var stream=File.Create(Path.Combine(directory,"desktop-summary-preview.png")))png.Save(stream);
            await File.WriteAllTextAsync(Path.Combine(directory,"desktop-summary-contract.json"),JsonSerializer.Serialize(new{passed=true,views=views.Count,actionClicks=launched.Count,exactUrls=true,fullText=true,syntheticOnly=true}));
        }
        finally{MessageText.Launch=previous;window.Close();}
    }
}
